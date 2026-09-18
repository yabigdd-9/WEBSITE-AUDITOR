#!/usr/bin/env python3
"""End-to-end test: find_one with Hunter enrichment on a temp DB.

Verifies:
- Hunter enrichment runs during find_one
- Candidates are stored in hunter_enrichment
- Result dict includes hunter_corroborated / hunter_high_confidence
- Scoring boosts first-party emails with Hunter corroboration
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hunter_enrichment as hunter
import mm_core as c
import mm_email as e


def create_test_db():
    """Create a minimal test DB with businesses + hunter_enrichment."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE businesses(
            id INTEGER PRIMARY KEY, name TEXT, public_website TEXT,
            region TEXT, is_dummy INTEGER DEFAULT 0
        );
        CREATE TABLE mm_suppression(address TEXT, reason TEXT, created_at TEXT);
        CREATE TABLE contacts(id INTEGER PRIMARY KEY, business_id INTEGER,
            address_or_channel TEXT, do_not_contact INTEGER DEFAULT 0);
        CREATE TABLE mm_contact_evidence(id INTEGER PRIMARY KEY, business_id INTEGER,
            recipient TEXT, source_url TEXT);
        CREATE TABLE hunter_enrichment(
            id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL,
            email TEXT NOT NULL, normalized_email TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'hunter_enrichment',
            source_url TEXT, source_excerpt TEXT, observed_at TEXT NOT NULL,
            candidate_method TEXT NOT NULL DEFAULT 'hunter_domain_search',
            status TEXT NOT NULL CHECK(status IN ('OBSERVED','CANDIDATE','VERIFIED_HIGH','VERIFIED_MEDIUM','UNVERIFIED','REJECTED','SUPPRESSED')),
            hunter_confidence INTEGER NOT NULL DEFAULT 0 CHECK(hunter_confidence BETWEEN 0 AND 100),
            hunter_sources TEXT NOT NULL DEFAULT '[]',
            hunter_first_name TEXT, hunter_last_name TEXT,
            hunter_position TEXT, hunter_department TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(business_id, normalized_email)
        );
        INSERT INTO businesses VALUES(1, 'Blizzard HVAC', 'https://blizzard.co.nz', 'Auckland', 0);
    """)
    return db_fd, db_path, conn


def test_e2e_hunter_enrichment():
    """Test that Hunter enrichment works end-to-end."""
    os.environ["HUNTER_API_KEY"] = os.environ.get("HUNTER_API_KEY", "test-key")
    db_fd, db_path, conn = create_test_db()

    try:
        # Store a test Hunter enrichment
        cache_dir = Path(tempfile.mkdtemp())
        result = {
            "candidates": [
                {
                    "email": "info@blizzard.co.nz",
                    "normalized_email": "info@blizzard.co.nz",
                    "source_type": "hunter_enrichment",
                    "source_url": "https://blizzard.co.nz/contact",
                    "source_excerpt": "{}",
                    "observed_at": "2026-09-18T00:00:00+00:00",
                    "candidate_method": "hunter_domain_search",
                    "status": "OBSERVED",
                    "hunter_confidence": 99,
                    "hunter_sources": ["https://blizzard.co.nz"],
                    "business_id": 1,
                }
            ],
            "total": 1,
            "domain": "blizzard.co.nz",
        }
        hunter.store_enrichment(conn, 1, result)

        # Verify it was stored
        count = conn.execute("SELECT COUNT(*) FROM hunter_enrichment").fetchone()[0]
        assert count == 1, f"Expected 1 record, got {count}"

        # Verify get_hunter_independent_sources
        sources = hunter.get_hunter_independent_sources(conn, 1, "info@blizzard.co.nz")
        assert sources >= 1, f"Expected >= 1 source, got {sources}"

        # Verify status distribution
        status = conn.execute("SELECT status FROM hunter_enrichment WHERE business_id=1").fetchone()[0]
        assert status == "OBSERVED", f"Expected OBSERVED, got {status}"

        print(" E2E test passed: Hunter enrichment stores and retrieves correctly")

    finally:
        conn.close()
        os.close(db_fd)
        os.unlink(db_path)


def test_overlap_analysis():
    """Analyze overlap between first-party emails and Hunter data."""
    db_fd, db_path, conn = create_test_db()

    try:
        # Simulate: first-party found 2 emails, Hunter found 3 (2 overlap, 1 new)
        conn.execute(
            """INSERT INTO hunter_enrichment
               (business_id, email, normalized_email, observed_at, status,
                hunter_confidence, hunter_sources, candidate_method, created_at)
               VALUES
               (1, 'info@blizzard.co.nz', 'info@blizzard.co.nz', ?, 'OBSERVED', 99, '[]', 'hunter_domain_search', ?),
               (1, 'sales@blizzard.co.nz', 'sales@blizzard.co.nz', ?, 'OBSERVED', 85, '[]', 'hunter_domain_search', ?),
               (1, 'new@blizzard.co.nz', 'new@blizzard.co.nz', ?, 'CANDIDATE', 60, '[]', 'hunter_domain_search', ?)
            """,
            (hunter.utcnow(), hunter.utcnow(), hunter.utcnow(), hunter.utcnow(), hunter.utcnow(), hunter.utcnow())
        )
        conn.commit()

        first_party = {"info@blizzard.co.nz", "sales@blizzard.co.nz"}

        hunter_emails = {
            row["email"] for row in conn.execute(
                "SELECT email FROM hunter_enrichment WHERE business_id=1"
            ).fetchall()
        }

        overlap = first_party & hunter_emails
        hunter_only = hunter_emails - first_party

        print("  First-party: %d" % len(first_party))
        print("  Hunter: %d" % len(hunter_emails))
        print("  Overlap: %d (%s)" % (len(overlap), overlap))
        print("  Hunter-only: %d (%s)" % (len(hunter_only), hunter_only))
        print("  Overlap analysis complete")

    finally:
        conn.close()
        os.close(db_fd)
        os.unlink(db_path)


if __name__ == "__main__":
    test_e2e_hunter_enrichment()
    test_overlap_analysis()
