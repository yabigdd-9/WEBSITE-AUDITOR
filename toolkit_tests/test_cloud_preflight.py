"""Portable tests for the cloud startup safety gate."""
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/cloud/preflight.py"
SPEC = importlib.util.spec_from_file_location("wa_cloud_preflight", SCRIPT)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


class CloudPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mount = Path(self.temp.name)
        self.root = self.mount / "WEBSITE-AUDITOR"
        (self.root / "state").mkdir(parents=True)
        (self.root / "database").mkdir(parents=True)
        self.transport = self.root / "money-machine/config/transport.json"
        self.transport.parent.mkdir(parents=True)
        self.transport.write_text(json.dumps({
            "enabled": False,
            "external_send_allowed": False,
            "daily_cap": 0,
        }))
        self.database = self.root / "database/money_machine.db"
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE businesses (id INTEGER PRIMARY KEY)")

    def validate(self, mounted=True):
        with patch.object(Path, "is_mount", return_value=mounted):
            return PREFLIGHT.validate(self.root, self.mount)

    def test_valid_mounted_db_passes(self):
        self.assertEqual(self.validate(), [])

    def test_unmounted_disk_fails(self):
        self.assertTrue(any("not mounted" in x for x in self.validate(mounted=False)))

    def test_missing_database_fails_without_creating_one(self):
        self.database.unlink()
        self.assertTrue(any("Nonempty restored" in x for x in self.validate()))
        self.assertFalse(self.database.exists())

    def test_corrupt_database_fails(self):
        self.database.write_bytes(b"not a SQLite database")
        self.assertTrue(any("SQLite" in x for x in self.validate()))

    def test_missing_business_schema_fails(self):
        self.database.unlink()
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE other (id INTEGER)")
        self.assertTrue(any("businesses table" in x for x in self.validate()))

    def test_enabled_mail_transport_fails(self):
        self.transport.write_text(json.dumps({
            "enabled": True,
            "external_send_allowed": True,
            "daily_cap": 10,
        }))
        self.assertTrue(any("Mail transport" in x for x in self.validate()))

    def test_missing_policy_fails(self):
        self.transport.unlink()
        self.assertTrue(any("policy missing" in x for x in self.validate()))

    def test_root_outside_mount_fails(self):
        with patch.object(Path, "is_mount", return_value=True):
            errors = PREFLIGHT.validate(self.mount.parent, self.mount)
        self.assertTrue(any("MM_ROOT" in x for x in errors))


if __name__ == "__main__":
    unittest.main()
