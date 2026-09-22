"""P2 tests: intake URL normalization and canonical dedupe.

All fixtures are synthetic and disposable. No network, no model calls, no sends.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import mm_core as c
import mm_pipeline as p
import mm_discovery as discovery


def fresh_db(tmp):
    path = Path(tmp) / 't.db'
    sqlite3.connect(path).close()
    d = c.connect(path)
    d.executescript("""
    CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY, name TEXT,
        public_website TEXT, region TEXT, source TEXT, discovered_at TEXT,
        current_status TEXT, is_dummy INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS mm_events(event_at TEXT, action TEXT,
        business_id INTEGER, detail TEXT);
    CREATE TABLE IF NOT EXISTS mm_evidence(id INTEGER PRIMARY KEY,
        business_id INTEGER REFERENCES businesses(id), note TEXT);
    CREATE TABLE IF NOT EXISTS mm_deals(business_id INTEGER, stage TEXT,
        updated_at TEXT);
    """)
    p.migrate(d)
    c.ensure_business_columns(d)
    d.commit()
    return d


def add_business(d, name, site, region='Canterbury', source='import'):
    return d.execute(
        "INSERT INTO businesses(name,public_website,region,source,discovered_at,"
        "current_status,is_dummy) VALUES(?,?,?,?,?,'discovered',0)",
        (name, site, region, source, c.now()),
    ).lastrowid


class NormalizeIntakeUrl(unittest.TestCase):
    def test_bare_domain_gets_scheme(self):
        self.assertEqual(
            discovery.normalize_intake_url('  KoruPlumbing.co.nz '),
            'https://koruplumbing.co.nz/',
        )
        self.assertEqual(
            discovery.normalize_intake_url('WWW.Fixture.Co.NZ/about#team'),
            'https://fixture.co.nz/about',
        )

    def test_reserved_tld_suppressed_at_intake(self):
        for bad in ('https://alpha.example', 'http://thing.invalid',
                    'https://x.test', 'https://example.com',
                    'https://www.example.net', 'example.org'):
            with self.assertRaises(ValueError, msg=bad):
                discovery.normalize_intake_url(bad)

    def test_normalizer_never_accepts_private_ip(self):
        for bad in ('https://127.0.0.1', 'http://10.0.0.4',
                    'https://192.168.1.10', 'http://169.254.1.1',
                    'https://localhost', 'http://[::1]'):
            with self.assertRaises(ValueError, msg=bad):
                discovery.normalize_intake_url(bad)

    def test_public_url_rejects_garbage(self):
        for bad in ('', 'not a url', 'ftp://fixture.co.nz',
                    'https://user:pw@fixture.co.nz', 'https://fixture.co.nz:8443'):
            with self.assertRaises(ValueError, msg=bad):
                c.public_url(bad)



class Dedupe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()

    def test_dedupe_merges_and_repoints_fks(self):
        survivor = add_business(self.d, 'Alpha', 'https://alpha.example')
        dup = add_business(self.d, '  alpha ', 'https://www.alpha.example/about')
        p.enqueue(self.d, dup)
        ev_id = self.d.execute(
            "INSERT INTO mm_evidence(business_id,note) VALUES(?,'obs')",
            (dup,)).lastrowid
        self.d.commit()

        result = discovery.dedupe_businesses(self.d)
        self.d.commit()

        self.assertEqual(result['merged'], 1)
        self.assertEqual(result['merges'][0]['survivor_id'], survivor)
        self.assertEqual(result['merges'][0]['duplicate_id'], dup)
        self.assertEqual(result['deleted'], 0)
        # FK repointed to survivor
        owner = self.d.execute(
            "SELECT business_id FROM mm_evidence WHERE id=?",
            (ev_id,)).fetchone()[0]
        self.assertEqual(owner, survivor)
        # duplicate retained but suppressed with traceable reason
        row = self.d.execute(
            "SELECT suppression_reason, current_status FROM businesses WHERE id=?",
            (dup,)).fetchone()
        self.assertEqual(row['suppression_reason'], f'duplicate_of:{survivor}')
        self.assertEqual(row['current_status'], 'suppressed')
        self.assertEqual(p.item(self.d, dup)['state'], 'SUPPRESSED')
        # idempotent: second run merges nothing
        again = discovery.dedupe_businesses(self.d)
        self.assertEqual(again['merged'], 0)

    def test_dedupe_rolls_back_on_error(self):
        add_business(self.d, 'Alpha', 'https://alpha.example')
        dup = add_business(self.d, 'Alpha', 'https://www.alpha.example')
        self.d.execute(
            "INSERT INTO mm_evidence(business_id,note) VALUES(?,'obs')", (dup,))
        # RAISE(ABORT) surfaces as OperationalError, not a swallowed unique
        # conflict, and must abort the whole merge
        self.d.execute(
            "CREATE TRIGGER fail_evidence BEFORE UPDATE ON mm_evidence "
            "BEGIN SELECT RAISE(ABORT,'forced failure'); END")
        self.d.commit()

        with self.assertRaises(sqlite3.Error):
            discovery.dedupe_businesses(self.d)
        self.d.rollback()

        row = self.d.execute(
            "SELECT suppression_reason FROM businesses WHERE id=?", (dup,)
        ).fetchone()
        self.assertIsNone(row['suppression_reason'])
        owner = self.d.execute(
            "SELECT 1 FROM mm_evidence WHERE business_id=?", (dup,)).fetchone()
        self.assertIsNotNone(owner)

    def test_reimport_adds_zero_rows(self):
        rows = [
            {'name': 'Alpha', 'website': 'https://alpha.example',
             'region': 'Canterbury'},
            {'name': 'Beta', 'website': 'beta.example', 'region': 'Canterbury'},
        ]
        first = discovery.ingest(self.d, rows)
        self.d.commit()
        self.assertEqual(first['counts']['inserted'], 2)
        second = discovery.ingest(self.d, rows)
        self.d.commit()
        self.assertEqual(second['counts']['inserted'], 0)
        self.assertEqual(second['counts']['duplicates'], 2)
        total = self.d.execute("SELECT count(*) FROM businesses").fetchone()[0]
        self.assertEqual(total, 2)


if __name__ == '__main__':
    unittest.main()
