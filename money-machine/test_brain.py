import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import mm_brain
import mm_core as core


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MM_ROOT"] = self.tmp.name
        Path(self.tmp.name, "database").mkdir()
        self.db = Path(self.tmp.name, "database", "money_machine.db")
        d = sqlite3.connect(self.db)
        d.executescript("""
            CREATE TABLE businesses(id INTEGER PRIMARY KEY, name TEXT, is_dummy INTEGER DEFAULT 0,
                canonical_host TEXT, normalized_name TEXT, region TEXT, suppression_reason TEXT);
            CREATE TABLE mm_deals(business_id INTEGER, stage TEXT, updated_at TEXT);
            CREATE TABLE pipeline_items(business_id INTEGER PRIMARY KEY, state TEXT, attempts INTEGER,
                updated_at TEXT);
            CREATE TABLE mm_contact_evidence(id INTEGER PRIMARY KEY, confidence REAL,
                capture_path TEXT, capture_hash TEXT);
        """)
        d.execute("INSERT INTO businesses VALUES (1,'Real',0,'real.co.nz','real','Canterbury',NULL)")
        d.execute("INSERT INTO mm_deals VALUES (1,'AUDITED','now')")
        d.execute("INSERT INTO pipeline_items VALUES (1,'AUDITED',0,'now')")
        d.commit(); d.close()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("MM_ROOT", None)

    def _connect(self):
        return core.connect(self.db, readonly=True)

    def test_brain_prioritises_bottleneck_and_is_safe(self):
        with self._connect() as d:
            result = mm_brain.recommend(d)
        self.assertEqual(result["primary_bottleneck"]["primary"], "AUDITED")
        self.assertEqual(result["highest_priority_action"]["action"], "refresh_evidence")
        self.assertEqual(result["safety"]["external_sends"], 0)
        self.assertTrue(result["safe_to_execute"])

    def test_do_nothing_empty_queue(self):
        d = core.connect(self.db)
        d.execute("DELETE FROM pipeline_items"); d.execute("DELETE FROM mm_deals"); d.commit(); d.close()
        with self._connect() as d:
            result = mm_brain.recommend(d)
        self.assertEqual(result["highest_priority_action"]["action"], "NONE")

    def test_ledger_idempotency_replay_and_safe_mode(self):
        row = mm_brain.decision("refresh_evidence", 1, "audit is stale", "AUDITED", "AUDITED", confidence=.8)
        self.assertEqual(mm_brain.replay(row["decision_id"])["match"], True)
        first = mm_brain.idempotency("business:1:audit:v1", "audit", 1)
        second = mm_brain.idempotency("business:1:audit:v1", "audit", 1)
        self.assertEqual(first["status"], "SUCCESS")
        self.assertEqual(second["status"], "SKIP_ALREADY_COMPLETE")
        self.assertTrue(mm_brain.safe_mode(True)["enabled"])
        self.assertTrue(mm_brain.safe_mode()["enabled"])

    def test_db_check(self):
        with self._connect() as d:
            result = mm_brain.db_check(d)
        self.assertTrue(result["ok"])

    def test_funnel_exposes_rich_metrics(self):
        with self._connect() as d:
            metrics = mm_brain.funnel(d)
        self.assertEqual(metrics["AUDITED"]["current_count"], 1)
        self.assertIn("entered_24h", metrics["AUDITED"])
        self.assertIn("failure_rate", metrics["AUDITED"])
        self.assertIn("average_processing_time_seconds", metrics["AUDITED"])

    def test_golden_scenarios(self):
        scenarios = mm_brain.golden_scenarios()
        self.assertGreaterEqual(len(scenarios), 7)
        for scenario in scenarios:
            result = mm_brain.evaluate_scenario(scenario)
            self.assertEqual(result["action"], scenario["expected_action"], scenario["name"])
            self.assertEqual(result["external_sends"], 0)
            self.assertEqual(result["paid_calls"], 0)


if __name__ == "__main__":
    unittest.main()
