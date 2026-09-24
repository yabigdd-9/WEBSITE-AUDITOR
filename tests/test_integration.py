"""
Tests for the proposal_engine integration module.
"""

import unittest
import tempfile
import os
import json
from proposal_engine.integration import SQLiteAuditLogger, SecurityLayer


class TestSQLiteAuditLogger(unittest.TestCase):
    """Test cases for SQLiteAuditLogger class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Create a temporary database file for testing
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.logger = SQLiteAuditLogger(self.db_path)

    def tearDown(self):
        """Tear down test fixtures after each test method."""
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_init_db_creates_table(self):
        """Test that init_db creates the proposals table."""
        # The table should already be created in setUp
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='proposals'"
            )
            result = cursor.fetchone()
            self.assertIsNotNone(result)

    def test_log_proposal_event(self):
        """Test logging a proposal event."""
        proposal_id = "test-proposal-1"
        business_id = "biz-123"
        website_id = "site-456"
        status = "draft"
        metadata = {"source": "test", "version": "1.0"}

        self.logger.log_proposal_event(
            proposal_id, business_id, website_id, status, metadata
        )

        # Query the event back
        results = self.logger.query_audit_trail(business_id=business_id)
        self.assertEqual(len(results), 1)
        event = results[0]
        self.assertEqual(event['id'], proposal_id)
        self.assertEqual(event['business_id'], business_id)
        self.assertEqual(event['website_id'], website_id)
        self.assertEqual(event['status'], status)
        self.assertEqual(event['metadata'], metadata)

    def test_query_audit_trail_filters(self):
        """Test querying audit trail with various filters."""
        # Log multiple events
        self.logger.log_proposal_event("prop1", "biz1", "site1", "draft", {"test": 1})
        self.logger.log_proposal_event("prop2", "biz1", "site2", "approved", {"test": 2})
        self.logger.log_proposal_event("prop3", "biz2", "site1", "rejected", {"test": 3})

        # Filter by business_id
        results = self.logger.query_audit_trail(business_id="biz1")
        self.assertEqual(len(results), 2)

        # Filter by website_id
        results = self.logger.query_audit_trail(website_id="site1")
        self.assertEqual(len(results), 2)

        # Filter by status
        results = self.logger.query_audit_trail(status="approved")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], "prop2")

        # Filter by multiple criteria
        results = self.logger.query_audit_trail(business_id="biz1", website_id="site1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], "prop1")

    def test_query_audit_trail_limit(self):
        """Test that limit parameter works correctly."""
        # Log 5 events
        for i in range(5):
            self.logger.log_proposal_event(
                f"prop{i}", "biz1", f"site{i}", "draft", {"index": i}
            )

        # Query with limit 3
        results = self.logger.query_audit_trail(business_id="biz1", limit=3)
        self.assertEqual(len(results), 3)

        # Should be ordered by timestamp descending (most recent first)
        # Since we logged them in order, the last 3 should be returned
        self.assertEqual(results[0]['id'], "prop4")
        self.assertEqual(results[1]['id'], "prop3")
        self.assertEqual(results[2]['id'], "prop2")


class TestSecurityLayer(unittest.TestCase):
    """Test cases for SecurityLayer class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.security = SecurityLayer(max_calls_per_minute=60)  # 1 per second for testing

    def test_sanitize_input(self):
        """Test input sanitization."""
        # Test normal string
        self.assertEqual(self.security.sanitize_input("hello world"), "hello world")

        # Test string with dangerous characters
        self.assertEqual(
            self.security.sanitize_input("<script>alert('xss')</script>"),
            "scriptalertxss/script"
        )

        # Test string with quotes and ampersands
        self.assertEqual(
            self.security.sanitize_input("test'\"&;<>()|`$\\"),
            "test"
        )

        # Test whitespace stripping
        self.assertEqual(self.security.sanitize_input("  hello  "), "hello")

    def test_validate_proposal_schema_valid(self):
        """Test validation of valid proposal data."""
        valid_data = {
            "business_id": "biz-123",
            "website_id": "site-456",
            "status": "draft"
        }
        self.assertTrue(self.security.validate_proposal_schema(valid_data))

        # Test with minimal required fields
        minimal_data = {
            "business_id": "biz-123",
            "website_id": "site-456"
        }
        self.assertTrue(self.security.validate_proposal_schema(minimal_data))

    def test_validate_proposal_schema_invalid(self):
        """Test validation of invalid proposal data."""
        # Missing required field
        invalid_data = {
            "business_id": "biz-123"
            # missing website_id
        }
        self.assertFalse(self.security.validate_proposal_schema(invalid_data))

        # Empty business_id
        invalid_data = {
            "business_id": "",
            "website_id": "site-456"
        }
        self.assertFalse(self.security.validate_proposal_schema(invalid_data))

        # Invalid characters in ID
        invalid_data = {
            "business_id": "biz@123",
            "website_id": "site-456"
        }
        self.assertFalse(self.security.validate_proposal_schema(invalid_data))

        # Invalid status
        invalid_data = {
            "business_id": "biz-123",
            "website_id": "site-456",
            "status": "invalid-status"
        }
        self.assertFalse(self.security.validate_proposal_schema(invalid_data))

        # Wrong type for ID
        invalid_data = {
            "business_id": 123,  # should be string
            "website_id": "site-456"
        }
        self.assertFalse(self.security.validate_proposal_schema(invalid_data))

    def test_rate_limiter_allows_requests_under_limit(self):
        """Test that rate limiter allows requests under the limit."""
        business_id = "test-biz"

        # Should allow first request
        self.assertTrue(self.security.rate_limiter(business_id))

        # Should allow several more requests (we set limit to 60 per minute)
        for _ in range(10):
            self.assertTrue(self.security.rate_limiter(business_id))

    def test_rate_limiter_blocks_excessive_requests(self):
        """Test that rate limiter blocks excessive requests."""
        business_id = "test-biz"

        # Use a very low limit for testing
        security_low_limit = SecurityLayer(max_calls_per_minute=5)  # 5 per minute

        # Allow first 5 requests
        for _ in range(5):
            self.assertTrue(security_low_limit.rate_limiter(business_id))

        # 6th request should be blocked
        self.assertFalse(security_low_limit.rate_limiter(business_id))

        # Additional requests should also be blocked
        self.assertFalse(security_low_limit.rate_limiter(business_id))
        self.assertFalse(security_low_limit.rate_limiter(business_id))

    def test_rate_limiter_different_business_ids(self):
        """Test that rate limiting is per business_id."""
        security = SecurityLayer(max_calls_per_minute=2)  # Very low limit for testing

        biz1_allowed = True
        biz2_allowed = True

        # First requests for both businesses should be allowed
        self.assertTrue(security.rate_limiter("biz-1"))
        self.assertTrue(security.rate_limiter("biz-2"))

        # Second requests for both businesses should be allowed
        self.assertTrue(security.rate_limiter("biz-1"))
        self.assertTrue(security.rate_limiter("biz-2"))

        # Third requests for both businesses should be blocked
        self.assertFalse(security.rate_limiter("biz-1"))
        self.assertFalse(security.rate_limiter("biz-2"))


if __name__ == '__main__':
    unittest.main()