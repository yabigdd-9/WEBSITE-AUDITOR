#!/usr/bin/env python3
"""Tests for Hunter.io enrichment adapter."""
import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hunter_enrichment as hunter


class TestHunterAPISafety(unittest.TestCase):

    def test_get_api_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                hunter.get_api_key()
            self.assertIn("HUNTER_API_KEY not set", str(ctx.exception))

    def test_get_api_key_present(self):
        with patch.dict(os.environ, {"HUNTER_API_KEY": "test-key-123"}):
            self.assertEqual(hunter.get_api_key(), "test-key-123")

    @patch("hunter_enrichment.socket.getaddrinfo")
    def test_safe_getaddr_rejects_private_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, '', ('192.168.1.1', 443))]
        with self.assertRaises(ValueError) as ctx:
            hunter._safe_getaddr("api.hunter.io")
        self.assertIn("Non-public IP", str(ctx.exception))

    @patch("hunter_enrichment.socket.getaddrinfo")
    def test_safe_getaddr_accepts_public_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, '', ('104.26.10.78', 443))]
        ip = hunter._safe_getaddr("api.hunter.io")
        self.assertEqual(ip, "104.26.10.78")

    @patch("hunter_enrichment.socket.getaddrinfo")
    def test_safe_getaddr_no_resolution(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = []
        with self.assertRaises(ValueError) as ctx:
            hunter._safe_getaddr("api.hunter.io")
        self.assertIn("No DNS resolution", str(ctx.exception))


class TestDomainSearch(unittest.TestCase):

    def setUp(self):
        self.cache_dir = Path(tempfile.mkdtemp())
        os.environ["HUNTER_API_KEY"] = "test-key"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def _make_email_entry(self, value="info@example.com", confidence=85, **kwargs):
        return {"value": value, "confidence": confidence, "type": "personal",
                "sources": [{"uri": "https://example.com"}], **kwargs}

    @patch("hunter_enrichment._api_request")
    def test_domain_search_normalizes(self, mock_request):
        mock_request.return_value = {
            "data": {"domain": "example.com", "emails": [self._make_email_entry()], "total": 1}
        }
        result = hunter.domain_search("example.com", limit=5, cache_dir=self.cache_dir)
        self.assertEqual(result["domain"], "example.com")
        self.assertEqual(len(result["emails"]), 1)

    @patch("hunter_enrichment._api_request")
    def test_domain_search_caches(self, mock_request):
        mock_request.return_value = {
            "data": {"domain": "example.com", "emails": [self._make_email_entry()], "total": 1}
        }
        hunter.domain_search("example.com", limit=5, cache_dir=self.cache_dir)
        hunter.domain_search("example.com", limit=5, cache_dir=self.cache_dir)
        self.assertEqual(mock_request.call_count, 1)

    @patch("hunter_enrichment._api_request")
    def test_domain_search_handles_404(self, mock_request):
        mock_request.return_value = None
        result = hunter.domain_search("example.com", limit=5, cache_dir=self.cache_dir)
        self.assertIsNone(result)


class TestEmailVerifier(unittest.TestCase):

    def setUp(self):
        self.cache_dir = Path(tempfile.mkdtemp())
        os.environ["HUNTER_API_KEY"] = "test-key"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    @patch("hunter_enrichment._api_request")
    def test_email_verifier_deliverable(self, mock_request):
        mock_request.return_value = {"data": {"result": "deliverable", "score": 95,
            "regexp": True, "disposable": False, "webmail": False, "mx_records": True,
            "smtp_server": True, "smtp_check": True, "accept_all": False, "block": False,
            "sources": [{"uri": "https://example.com"}]}}
        result = hunter.email_verifier("info@example.com", cache_dir=self.cache_dir)
        self.assertEqual(result["result"], "deliverable")
        self.assertEqual(result["score"], 95)

    @patch("hunter_enrichment._api_request")
    def test_email_verifier_disposable(self, mock_request):
        mock_request.return_value = {"data": {"result": "risky", "score": 0,
            "disposable": True, "sources": []}}
        result = hunter.email_verifier("test@mailinator.com", cache_dir=self.cache_dir)
        self.assertTrue(result["disposable"])


class TestStatusMapping(unittest.TestCase):

    def test_high_confidence(self):
        candidate = hunter.hunter_to_candidate(
            {"value": "info@example.com", "confidence": 85}, 1, "example.com")
        self.assertEqual(candidate["status"], "OBSERVED")

    def test_medium_confidence(self):
        candidate = hunter.hunter_to_candidate(
            {"value": "info@example.com", "confidence": 65}, 1, "example.com")
        self.assertEqual(candidate["status"], "CANDIDATE")

    def test_low_confidence(self):
        candidate = hunter.hunter_to_candidate(
            {"value": "info@example.com", "confidence": 30}, 1, "example.com")
        self.assertEqual(candidate["status"], "UNVERIFIED")

    def test_invalid_email(self):
        candidate = hunter.hunter_to_candidate(
            {"value": "", "confidence": 85}, 1, "example.com")
        self.assertIsNone(candidate)


class TestStoreEnrichment(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE businesses(id INTEGER PRIMARY KEY);
            INSERT INTO businesses VALUES(1);
            CREATE TABLE hunter_enrichment(
                id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL,
                email TEXT NOT NULL, normalized_email TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'hunter_enrichment',
                source_url TEXT, source_excerpt TEXT, observed_at TEXT NOT NULL,
                candidate_method TEXT NOT NULL DEFAULT 'hunter_domain_search',
                status TEXT NOT NULL,
                hunter_confidence INTEGER NOT NULL DEFAULT 0,
                hunter_sources TEXT NOT NULL DEFAULT '[]',
                hunter_first_name TEXT, hunter_last_name TEXT,
                hunter_position TEXT, hunter_department TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(business_id, normalized_email)
            );
        """)

    def tearDown(self):
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_store_inserts(self):
        result = {"candidates": [{
            "email": "info@example.com", "normalized_email": "info@example.com",
            "source_type": "hunter_enrichment", "source_url": "https://example.com",
            "source_excerpt": "{}", "observed_at": hunter.utcnow(),
            "candidate_method": "hunter_domain_search", "status": "OBSERVED",
            "hunter_confidence": 85, "hunter_sources": [], "business_id": 1,
        }], "total": 1, "domain": "example.com"}
        hunter.store_enrichment(self.conn, 1, result)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM hunter_enrichment").fetchone()[0], 1)

    def test_store_idempotent(self):
        result = {"candidates": [{
            "email": "info@example.com", "normalized_email": "info@example.com",
            "source_type": "hunter_enrichment", "source_url": "https://example.com",
            "source_excerpt": "{}", "observed_at": hunter.utcnow(),
            "candidate_method": "hunter_domain_search", "status": "OBSERVED",
            "hunter_confidence": 85, "hunter_sources": [], "business_id": 1,
        }], "total": 1, "domain": "example.com"}
        hunter.store_enrichment(self.conn, 1, result)
        hunter.store_enrichment(self.conn, 1, result)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM hunter_enrichment").fetchone()[0], 1)


class TestGetHunterIndependentSources(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE businesses(id INTEGER PRIMARY KEY);
            INSERT INTO businesses VALUES(1);
            CREATE TABLE hunter_enrichment(
                id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL,
                email TEXT NOT NULL, normalized_email TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'hunter_enrichment',
                source_url TEXT, source_excerpt TEXT, observed_at TEXT NOT NULL,
                candidate_method TEXT NOT NULL DEFAULT 'hunter_domain_search',
                status TEXT NOT NULL, hunter_confidence INTEGER NOT NULL DEFAULT 0,
                hunter_sources TEXT NOT NULL DEFAULT '[]',
                hunter_first_name TEXT, hunter_last_name TEXT,
                hunter_position TEXT, hunter_department TEXT,
                created_at TEXT NOT NULL, UNIQUE(business_id, normalized_email)
            );
        """)
        self.conn.execute(
            """INSERT INTO hunter_enrichment
               (business_id, email, normalized_email, observed_at, status,
                hunter_confidence, hunter_sources, source_url, candidate_method, created_at)
               VALUES (1, 'info@example.com', 'info@example.com', ?, 'OBSERVED', 85,
                       ?, 'https://source1.com', 'hunter_domain_search', ?)""",
            (hunter.utcnow(), json.dumps(["https://source1.com", "https://source2.com"]), hunter.utcnow()))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_count_sources(self):
        count = hunter.get_hunter_independent_sources(self.conn, 1, "info@example.com")
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
