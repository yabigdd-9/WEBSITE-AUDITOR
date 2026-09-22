"""P1 tests: test-fixture quarantine and dead-letter resolution.

All fixtures are synthetic and disposable. No network, no model calls, no sends.
"""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

import mm_core as c
import mm_pipeline as p


def fresh_db(tmp):
    # Operator commands open the canonical MM_ROOT database path.
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
    """)
    p.migrate(d)
    c.ensure_business_columns(d)
    d.commit()
    return d


def add_business(d, name, source, site='https://fixture.example.co.nz'):
    return d.execute(
        "INSERT INTO businesses(name,public_website,source,discovered_at,"
        "current_status,is_dummy) VALUES(?,?,?,?,'discovered',0)",
        (name, site, source, c.now()),
    ).lastrowid


class Quarantine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['MM_ROOT'] = self.tmp.name
        (Path(self.tmp.name) / 'state').mkdir(parents=True, exist_ok=True)
        self.d = fresh_db(self.tmp.name)
        import mm_operator
        self.op = mm_operator

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()
        os.environ.pop('MM_ROOT', None)

    def test_quarantine_excludes_from_queue_and_metrics(self):
        bid = add_business(self.d, 'Fixture Co', 'test_import')
        p.enqueue(self.d, bid)
        self.d.commit()

        result = self.op.cmd_data_quarantine('test_import')

        self.assertEqual(result['quarantined'], 1)
        row = self.d.execute(
            "SELECT is_dummy, suppression_reason FROM businesses WHERE id=?",
            (bid,),
        ).fetchone()
        self.assertEqual(row['is_dummy'], 1)
        self.assertEqual(row['suppression_reason'], 'test_fixture')
        # excluded from the production work queue
        self.assertEqual(p.item(self.d, bid)['state'], 'SUPPRESSED')
        # excluded from business metrics (real prospects count only is_dummy=0)
        real = self.d.execute(
            "SELECT count(*) FROM businesses WHERE is_dummy=0").fetchone()[0]
        self.assertEqual(real, 0)
        # suppression recorded in the append-only event trail
        ev = self.d.execute(
            "SELECT actor, reason, to_state FROM pipeline_events "
            "WHERE business_id=? ORDER BY id DESC LIMIT 1", (bid,)).fetchone()
        self.assertEqual(ev['actor'], 'mm-data-quarantine')
        self.assertEqual(ev['reason'], 'test_fixture')
        self.assertEqual(ev['to_state'], 'SUPPRESSED')

    def test_quarantine_idempotent(self):
        bid = add_business(self.d, 'Fixture Co', 'test_import')
        self.d.commit()
        first = self.op.cmd_data_quarantine('test_import')
        events_after_first = self.d.execute(
            "SELECT count(*) FROM pipeline_events WHERE business_id=?",
            (bid,)).fetchone()[0]
        second = self.op.cmd_data_quarantine('test_import')
        events_after_second = self.d.execute(
            "SELECT count(*) FROM pipeline_events WHERE business_id=?",
            (bid,)).fetchone()[0]
        self.assertEqual(first['quarantined'], 1)
        self.assertEqual(second['quarantined'], 0)
        self.assertEqual(second['already_quarantined'], 1)
        self.assertEqual(events_after_first, events_after_second)

    def test_quarantine_never_deletes_rows(self):
        bid = add_business(self.d, 'Fixture Co', 'test_import')
        keep = add_business(self.d, 'Real Co', 'search',
                            site='https://real.example.co.nz')
        self.d.commit()
        self.op.cmd_data_quarantine('test_import')
        self.assertIsNotNone(self.d.execute(
            "SELECT 1 FROM businesses WHERE id=?", (bid,)).fetchone())
        real = self.d.execute(
            "SELECT is_dummy, suppression_reason FROM businesses WHERE id=?",
            (keep,)).fetchone()
        self.assertEqual(real['is_dummy'], 0)
        self.assertIsNone(real['suppression_reason'])

    def test_dead_letter_resolve_records_reason(self):
        bid = add_business(self.d, 'Fixture Co', 'test_import')
        self.d.execute("UPDATE businesses SET is_dummy=1 WHERE id=?", (bid,))
        p.enqueue(self.d, bid)
        p.transition(self.d, bid, 'RETRYABLE_FAILURE', 'w-test', 'boom')
        self.d.commit()

        result = self.op.cmd_dead_letter_resolve('test_fixture')

        self.assertEqual(result['resolved'], 1)
        self.assertEqual(result['deleted'], 0)
        self.assertEqual(p.item(self.d, bid)['state'], 'SUPPRESSED')
        ev = self.d.execute(
            "SELECT actor, reason, from_state, to_state, event_at FROM "
            "pipeline_events WHERE business_id=? AND actor='mm-dead-letter-resolve'",
            (bid,)).fetchone()
        self.assertIsNotNone(ev)
        self.assertEqual(ev['reason'], 'test_fixture')
        self.assertEqual(ev['from_state'], 'RETRYABLE_FAILURE')
        self.assertEqual(ev['to_state'], 'SUPPRESSED')
        self.assertTrue(ev['event_at'])
        # row preserved, attempts history intact
        self.assertIsNotNone(self.d.execute(
            "SELECT 1 FROM businesses WHERE id=?", (bid,)).fetchone())


if __name__ == '__main__':
    unittest.main()
