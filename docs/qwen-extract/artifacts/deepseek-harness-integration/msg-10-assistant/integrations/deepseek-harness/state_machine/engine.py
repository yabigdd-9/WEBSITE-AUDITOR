import sqlite3
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

DB_PATH = os.path.join(os.getcwd(), 'harness_state.db')

class StateMachineEngine:
    """
    Deterministic state manager for WEBSITE-AUDITOR prospects.
    Enforces legal transitions and records evidence for every step.
    """
    
    LEGAL_TRANSITIONS = {
        'DISCOVERED': ['IDENTITY_PENDING', 'REJECTED'],
        'IDENTITY_PENDING': ['IDENTITY_RESOLVED', 'PERMANENT_FAILURE'],
        'IDENTITY_RESOLVED': ['AUDIT_PENDING'],
        'AUDIT_PENDING': ['AUDITED', 'RETRYABLE_FAILURE'],
        'AUDITED': ['QUALIFICATION_PENDING'],
        'QUALIFICATION_PENDING': ['QUALIFIED', 'REJECTED'],
        'QUALIFIED': ['CONTACT_PENDING'],
        'CONTACT_PENDING': ['CONTACT_RESOLVED', 'NO_VERIFIED_EMAIL'],
        'CONTACT_RESOLVED': ['VERIFICATION_PENDING'],
        'VERIFICATION_PENDING': ['VERIFIED', 'REJECTED'], # Rejected if low conf
        'VERIFIED': ['REMEDIATION_PENDING'],
        'REMEDIATION_PENDING': ['DEMO_PENDING'],
        'DEMO_PENDING': ['DEMO_READY', 'RETRYABLE_FAILURE'],
        'DEMO_READY': ['QA_PENDING'],
        'QA_PENDING': ['OUTREACH_PENDING', 'NEEDS_REVIEW'],
        'OUTREACH_PENDING': ['APPROVAL_PENDING'],
        'APPROVAL_PENDING': ['READY_TO_SEND', 'REJECTED'],
        'READY_TO_SEND': ['SENT', 'QUARANTINED'],
        'SENT': ['RESPONDED', 'BOUNCED'],
        'RESPONDED': ['CONVERTED', 'LOST'],
        # Terminal/Error States
        'REJECTED': [],
        'NO_VERIFIED_EMAIL': [],
        'PERMANENT_FAILURE': [],
        'SUPPRESSED': [],
        'DUPLICATE': [],
        'QUARANTINED': [] # Can move back to READY_TO_SEND after manual review
    }

    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prospects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT UNIQUE NOT NULL,
                business_name TEXT,
                current_state TEXT DEFAULT 'DISCOVERED',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSON
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transition_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER,
                from_state TEXT,
                to_state TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actor TEXT, -- 'hermes', 'deepseek_harness', 'human'
                evidence_path TEXT, -- Path to JSON/HTML proof
                reason TEXT,
                FOREIGN KEY(prospect_id) REFERENCES prospects(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS outreach_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER,
                recipient_email TEXT,
                confidence_score REAL,
                template_version TEXT,
                sent_at TIMESTAMP,
                status TEXT, -- 'SENT', 'DELIVERED', 'OPENED', 'CLICKED', 'BOUNCED'
                message_id TEXT,
                UNIQUE(prospect_id, recipient_email, template_version) -- Idempotency key
            )
        ''')
        self.conn.commit()

    def register_prospect(self, domain: str, business_name: str = None) -> int:
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO prospects (domain, business_name, current_state) VALUES (?, ?, ?)",
                (domain, business_name, 'DISCOVERED')
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate detected
            cursor.execute("SELECT id FROM prospects WHERE domain = ?", (domain,))
            row = cursor.fetchone()
            if row:
                self.log_transition(row[0], 'EXISTING', 'DUPLICATE', 'system', '', 'Duplicate domain detected')
                return -1 # Signal duplicate
            raise

    def get_state(self, prospect_id: int) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT current_state FROM prospects WHERE id = ?", (prospect_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def transition(self, prospect_id: int, new_state: str, actor: str, evidence_path: str = "", reason: str = "") -> bool:
        current_state = self.get_state(prospect_id)
        if not current_state:
            return False
        
        allowed_next_states = self.LEGAL_TRANSITIONS.get(current_state, [])
        
        if new_state not in allowed_next_states:
            # Illegal transition attempt
            self.log_transition(prospect_id, current_state, 'ILLEGAL_ATTEMPT_' + new_state, actor, '', f'Transition blocked: {current_state} -> {new_state}')
            return False
            
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE prospects SET current_state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_state, prospect_id)
        )
        self.log_transition(prospect_id, current_state, new_state, actor, evidence_path, reason)
        self.conn.commit()
        return True

    def log_transition(self, prospect_id: int, from_state: str, to_state: str, actor: str, evidence_path: str, reason: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO transition_log (prospect_id, from_state, to_state, actor, evidence_path, reason) VALUES (?, ?, ?, ?, ?, ?)",
            (prospect_id, from_state, to_state, actor, evidence_path, reason)
        )

    def record_outreach_send(self, prospect_id: int, email: str, confidence: float, template_ver: str, msg_id: str):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO outreach_records (prospect_id, recipient_email, confidence_score, template_version, sent_at, status, message_id) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'SENT', ?)",
                (prospect_id, email, confidence, template_ver, msg_id)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False # Already sent this version to this person

    def close(self):
        self.conn.close()
