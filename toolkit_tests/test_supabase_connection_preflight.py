"""Offline tests: locked connector metadata and read-only live-preflight guard."""
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from scripts import supabase_connection_preflight as preflight
from scripts.supabase_connection_preflight import verify_status


def permitted():
    return (
        "mm_pipeline_connector", True, False, False, False, False, False,
        True, True, True, True, False, True,
    )


class TestConnectorPreflight(unittest.TestCase):
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

    def test_failure_stage_never_echoes_driver_error_or_connection_string(self):
        sensitive = "synthetic-secret-that-must-not-appear"
        driver = ModuleType("psycopg")
        driver.connect = Mock(side_effect=RuntimeError(sensitive))
        connection_info = ModuleType("psycopg.conninfo")
        connection_info.conninfo_to_dict = Mock(return_value={"user": preflight.USERNAME})
        modules = {"psycopg": driver, "psycopg.conninfo": connection_info}
        with (
            patch.dict("sys.modules", modules),
            patch("scripts.supabase_checkpoint_store.validate_supabase_dsn"),
        ):
            for project, stage in (
                ("unexpected-project", "configuration"),
                (preflight.PROJECT_REF, "connection"),
            ):
                with self.subTest(stage=stage):
                    output = io.StringIO()
                    with (
                        patch.dict("os.environ", {
                            "WA_SUPABASE_PROJECT_REF": project,
                            "WA_PG_DATABASE_URL": sensitive,
                        }),
                        redirect_stdout(output),
                    ):
                        self.assertEqual(preflight.main(), 2)
                    self.assertEqual(
                        output.getvalue(),
                        f"SUPABASE_PREFLIGHT_BLOCKED: stage={stage}; no writes or worker activation\n",
                    )
                    if stage == "configuration":
                        driver.connect.assert_not_called()
            driver.connect.assert_called_once()

    def test_migration_does_not_install_password_or_enable_login(self):
        sql = (Path(__file__).resolve().parents[1] /
               "deploy/postgres/002_locked_connector_role.sql").read_text()
        self.assertIn("NOLOGIN NOSUPERUSER", sql)
        self.assertIn("GRANT mm_checkpoint_writer TO mm_pipeline_connector", sql)
        self.assertNotIn("PASSWORD '", sql)
        self.assertNotIn("ALTER ROLE mm_pipeline_connector LOGIN", sql)


if __name__ == "__main__":
    unittest.main()
