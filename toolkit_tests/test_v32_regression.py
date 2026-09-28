import json
import os
import sqlite3
import sys

import pytest

# Ensure MoneyMachine is importable for tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../money-machine')))
import mm_core as c
import mm_email_store as email_store
import mm_evolutionary_genome as genome
import mm_unified_field as unified_field


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """Provides a fresh, schema-initialized database connection for regression tests."""
    db_file = tmp_path / "test_mm.db"
    # Direct sqlite3.connect (not c.connect which uses URI mode=rw requiring existing file)
    conn = sqlite3.connect(db_file, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=10000')
    # Register UDFs that mm_core normally registers
    conn.create_function('mm_digest', 2, c.digest, deterministic=True)
    conn.create_function('mm_proposal_digest', 3, lambda r, b, p: c.proposal_digest(r, b, p))
    # Initialize base schema
    conn.executescript(c.SCHEMA)
    conn.executescript(c.TRIGGERS)
    # Initialize only essential legacy tables, NOT email-specific ones
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, business_id INTEGER, address_or_channel TEXT, do_not_contact INTEGER, source TEXT);
    ''')
    conn.commit()

    # Create a minimal backup manifest with a verified DB item
    backup = tmp_path / "backups" / "mm-v2-manual"
    backup.mkdir(parents=True, exist_ok=True)
    # Create a dummy DB file for the manifest to reference
    dummy_db = backup / "money_machine.db"
    # Create valid SQLite DB
    temp_conn = sqlite3.connect(dummy_db)
    temp_conn.executescript(c.SCHEMA)
    temp_conn.close()

    manifest = {
        "created_at": c.now(),
        "items": [
            {"source": str(dummy_db), "path": str(dummy_db), "sha256": c.sha(dummy_db.read_bytes())}
        ]
    }
    (backup / "manifest.json").write_text(json.dumps(manifest))

    # Set MM_ROOT so mm_core.root() resolves correctly
    monkeypatch.setenv('MM_ROOT', str(tmp_path))

    # Return connection and backup path for the test
    yield conn, backup
    conn.close()

def test_email_migration_integrity(db_conn):
    """Verify that email storage migrations correctly handle legacy state."""
    conn, backup = db_conn
    # Insert a test business first (contacts reference businesses via FK)
    conn.execute("INSERT INTO businesses (name, source, discovered_at, current_status) VALUES ('TestCo', 'fixture', ?, 'discovered')", (c.now(),))
    conn.commit()
    # Insert legacy contacts
    conn.execute("INSERT INTO contacts (business_id, address_or_channel, do_not_contact) VALUES (1, 'blocked@example.com', 1)")
    conn.execute("INSERT INTO contacts (business_id, address_or_channel, do_not_contact) VALUES (1, 'active@example.com', 0)")
    conn.commit()

    # Run migration
    email_store.migrate_email(conn, backup)

    # Assert
    blocked = conn.execute("SELECT status FROM email_candidates WHERE email='blocked@example.com'").fetchone()
    active = conn.execute("SELECT status FROM email_candidates WHERE email='active@example.com'").fetchone()

    assert blocked[0] == 'SUPPRESSED'
    assert active[0] == 'UNVERIFIED'

def test_evolutionary_diversity_calculation(db_conn):
    """Verify that diversity metrics are calculated correctly."""
    conn, _ = db_conn
    # Setup: Encode architectural genes
    pattern = "test_pattern"
    params = {"weight": 0.5}
    genome.encode_architectural_genes(conn, pattern, params, generation=1)

    # Calculate diversity
    diversity = genome.get_genetic_diversity_metrics()

    # Assert
    assert "total_genetic_encodings" in diversity
    assert isinstance(diversity["total_genetic_encodings"], int)

def test_unified_field_coherence(db_conn):
    """Verify that cross-component coherence calculation handles insufficient data correctly."""
    conn, _ = db_conn
    # Define test scenario: insufficient data pairs (no data in DB)
    pairs = [("compA", "compB")]

    # Analyze
    results = unified_field.measure_cross_component_coherence(conn, pairs)

    # Assert: Key is formatted as component_a_component_b in nested 'results'
    key = "compA_compB"
    assert key in results["results"]
    assert results["results"][key]["status"] == "insufficient_data"
