"""Offline tests: locked connector metadata and read-only live-preflight guard."""
import unittest
from pathlib import Path

from scripts.supabase_connection_preflight import verify_status, safe_failure_category


def permitted():
    return (
        "mm_pipeline_connector", True, False, False, False, False, False,
        True, True, True, True, False, True,
    )


class TestConnectorPreflight(unittest.TestCase):
    def test_secret_safe_failure_categories(self):
        OperationalError = type("OperationalError", (Exception,), {"__module__": "psycopg.errors"})
        self.assertEqual(safe_failure_category(KeyError("SECRET_VALUE")), "MISSING_CONFIGURATION")
        self.assertEqual(safe_failure_category(ValueError("postgresql://secret")), "CONFIGURATION_OR_POLICY")
        self.assertEqual(safe_failure_category(OperationalError("password=secret")), "DATABASE_CONNECTION")
        self.assertEqual(safe_failure_category(RuntimeError("token=secret")), "UNCLASSIFIED")

    def test_minimum_privileges_with_rls_are_accepted(self):
        result = verify_status(permitted(), (0, 0))
        self.assertEqual(result["read_only_preflight"], "PASS")
        self.assertEqual(result["writes_performed"], 0)
        self.assertFalse(result["worker_switched"])
        self.assertEqual(result["saved_revisions"], 0)

    def test_admin_or_nonlogin_connector_is_rejected(self):
        for index, value in ((0, "postgres"), (1, False), (2, True),
                             (3, True), (4, True), (5, True), (6, True),
                             (11, True)):
            with self.subTest(index=index):
                row = list(permitted())
                row[index] = value
                with self.assertRaises(ValueError):
                    verify_status(tuple(row), (0, 0))

    def test_missing_grants_or_rls_block_connection(self):
        for index in (7, 8, 9, 10, 12):
            row = list(permitted())
            row[index] = False
            with self.subTest(index=index), self.assertRaises(ValueError):
                verify_status(tuple(row), (0, 0))

    def test_unexpected_persisted_state_is_rejected(self):
        for counts in ((2, 0), (0, 25), (-1, 0), (0, 1.0), ("1", 0)):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                verify_status(permitted(), counts)

    def test_migration_does_not_install_password_or_enable_login(self):
        sql = (Path(__file__).resolve().parents[1] /
               "deploy/postgres/002_locked_connector_role.sql").read_text()
        self.assertIn("NOLOGIN NOSUPERUSER", sql)
        self.assertIn("GRANT mm_checkpoint_writer TO mm_pipeline_connector", sql)
        self.assertNotIn("PASSWORD '", sql)
        self.assertNotIn("ALTER ROLE mm_pipeline_connector LOGIN", sql)


if __name__ == "__main__":
    unittest.main()
