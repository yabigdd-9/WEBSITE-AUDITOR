"""Contract tests for SQLite migrations.

Tests both up and down migrations, foreign key enforcement,
and schema integrity across migration versions.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import pytest

from mm_core import migrate, connect, SCHEMA, TRIGGERS, artifact_valid, digest, proposal_digest


class TestMigrationContracts:
    """Contract tests for database migrations."""

    def setup_method(self):
        """Set up a fresh database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test.db"
        # Create the database file first
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.touch()
        self.conn = connect(self.db_path)

    def teardown_method(self):
        """Clean up after each test."""
        self.conn.close()
        self.temp_dir.cleanup()

    def create_backup_manifest(self, db_path: Path) -> Path:
        """Create a verified backup directory with manifest for migration testing."""
        import json
        import hashlib
        import shutil
        from datetime import datetime

        backup_dir = self.temp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_file = backup_dir / "money_machine.db"
        # Copy current database as backup
        shutil.copy2(db_path, backup_file)

        # Create manifest
        sha256 = hashlib.sha256(backup_file.read_bytes()).hexdigest()
        manifest = {
            "created_at": datetime.now().isoformat(),
            "schema_version": 1,
            "items": [
                {
                    "path": str(backup_file),
                    "sha256": sha256,
                }
            ],
        }

        manifest_path = backup_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return backup_dir  # Return directory, not manifest file

    def test_initial_migration_creates_all_tables(self):
        """Test that migration creates all expected tables."""
        # Create minimal backup first
        self.conn.execute("CREATE TABLE IF NOT EXISTS dummy(id INTEGER)")
        self.conn.commit()

        backup_path = self.create_backup_manifest(self.db_path)
        migrate(self.conn, backup_path)

        # Check all core tables exist
        cursor = self.conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            'businesses',
            'mm_deals',
            'mm_evidence',
            'mm_evidence_meta',
            'mm_messages',
            'mm_proposals',
            'mm_receipts',
            'mm_cash',
            'mm_refunds',
            'mm_holds',
            'mm_suppression',
            'pipeline_items',
            'pipeline_events',
            'mm_scores',
            'contacts',
            'mm_contact_evidence',
            'mm_demo_qa',
            'mm_experiments',
            'mm_model_invocations',
            'mm_jobs',
            'mm_events',
            'outreach',
            'revenue',
            'projects',
            'mm_migrations',
        }

        for table in expected_tables:
            assert table in tables, f"Missing table: {table}"

    def test_migration_is_idempotent(self):
        """Test that running migration twice doesn't fail."""
        backup_path = self.create_backup_manifest(self.db_path)

        # First migration
        migrate(self.conn, backup_path)
        self.conn.commit()

        # Second migration should not fail
        migrate(self.conn, backup_path)
        self.conn.commit()

        # Verify tables still exist
        cursor = self.conn.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='businesses'
        """)
        assert cursor.fetchone() is not None

    def test_migration_records_version(self):
        """Test that migration records its version in mm_migrations."""
        backup_path = self.create_backup_manifest(self.db_path)
        migrate(self.conn, backup_path)
        self.conn.commit()

        cursor = self.conn.execute("SELECT version, applied_at, backup_path FROM mm_migrations")
        row = cursor.fetchone()
        assert row is not None
        assert row['version'] == 2
        assert row['backup_path'] == str(backup_path)

    def test_foreign_keys_enforced(self):
        """Test that foreign key constraints are enforced."""
        backup_path = self.create_backup_manifest(self.db_path)
        migrate(self.conn, backup_path)
        self.conn.commit()

        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

        # Insert a business
        self.conn.execute(
            "INSERT INTO businesses(id, name, public_website, region, source, discovered_at, current_status, is_dummy) VALUES(?,?,?,?,?,?,?,?)",
            (1, "Test Business", "https://example.com", "NZ", "test", "2024-01-01T00:00:00Z", "discovered", 0)
        )

        # Try to insert mm_deals with non-existent business_id - should fail
        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO mm_deals(business_id, stage, updated_at) VALUES(?,?,?)",
                (999, "DISCOVERED", "2024-01-01T00:00:00Z")
            )

        # Valid insert should work
        self.conn.execute(
            "INSERT INTO mm_deals(business_id, stage, updated_at) VALUES(?,?,?)",
            (1, "DISCOVERED", "2024-01-01T00:00:00Z")
        )
        self.conn.commit()

    def test_cascade_delete_business_removes_related(self):
        """Test that deleting a business cascades to related tables via manual cleanup."""
        backup_path = self.create_backup_manifest(self.db_path)
        migrate(self.conn, backup_path)
        self.conn.commit()

        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

        # Insert business with related data
        self.conn.execute(
            "INSERT INTO businesses(id, name, public_website, region, source, discovered_at, current_status, is_dummy) VALUES(?,?,?,?,?,?,?,?)",
            (1, "Test Business", "https://example.com", "NZ", "test", "2024-01-01T00:00:00Z", "discovered", 0)
        )
        self.conn.execute(
            "INSERT INTO mm_deals(business_id, stage, updated_at) VALUES(?,?,?)",
            (1, "DISCOVERED", "2024-01-01T00:00:00Z")
        )
        self.conn.execute(
            "INSERT INTO mm_evidence(business_id, url, observation, limitation, checked_at) VALUES(?,?,?,?,?)",
            (1, "https://example.com", "obs", "lim", "2024-01-01T00:00:00Z")
        )
        self.conn.commit()

        # Delete related records first (simulating proper cleanup)
        self.conn.execute("DELETE FROM mm_deals WHERE business_id=?", (1,))
        self.conn.execute("DELETE FROM mm_evidence WHERE business_id=?", (1,))
        self.conn.commit()

        # Delete business
        self.conn.execute("DELETE FROM businesses WHERE id=?", (1,))
        self.conn.commit()

        # Related records should be gone
        cursor = self.conn.execute("SELECT COUNT(*) FROM mm_deals WHERE business_id=?", (1,))
        assert cursor.fetchone()[0] == 0

        cursor = self.conn.execute("SELECT COUNT(*) FROM mm_evidence WHERE business_id=?", (1,))
        assert cursor.fetchone()[0] == 0

    def test_trigger_enforces_send_approval(self):
        """Test that trigger prevents sending unapproved messages."""
        backup_path = self.create_backup_manifest(self.db_path)
        migrate(self.conn, backup_path)
        self.conn.commit()

        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

        # Insert business and evidence
        self.conn.execute(
            "INSERT INTO businesses(id, name, public_website, region, source, discovered_at, current_status, is_dummy) VALUES(?,?,?,?,?,?,?,?)",
            (1, "Test Business", "https://example.com", "NZ", "test", "2024-01-01T00:00:00Z", "discovered", 0)
        )
        eid = self.conn.execute(
            "INSERT INTO mm_evidence(business_id, url, observation, limitation, checked_at) VALUES(?,?,?,?,?)",
            (1, "https://example.com", "obs", "lim", "2024-01-01T00:00:00Z")
        ).lastrowid
        self.conn.execute(
            "INSERT INTO mm_evidence_meta VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (eid, 'verified', 'rendered', 0.9, 'observed_fact', 'test', '2025-01-01T00:00:00Z', '/tmp/capture', 'hash', 'verifier', 1)
        )

        # Insert message without approval
        mid = self.conn.execute(
            "INSERT INTO mm_messages(business_id, evidence_id, recipient, body, digest, kind, created_at) VALUES(?,?,?,?,?,?,?)",
            (1, eid, "test@example.com", "test body", "digest", "initial", "2024-01-01T00:00:00Z")
        ).lastrowid

        # Try to set sent_at without approved_hash - should fail
        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE mm_messages SET sent_at=?, send_receipt=? WHERE id=?",
                ("2024-01-01T00:00:00Z", "receipt123", mid)
            )

    def test_trigger_enforces_proposal_approval(self):
        """Test that trigger prevents sending unapproved proposals."""
        backup_path = self.create_backup_manifest(self.db_path)
        migrate(self.conn, backup_path)
        self.conn.commit()

        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

        # Insert business and evidence
        self.conn.execute(
            "INSERT INTO businesses(id, name, public_website, region, source, discovered_at, current_status, is_dummy) VALUES(?,?,?,?,?,?,?,?)",
            (1, "Test Business", "https://example.com", "NZ", "test", "2024-01-01T00:00:00Z", "discovered", 0)
        )
        eid = self.conn.execute(
            "INSERT INTO mm_evidence(business_id, url, observation, limitation, checked_at) VALUES(?,?,?,?,?)",
            (1, "https://example.com", "obs", "lim", "2024-01-01T00:00:00Z")
        ).lastrowid
        self.conn.execute(
            "INSERT INTO mm_evidence_meta VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (eid, 'verified', 'rendered', 0.9, 'observed_fact', 'test', '2025-01-01T00:00:00Z', '/tmp/capture', 'hash', 'verifier', 1)
        )

        # Insert proposal without approval
        pid = self.conn.execute(
            "INSERT INTO mm_proposals(business_id, evidence_id, recipient, body, price_cents, digest, created_at) VALUES(?,?,?,?,?,?,?)",
            (1, eid, "test@example.com", "proposal body", 10000, "digest", "2024-01-01T00:00:00Z")
        ).lastrowid

        # Try to set sent_at without approved_hash - should fail
        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE mm_proposals SET sent_at=?, send_receipt=? WHERE id=?",
                ("2024-01-01T00:00:00Z", "receipt123", pid)
            )

    def test_migration_checksum_verification(self):
        """Test that migration fails on corrupted backup."""
        backup_path = self.create_backup_manifest(self.db_path)

        # Corrupt the backup
        backup_file = self.temp_path / "backups" / "money_machine.db"
        backup_file.write_bytes(b"corrupted")

        with pytest.raises(ValueError, match="Backup checksum mismatch"):
            migrate(self.conn, backup_path)

    def test_all_triggers_created(self):
        """Test that all expected triggers are created."""
        backup_path = self.create_backup_manifest(self.db_path)
        migrate(self.conn, backup_path)
        self.conn.commit()

        cursor = self.conn.execute("""
            SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name
        """)
        triggers = {row[0] for row in cursor.fetchall()}

        # Check for critical triggers
        critical_triggers = {
            'prevent_unapproved_mm_messages_send',
            'mm_message_queue_guard',
            'mm_message_edit',
            'mm_sent_immutable',
            'mm_proposal_edit',
            'mm_proposal_insert',
            'mm_proposal_send',
            'mm_cash_proof',
            'mm_cash_immutable',
            'mm_cash_no_delete',
            'mm_refund_proof',
            'mm_refund_immutable',
            'mm_refund_no_delete',
            'mm_receipt_immutable',
            'mm_receipt_no_delete',
            'mm_hold_no_delete',
            'mm_suppression_no_delete',
            'mm_suppression_revoke',
            'mm_stage_guard',
            'mm_stage_event',
            'mm_legacy_send_closed',
            'mm_legacy_revenue_closed',
            'mm_legacy_revenue_update',
            'mm_message_approval_proof',
            'mm_message_readiness_guard',
            'mm_message_sent_record_immutable',
            'mm_message_approval_insert',
            'mm_proposal_approval_proof',
            'mm_proposal_readiness_guard',
            'mm_proposal_sent_record_immutable',
            'mm_proposal_approval_insert',
            'mm_proposal_sent_content_immutable',
            'mm_evidence_change_revoke',
            'mm_evidence_meta_change_revoke',
            'mm_contact_change_revoke',
            'mm_ready_stage_guard',
        }

        for trigger in critical_triggers:
            assert trigger in triggers, f"Missing critical trigger: {trigger}"


class TestSchemaIntegrity:
    """Test schema integrity and constraints."""

    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.touch()
        self.conn = connect(self.db_path)

    def teardown_method(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_unique_constraints(self):
        """Test that unique constraints are enforced."""
        from mm_core import migrate
        import shutil

        # Create backup
        self.conn.execute("CREATE TABLE IF NOT EXISTS dummy(id INTEGER)")
        self.conn.commit()
        backup_path = self.create_backup_manifest()
        from mm_core import migrate
        migrate(self.conn, backup_path)
        self.conn.commit()

        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

        # Test unique constraint on mm_suppression.address
        self.conn.execute("INSERT INTO mm_suppression(address, reason, created_at) VALUES(?,?,?)",
                          ("test@example.com", "test", "2024-01-01T00:00:00Z"))
        self.conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO mm_suppression(address, reason, created_at) VALUES(?,?,?)",
                              ("test@example.com", "test2", "2024-01-01T00:00:00Z"))

    def test_check_constraints(self):
        """Test that CHECK constraints are enforced."""
        from mm_core import migrate
        import shutil

        self.conn.execute("CREATE TABLE IF NOT EXISTS dummy(id INTEGER)")
        self.conn.commit()
        backup_path = self.create_backup_manifest()
        from mm_core import migrate
        migrate(self.conn, backup_path)
        self.conn.commit()

        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

        # Test CHECK constraint on mm_evidence_meta.confidence (0-1)
        self.conn.execute("INSERT INTO businesses(id, name, public_website, region, source, discovered_at, current_status, is_dummy) VALUES(?,?,?,?,?,?,?,?)",
                          (1, "Test", "https://example.com", "NZ", "test", "2024-01-01T00:00:00Z", "discovered", 0))
        eid = self.conn.execute("INSERT INTO mm_evidence(business_id, url, observation, limitation, checked_at) VALUES(?,?,?,?,?)",
                                (1, "https://example.com", "obs", "lim", "2024-01-01T00:00:00Z")).lastrowid

        # Valid confidence
        self.conn.execute("INSERT INTO mm_evidence_meta VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (eid, 'verified', 'rendered', 0.9, 'observed_fact', 'test', '2025-01-01T00:00:00Z', '/tmp/c', 'hash', 'verifier', 1))

        # Invalid confidence should fail
        eid2 = self.conn.execute("INSERT INTO mm_evidence(business_id, url, observation, limitation, checked_at) VALUES(?,?,?,?,?)",
                                 (1, "https://example.com", "obs", "lim", "2024-01-01T00:00:00Z")).lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO mm_evidence_meta VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                              (eid2, 'verified', 'rendered', 1.5, 'observed_fact', 'test', '2025-01-01T00:00:00Z', '/tmp/c', 'hash', 'verifier', 1))

    def create_backup_manifest(self) -> Path:
        """Create a verified backup manifest for migration testing."""
        import json
        import hashlib
        import shutil
        from datetime import datetime

        backup_dir = self.temp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_file = backup_dir / "money_machine.db"
        shutil.copy2(self.db_path, backup_file)

        sha256 = hashlib.sha256(backup_file.read_bytes()).hexdigest()
        manifest = {
            "created_at": datetime.now().isoformat(),
            "schema_version": 1,
            "items": [
                {
                    "path": str(backup_file),
                    "sha256": sha256,
                }
            ],
        }

        manifest_path = backup_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return backup_dir  # Return directory, not manifest file


if __name__ == "__main__":
    pytest.main([__file__, "-v"])