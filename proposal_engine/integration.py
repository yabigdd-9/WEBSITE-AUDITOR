"""
Integration module for proposal engine with audit logging and security features.
"""

import sqlite3
import json
import time
import hashlib
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from threading import Lock
from collections import defaultdict, deque


class SQLiteAuditLogger:
    """SQLite-based audit logger for proposal events."""

    def __init__(self, db_path: str = "./audit.db"):
        """Initialize the audit logger with SQLite database.

        Args:
            db_path: Path to SQLite database file (default: persistent file)
        """
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Initialize the database schema for audit logging."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY,
                    business_id TEXT NOT NULL,
                    website_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata_json TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_proposals_business_id
                ON proposals(business_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_proposals_website_id
                ON proposals(website_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_proposals_timestamp
                ON proposals(timestamp)
            """)

            # Additional indexes for better query performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_proposals_status_timestamp
                ON proposals(status, timestamp)
            """)
            conn.commit()

    def log_proposal_event(self, proposal_id: str, business_id: str, website_id: str,
                          status: str, metadata: Optional[Dict[str, Any]] = None):
        """Log a proposal event to the audit trail.

        Args:
            proposal_id: Unique identifier for the proposal
            business_id: Identifier for the business
            website_id: Identifier for the website
            status: Current status of the proposal
            metadata: Optional metadata dictionary
        """
        timestamp = time.time()
        metadata_json = json.dumps(metadata) if metadata else None

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO proposals
                (id, business_id, website_id, status, timestamp, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (proposal_id, business_id, website_id, status, timestamp, metadata_json))
            conn.commit()

    def query_audit_trail(self, business_id: Optional[str] = None,
                         website_id: Optional[str] = None,
                         status: Optional[str] = None,
                         start_time: Optional[float] = None,
                         end_time: Optional[float] = None,
                         limit: int = 100) -> List[Dict[str, Any]]:
        """Query the audit trail with optional filters.

        Args:
            business_id: Filter by business ID
            website_id: Filter by website ID
            status: Filter by status
            start_time: Filter by start timestamp (inclusive)
            end_time: Filter by end timestamp (inclusive)
            limit: Maximum number of results to return

        Returns:
            List of proposal event dictionaries
        """
        query = "SELECT id, business_id, website_id, status, timestamp, metadata_json FROM proposals WHERE 1=1"
        params = []

        if business_id:
            query += " AND business_id = ?"
            params.append(business_id)

        if website_id:
            query += " AND website_id = ?"
            params.append(website_id)

        if status:
            query += " AND status = ?"
            params.append(status)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                event = {
                    'id': row['id'],
                    'business_id': row['business_id'],
                    'website_id': row['website_id'],
                    'status': row['status'],
                    'timestamp': row['timestamp'],
                    'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else None
                }
                results.append(event)

            return results

    def get_context_for_agent_run(self, business_id: Optional[str] = None,
                                 website_id: Optional[str] = None,
                                 status: Optional[str] = None,
                                 start_time: Optional[float] = None,
                                 end_time: Optional[float] = None,
                                 limit: int = 10) -> str:
        """Get past execution logs formatted as context for new agent runs.

        Args:
            business_id: Filter by business ID
            website_id: Filter by website ID
            status: Filter by status
            start_time: Filter by start timestamp (inclusive)
            end_time: Filter by end timestamp (inclusive)
            limit: Maximum number of results to return

        Returns:
            Formatted string containing past execution logs suitable for use as context
        """
        events = self.query_audit_trail(
            business_id=business_id,
            website_id=website_id,
            status=status,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        if not events:
            return "No past execution logs found."

        context_parts = ["Past Execution Logs:"]
        for i, event in enumerate(events, 1):
            timestamp_str = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(event['timestamp'])
            )
            context_parts.append(
                f"\n{i}. Proposal ID: {event['id']}"
                f"\n   Business: {event['business_id']}"
                f"\n   Website: {event['website_id']}"
                f"\n   Status: {event['status']}"
                f"\n   Timestamp: {timestamp_str}"
            )

            if event['metadata']:
                context_parts.append(f"   Metadata: {json.dumps(event['metadata'], indent=2)}")

        context_parts.append(f"\nTotal: {len(events)} execution log(s)")
        return "\n".join(context_parts)

    def get_recent_context(self, hours: int = 24, limit: int = 5) -> str:
        """Get recent execution logs as context for agent runs.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of results to return

        Returns:
            Formatted string containing recent execution logs suitable for use as context
        """
        start_time = time.time() - (hours * 3600)
        return self.get_context_for_agent_run(
            start_time=start_time,
            limit=limit
        )


class TokenBucket:
    """Token bucket implementation for rate limiting."""

    def __init__(self, capacity: int, refill_rate: float):
        """Initialize token bucket.

        Args:
            capacity: Maximum number of tokens in bucket
            refill_rate: Rate at which tokens are refilled per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens from bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if not enough tokens
        """
        with self.lock:
            now = time.time()
            # Refill tokens based on time elapsed
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


class SecurityLayer:
    """Security layer for input validation and rate limiting."""

    def __init__(self, max_calls_per_minute: int = 100):
        """Initialize security layer.

        Args:
            max_calls_per_minute: Maximum calls allowed per minute per business_id
        """
        self.max_calls_per_minute = max_calls_per_minute
        self.refill_rate = max_calls_per_minute / 60.0  # Tokens per second
        self.buckets: Dict[str, TokenBucket] = {}
        self.bucket_lock = Lock()

    def sanitize_input(self, input_str: str) -> str:
        """Sanitize input string to prevent injection attacks.

        Args:
            input_str: Input string to sanitize

        Returns:
            Sanitized string
        """
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '&', ';', '(', ')', '|', '`', '$', '\\']
        sanitized = input_str
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        return sanitized.strip()

    def validate_proposal_schema(self, proposal_data: Dict[str, Any]) -> bool:
        """Validate proposal data against expected schema.

        Args:
            proposal_data: Dictionary containing proposal data

        Returns:
            True if valid, False otherwise
        """
        required_fields = ['business_id', 'website_id']

        # Check required fields exist and are non-empty strings
        for field in required_fields:
            if field not in proposal_data:
                return False
            if not isinstance(proposal_data[field], str) or not proposal_data[field].strip():
                return False

        # Validate ID formats (alphanumeric and hyphens/underscores)
        import re
        id_pattern = re.compile(r'^[a-zA-Z0-9_-]+$')

        for field in required_fields:
            if not id_pattern.match(proposal_data[field]):
                return False

        # Optional fields validation
        if 'status' in proposal_data:
            valid_statuses = ['draft', 'review', 'approved', 'rejected', 'sent']
            if proposal_data['status'] not in valid_statuses:
                return False

        return True

    def rate_limiter(self, business_id: str) -> bool:
        """Check if request is allowed based on rate limiting.

        Args:
            business_id: Identifier for the business making the request

        Returns:
            True if request is allowed, False if rate limited
        """
        with self.bucket_lock:
            if business_id not in self.buckets:
                # Create new token bucket for this business_id
                self.buckets[business_id] = TokenBucket(
                    capacity=self.max_calls_per_minute,
                    refill_rate=self.refill_rate
                )

            bucket = self.buckets[business_id]
            return bucket.consume(1)