"""P3 tests: error fingerprinting, dedupe counters, and typed error fencing.

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
    db_dir = Path(tmp) / 'database'
    db_dir.mkdir(parents=True, exist_ok=True)
    path = db_dir / 'money_machine.db'
    sqlite3.connect(path).close()
    d = c.connect(path)
    d.executescript("""
    CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY, name TEXT,
        public_website TEXT, region TEXT, source TEXT, discovered_at TEXT,
        current_status TEXT, is_dummy INTEGER DEFAULT 0);
    """)
    p.migrate(d)
    d.commit()
    return d


class ErrorTracking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['MM_ROOT'] = self.tmp.name
        (Path(self.tmp.name) / 'state').mkdir(parents=True, exist_ok=True)
        self.d = fresh_db(self.tmp.name)
        self.bid = self.d.execute(
            "INSERT INTO businesses(name,discovered_at) VALUES('Fixture Co',?)",
            (c.now(),)).lastrowid
        p.enqueue(self.d, self.bid)
        self.d.commit()

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()
        os.environ.pop('MM_ROOT', None)

    def test_error_fingerprint_stable(self):
        e1 = ValueError('business 12345 failed at 2026-09-22T10:11:12')
        e2 = ValueError('business 98765 failed at 2026-09-22T23:59:59')
        self.assertEqual(p.error_fingerprint(e1, 'w1'),
                         p.error_fingerprint(e2, 'w1'))
        self.assertNotEqual(p.error_fingerprint(e1, 'w1'),
                            p.error_fingerprint(e1, 'w2'))
        self.assertNotEqual(p.error_fingerprint(ValueError('a'), 'w1'),
                            p.error_fingerprint(KeyError('a'), 'w1'))

    def test_repeated_errors_dedupe_with_counter(self):
        err = p.RetryableError('database locked at host 12345')
        p.fail(self.d, self.bid, 'w-test', err)
        p.fail(self.d, self.bid, 'w-test', err)
        self.d.commit()
        row = p.item(self.d, self.bid)
        self.assertEqual(row['repeat_count'], 2)
        self.assertTrue(row['error_fingerprint'])
        self.assertEqual(row['classification'], 'transient')
        self.assertTrue(row['first_seen'])
        self.assertTrue(row['last_seen'])
        self.assertEqual(row['component'], 'w-test')
        # third occurrence of a *different* error keeps its own counter chain
        p.fail(self.d, self.bid, 'w-test', p.RetryableError('other failure'))
        self.d.commit()
        row = p.item(self.d, self.bid)
        self.assertEqual(row['repeat_count'], 3)
        self.assertNotEqual(row['error_fingerprint'],
                            p.error_fingerprint(err, 'w-test'))

    def test_contract_bug_is_permanent_not_endless_retry(self):
        def row_get_handler(d, it, w):
            # the sqlite3.Row.get bug class: AttributeError inside a handler
            return it['payload'].get('missing')
        w = p.Worker('w-contract', ('DISCOVERED',), row_get_handler)
        w.run_once(self.d)
        self.d.commit()
        row = p.item(self.d, self.bid)
        self.assertEqual(row['state'], 'PERMANENT_FAILURE')
        self.assertEqual(row['classification'], 'permanent')
        self.assertEqual(row['component'], 'w-contract')
        # transition clears last_error; the dead-letter event keeps the detail
        ev = self.d.execute(
            "SELECT reason FROM pipeline_events WHERE business_id=? "
            "AND to_state='PERMANENT_FAILURE'", (self.bid,)).fetchone()
        self.assertIn('contract error', ev['reason'])

    def test_schema_error_is_permanent(self):
        def missing_table_handler(d, it, w):
            d.execute('SELECT 1 FROM mm_demo_qa').fetchall()
            return ('DISCOVERED', 'noop', None)
        w = p.Worker('w-schema', ('DISCOVERED',), missing_table_handler)
        w.run_once(self.d)
        self.d.commit()
        row = p.item(self.d, self.bid)
        self.assertEqual(row['state'], 'PERMANENT_FAILURE')
        self.assertEqual(row['classification'], 'permanent')
        ev = self.d.execute(
            "SELECT reason FROM pipeline_events WHERE business_id=? "
            "AND to_state='PERMANENT_FAILURE'", (self.bid,)).fetchone()
        self.assertIn('database error', ev['reason'])

    def test_root_causes_surface(self):
        import mm_observability
        p.fail(self.d, self.bid, 'w-test', p.PermanentError('hard failure 12345'))
        self.d.commit()
        result = mm_observability.errors(show_root_causes=True)
        self.assertEqual(result['count'], 1)
        rc = result['root_causes'][0]
        self.assertEqual(rc['business_id'], self.bid)
        self.assertEqual(rc['classification'], 'permanent')
        self.assertTrue(rc['error_fingerprint'])
        self.assertEqual(rc['repeat_count'], 1)




class TransientSQLiteClassification(unittest.TestCase):
    """Lock contention must retry with backoff; schema faults stay permanent."""

    def test_locked_database_is_retryable(self):
        ex = p.classify_unexpected(sqlite3.OperationalError('database is locked'))
        self.assertIsInstance(ex, p.RetryableError)

    def test_busy_database_is_retryable(self):
        ex = p.classify_unexpected(sqlite3.OperationalError('database table is busy'))
        self.assertIsInstance(ex, p.RetryableError)

    def test_disk_io_error_is_retryable(self):
        ex = p.classify_unexpected(sqlite3.OperationalError('disk I/O error'))
        self.assertIsInstance(ex, p.RetryableError)

    def test_missing_table_remains_permanent(self):
        ex = p.classify_unexpected(sqlite3.OperationalError('no such table: mm_demo_qa'))
        self.assertIsInstance(ex, p.PermanentError)

    def test_integrity_and_contract_faults_remain_permanent(self):
        self.assertIsInstance(
            p.classify_unexpected(sqlite3.IntegrityError('NOT NULL constraint failed')),
            p.PermanentError)
        self.assertIsInstance(
            p.classify_unexpected(AttributeError("'sqlite3.Row' object has no attribute 'get'")),
            p.PermanentError)

    def test_unknown_fault_is_bounded_retryable_with_context(self):
        ex = p.classify_unexpected(RuntimeError('boom'), 'completion rejected: ')
        self.assertIsInstance(ex, p.RetryableError)
        self.assertIn('completion rejected: ', str(ex))


if __name__ == '__main__':
    unittest.main()
