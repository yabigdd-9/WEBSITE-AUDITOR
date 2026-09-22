"""P6 tests: daily report, funnel metrics, alert rules, jsonl retention, and
the fail-closed negative proof that outreach send is impossible.

All fixtures synthetic/disposable. No network, no model calls, no sends.
"""
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import mm_core as c
import mm_reporting as r
import mm_transport as transport


def fresh_db(tmp):
    db_dir = Path(tmp) / 'database'
    db_dir.mkdir(parents=True, exist_ok=True)
    path = db_dir / 'money_machine.db'
    sqlite3.connect(path).close()
    d = c.connect(path)
    d.executescript("""
    CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY, name TEXT,
        public_website TEXT, region TEXT, source TEXT, discovered_at TEXT,
        current_status TEXT, is_dummy INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS mm_events(event_at TEXT, action TEXT,
        business_id INTEGER, detail TEXT);
    CREATE TABLE IF NOT EXISTS mm_evidence(id INTEGER PRIMARY KEY,
        business_id INTEGER, url TEXT, observation TEXT, limitation TEXT,
        checked_at TEXT);
    CREATE TABLE IF NOT EXISTS mm_messages(id INTEGER PRIMARY KEY,
        business_id INTEGER, kind TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS mm_deals(business_id INTEGER, stage TEXT,
        updated_at TEXT);
    CREATE TABLE IF NOT EXISTS pipeline_items(id INTEGER PRIMARY KEY,
        business_id INTEGER, state TEXT);
    """)
    d.commit()
    return d


class ReportingBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['MM_ROOT'] = self.tmp.name
        (Path(self.tmp.name) / 'state').mkdir(parents=True, exist_ok=True)
        self.d = fresh_db(self.tmp.name)
        self.bid = self.d.execute(
            "INSERT INTO businesses(name,public_website,source,discovered_at,"
            "current_status,is_dummy) VALUES('Fixture','https://fixture.example.co.nz',"
            "'fixture',?,'discovered',0)", (c.now(),)).lastrowid
        self.d.execute("INSERT INTO mm_deals VALUES(?,'DISCOVERED',?)", (self.bid, c.now()))
        self.d.execute("INSERT INTO mm_evidence(business_id,url,observation,limitation,checked_at)"
                       " VALUES(?,?,?,?,?)", (self.bid, 'https://fixture.example.co.nz',
                                              'obs', 'test', c.now()))
        self.d.commit()

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()
        os.environ.pop('MM_ROOT', None)


class DailyReport(ReportingBase):
    def test_daily_report_contains_safety_attestation(self):
        result = r.daily_report()
        text = (Path(self.tmp.name) / 'reports' / Path(result['report']).name).read_text()
        self.assertIn('external_sends: 0', text)
        self.assertIn('model_calls: 0', text)
        self.assertIn('model_cost_usd: 0.0', text)
        self.assertIn('Nothing was sent', text)

    def test_daily_report_funnel_delta_on_second_run(self):
        r.daily_report(quiet=True)
        self.d.execute("UPDATE mm_deals SET stage='AUDITED' WHERE business_id=?", (self.bid,))
        self.d.commit()
        result = r.daily_report(quiet=True)
        self.assertEqual(result['delta'].get('AUDITED'), 1)
        self.assertEqual(result['delta'].get('DISCOVERED'), -1)


class FunnelMetrics(ReportingBase):
    def test_funnel_counts_per_stage(self):
        self.d.execute("INSERT INTO mm_deals VALUES(?,'AUDITED',?)", (self.bid + 1000, c.now()))
        self.d.commit()
        doc = r.daily_report(quiet=True)
        self.assertEqual(doc['funnel']['stages'].get('DISCOVERED'), 1)
        self.assertEqual(doc['funnel']['stages'].get('AUDITED'), 1)
        self.assertEqual(doc['funnel']['counts']['new_evidence_24h'], 1)


class AlertRules(ReportingBase):
    def test_alert_rules_evaluate(self):
        rules_path = Path(self.tmp.name) / 'state' / 'alert-rules.yaml'
        rules_path.write_text('# typed thresholds\ndead_lettered_growth_per_hour_max: 0\n'
                              'disk_free_mb_min: 999999999\nheartbeat_age_seconds_max: 0\n')
        doc = r.evaluate_alerts()
        self.assertEqual(doc['rules_source'], 'state/alert-rules.yaml')
        rules_triggered = {a['rule'] for a in doc['alerts']}
        self.assertIn('disk_free_mb_min', rules_triggered)
        # heartbeat absent in this temp root -> no heartbeat alert, no crash
        self.assertNotIn('heartbeat_age_seconds_max', rules_triggered)
        # stale heartbeat (mtime 10 min old) triggers the rule
        hb = Path(self.tmp.name) / 'state' / 'supervisor.heartbeat'
        hb.write_text('x')
        os.utime(hb, (time.time() - 600, time.time() - 600))
        doc = r.evaluate_alerts()
        self.assertIn('heartbeat_age_seconds_max', {a['rule'] for a in doc['alerts']})

    def test_health_surfaces_alerts(self):
        import mm_observability
        health = mm_observability.health()
        self.assertIn('alerts', health)
        self.assertIsInstance(health['alerts'], list)


class Retention(ReportingBase):
    def test_errors_jsonl_rotates(self):
        errors = Path(self.tmp.name) / 'state' / 'errors.jsonl'
        errors.write_text('{"kind":"failure"}\n')
        old = time.time() - 40 * 86400
        os.utime(errors, (old, old))
        dest = r.rotate_jsonl('errors.jsonl', retention_days=30)
        self.assertTrue(dest and dest.endswith('.gz'))
        self.assertFalse(errors.exists())
        import gzip
        with gzip.open(dest) as f:
            self.assertIn(b'failure', f.read())

    def test_recent_jsonl_not_rotated(self):
        errors = Path(self.tmp.name) / 'state' / 'errors.jsonl'
        errors.write_text('{"kind":"failure"}\n')
        self.assertIsNone(r.rotate_jsonl('errors.jsonl', retention_days=30))
        self.assertTrue(errors.exists())


class SendImpossible(ReportingBase):
    def test_send_impossible_when_fail_closed(self):
        status = transport.status()
        self.assertEqual(status['provider'], 'none')
        self.assertFalse(status['enabled'])
        self.assertFalse(status['external_send_allowed'])
        self.assertEqual(status['daily_cap'], 0)
        self.assertFalse(status['network_send_implementation'])
        # Tampering with the config fails closed, never partially enables.
        bad = Path(self.tmp.name) / 'transport.json'
        doc = json.loads((Path(transport.__file__).parent / 'config' / 'transport.json').read_text())
        doc['daily_cap'] = 5
        bad.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, 'daily_cap'):
            transport.load_config(bad)


if __name__ == '__main__':
    unittest.main()
