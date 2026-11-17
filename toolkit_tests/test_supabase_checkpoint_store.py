"""No-network tests for the optional encrypted PostgreSQL checkpoint mirror."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from scripts.supabase_checkpoint_store import (
    MAX_BLOB_BYTES,
    SealedCheckpointStore,
    _private_output,
    validate_supabase_dsn,
    verify_encrypted_checkpoint,
)

if importlib.util.find_spec("cryptography") is not None:
    from cryptography.fernet import Fernet
else:
    Fernet = None

HAS_PSYCOPG = importlib.util.find_spec("psycopg") is not None


def sealed(key: bytes, *, event_count: int = 0) -> bytes:
    value = {
        "schema_version": 1,
        "prospects": {},
        "events": [
            {
                "timestamp_utc": "2026-11-18T00:00:00+00:00",
                "run_id": "fixture",
                "entity_id": "0" * 64,
                "action": "approval_config",
                "status": "disabled",
                "sanitized_error": "none",
            }
            for _ in range(event_count)
        ],
    }
    return Fernet(key).encrypt(json.dumps(value).encode())


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, parameters):
        state = self.connection.working
        if sql.startswith("SELECT pg_advisory_xact_lock"):
            self._row = (None,)
        elif sql.startswith("SELECT revision FROM mm_internal.encrypted_checkpoints"):
            self._row = (state["current"][0],) if state["current"] else None
        elif sql.startswith("SELECT revision,ciphertext,sha256"):
            self._row = state["current"]
        elif sql.startswith("INSERT INTO mm_internal.encrypted_checkpoint_history"):
            revision, blob, digest = parameters
            if revision in state["history"]:
                raise ValueError("Duplicate revision")
            state["history"][revision] = (blob, digest)
        elif sql.startswith("INSERT INTO mm_internal.encrypted_checkpoints"):
            _, revision, blob, digest = parameters
            if state["current"] is not None:
                raise ValueError("Current checkpoint already exists")
            state["current"] = (revision, blob, digest)
        elif sql.startswith("UPDATE mm_internal.encrypted_checkpoints"):
            if self.connection.fail_update:
                raise OSError("Simulated failure after history insertion")
            revision, blob, digest, _, old = parameters
            if state["current"][0] != old:
                raise ValueError("CAS mismatch")
            state["current"] = (revision, blob, digest)
        else:
            raise AssertionError(f"Unexpected SQL: {sql!r}")

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self, database):
        self.database = database
        self.working = None
        self.fail_update = database.fail_update

    def __enter__(self):
        self.working = copy.deepcopy(self.database.state)
        return self

    def __exit__(self, error_class, *_):
        if error_class is None:
            self.database.state = self.working
        return False

    def cursor(self):
        return FakeCursor(self)


class FakeDatabase:
    def __init__(self):
        self.state = {"current": None, "history": {}}
        self.fail_update = False

    def connect(self):
        return FakeConnection(self)


@unittest.skipUnless(Fernet is not None, "optional cryptography dependency not installed")
class TestCheckpointStore(unittest.TestCase):
    def setUp(self):
        self.key = Fernet.generate_key()
        self.db = FakeDatabase()
        self.store = SealedCheckpointStore(self.db.connect)

    def test_initial_import_is_sealed_and_records_history(self):
        blob = sealed(self.key)
        self.assertEqual(self.store.put(blob, self.key.decode(), expected_revision=0), 1)
        version, current = self.store.read(self.key.decode())
        self.assertEqual((version, current), (1, blob))
        self.assertEqual(self.db.state["history"][1][0], blob)
        self.assertEqual(self.db.state["history"][1][1], hashlib.sha256(blob).hexdigest())
        self.assertNotIn(b"prospects", repr(self.db.state).encode())

    def test_compare_and_swap_cannot_silently_replace_checkpoint(self):
        self.store.put(sealed(self.key), self.key.decode(), expected_revision=0)
        original = copy.deepcopy(self.db.state)
        with self.assertRaisesRegex(ValueError, "revision conflict"):
            self.store.put(sealed(self.key, event_count=1), self.key.decode(), expected_revision=0)
        self.assertEqual(self.db.state, original)
        next_blob = sealed(self.key, event_count=1)
        self.assertEqual(self.store.put(next_blob, self.key.decode(), expected_revision=1), 2)
        self.assertEqual(len(self.db.state["history"]), 2)
        self.assertEqual(self.store.read(self.key.decode()), (2, next_blob))

    def test_transactional_rollback_does_not_leave_orphan_history(self):
        self.store.put(sealed(self.key), self.key.decode(), expected_revision=0)
        before = copy.deepcopy(self.db.state)
        self.db.fail_update = True
        with self.assertRaisesRegex(OSError, "Simulated failure"):
            self.store.put(sealed(self.key, event_count=2), self.key.decode(), expected_revision=1)
        self.assertEqual(self.db.state, before)

    def test_no_checkpoint_is_not_implicit_bootstrap(self):
        with self.assertRaisesRegex(ValueError, "No saved checkpoint"):
            self.store.read(self.key.decode())

    def test_corrupted_ciphertext_and_wrong_key_fail(self):
        data = sealed(self.key)
        with self.assertRaises(Exception):
            verify_encrypted_checkpoint(data, Fernet.generate_key().decode())
        self.store.put(data, self.key.decode(), expected_revision=0)
        self.db.state["current"] = (1, data + b"x", hashlib.sha256(data).hexdigest())
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.store.read(self.key.decode())

    def test_invalid_input_does_not_create_version(self):
        for blob in (b"plaintext", b"A" * (MAX_BLOB_BYTES + 1)):
            with self.assertRaises(Exception):
                self.store.put(blob, self.key.decode(), expected_revision=0)
        self.assertIsNone(self.db.state["current"])
        for version in (-1, True, 200):
            with self.assertRaises(ValueError):
                self.store.put(sealed(self.key), self.key.decode(), expected_revision=version)

    def test_owner_download_file_rejects_overwrite_and_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sealed.bin"
            data = sealed(self.key)
            _private_output(path, data)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            with self.assertRaises(FileExistsError):
                _private_output(path, data)


@unittest.skipUnless(HAS_PSYCOPG, "optional psycopg dependency not installed")
class TestConnectionPolicy(unittest.TestCase):
    REF = "srymerkhraklwuttzexi"

    def test_direct_supabase_requires_dedicated_login_and_verified_tls(self):
        good = (
            f"host=db.{self.REF}.supabase.co dbname=postgres user=mm_pipeline "
            "password=placeholder sslmode=verify-full"
        )
        validate_supabase_dsn(good, expected_ref=self.REF)
        for changed in (
            good.replace("verify-full", "require"),
            good.replace(f"db.{self.REF}.supabase.co", "evil.example"),
            good.replace("user=mm_pipeline", "user=postgres"),
            good + " hostaddr=127.0.0.1",
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_supabase_dsn(changed, expected_ref=self.REF)

    def test_pooler_must_reference_the_same_project(self):
        valid = (
            f"host=aws-0-ap-southeast-2.pooler.supabase.com "
            f"user=mm_pipeline.{self.REF} sslmode=verify-full"
        )
        validate_supabase_dsn(valid, expected_ref=self.REF)
        with self.assertRaises(ValueError):
            validate_supabase_dsn(
                valid.replace(self.REF, "wrongprojectref0000"), expected_ref=self.REF
            )


class TestMigrationPolicy(unittest.TestCase):
    def test_schema_is_private_and_no_plaintext_columns(self):
        root = Path(__file__).resolve().parents[1]
        schema = (root / "deploy/postgres/001_encrypted_checkpoints.sql").read_text()
        self.assertIn("CREATE SCHEMA IF NOT EXISTS mm_internal", schema)
        self.assertIn("REVOKE ALL ON SCHEMA mm_internal FROM anon, authenticated, service_role", schema)
        self.assertIn("ENABLE ROW LEVEL SECURITY", schema)
        self.assertIn("NOLOGIN", schema)
        self.assertIn("mm_checkpoint_writer", schema)
        self.assertIn("ciphertext bytea NOT NULL", schema)
        self.assertNotIn("email text", schema)
        self.assertNotIn("plaintext text", schema)


if __name__ == "__main__":
    unittest.main()
