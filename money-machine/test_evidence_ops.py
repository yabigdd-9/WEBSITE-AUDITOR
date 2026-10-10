"""P5 tests: evidence throughput — audit backfill, own-site contact discovery,
typed BLOCKED_SEARCH_* errors, and the guess-alone-never-verified policy.

All fixtures synthetic/disposable. No network, external sends or model calls, $0.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import mm_core as c
import mm_discovery
import mm_evidence_ops as ops
import mm_email_store as s
import mm_operator


class EvidenceOps(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mm-evidence-ops-')
        self.r = Path(self.temp.name)
        (self.r / 'database').mkdir()
        self.path = self.r / 'database' / 'money_machine.db'
        sqlite3.connect(self.path).close()
        self.env = patch.dict(os.environ, {'MM_ROOT': str(self.r)})
        self.env.start()
        self.d = c.connect(self.path)
        self.d.executescript((Path(__file__).parent / 'database' / 'schema.sql').read_text())
        self.d.commit()
        backup = c.backup(self.r)
        c.migrate(self.d, backup)
        c.ensure_business_columns(self.d)
        s.migrate_email(self.d, backup)
        self.d.execute('CREATE TABLE pipeline_items(business_id INTEGER PRIMARY KEY, state TEXT)')
        self.bid = self._extra_business(site='https://fixture.example.co.nz')
        capture = self.r / 'baseline.txt'
        capture.write_text('Synthetic existing evidence; unverified.')
        c.record_evidence(self.d, self.bid, 'https://fixture.example.co.nz',
                          'Synthetic prior capture', 'Fixture only', capture,
                          'unverified', 'fixture', 0.0)
        self.d.commit()

    def tearDown(self):
        self.d.close()
        self.env.stop()
        self.temp.cleanup()

    @staticmethod
    def _blocked_fetch(url):
        raise ops.OwnSiteBlocked('BLOCKED_SITE_UNREACHABLE', url, 'synthetic failure')

    def backfill(self, **kwargs):
        kwargs.setdefault('fetch', self._blocked_fetch)
        kwargs.setdefault('capture_dir', self.r / 'audit-backfills')
        return ops.audit_backfill(self.d, **kwargs)

    def contacts(self, bid, **kwargs):
        kwargs.setdefault('fetch', self._blocked_fetch)
        kwargs.setdefault('capture_dir', self.r / 'contact-captures')
        return ops.discover_own_site_contacts(self.d, bid, **kwargs)

    def snapshot(self):
        names = ('businesses', 'mm_deals', 'mm_holds', 'pipeline_items',
                 'mm_evidence', 'mm_evidence_meta', 'mm_contact_evidence', 'mm_events',
                 'mm_messages', 'mm_proposals')
        return {name: [tuple(r) for r in self.d.execute('SELECT * FROM ' + name)]
                for name in names}

    def _extra_business(self, site='https://unreachable-fixture.example.co.nz'):
        bid = self.d.execute(
            "INSERT INTO businesses(name,region,public_website,source,discovered_at,"
            "current_status,is_dummy) VALUES('Backfill Fixture','Fixturetown',?,"
            "'fixture',?,'discovered',0)", (site, c.now())).lastrowid
        self.d.execute("INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)",
                       (bid, c.now()))
        self.d.commit()
        return bid

    def late_exclusion_fetch(self, bid, sql, observed):
        def fetch(url):
            with sqlite3.connect(self.path) as other:
                other.execute(sql, (bid,))
            observed['snapshot'] = self.snapshot()
            observed['changes'] = self.d.total_changes
            page = '<a href="mailto:fixture@example.invalid">Contact</a>'
            return page, page.encode(), url
        return fetch

    @staticmethod
    def exclusion_cases():
        return {
            'business_suppression': "UPDATE businesses SET suppression_reason='late opt out' WHERE id=?",
            'business_rejected': "UPDATE businesses SET current_status='rejected' WHERE id=?",
            'pipeline_rejected': "INSERT INTO pipeline_items VALUES(?,'REJECTED')",
            'hold': "INSERT INTO mm_holds(business_id,reason) VALUES(?,'late hold')",
        }


class AuditBackfill(EvidenceOps):
    def test_exclusion_committed_during_fetch_prevents_capture_and_all_writes(self):
        for name, sql in self.exclusion_cases().items():
            for existing_capture in (False, True):
                with self.subTest(reason=name, existing_capture=existing_capture):
                    bid = self._extra_business()
                    capture = self.r / 'audit-backfills' / f'business-{bid}.txt'
                    original = b'Synthetic earlier capture; preserve these bytes.'
                    if existing_capture:
                        capture.parent.mkdir(parents=True, exist_ok=True)
                        capture.write_bytes(original)
                    observed = {}
                    result = self.backfill(
                        ids=[bid], politeness=0,
                        fetch=self.late_exclusion_fetch(bid, sql, observed))
                    self.assertEqual(result['backfilled'], 0)
                    self.assertEqual(result['moved_to_audited'], 0)
                    self.assertEqual([r['id'] for r in result['skipped']], [bid])
                    self.assertEqual(self.snapshot(), observed['snapshot'])
                    self.assertEqual(self.d.total_changes, observed['changes'])
                    self.assertFalse(self.d.in_transaction)
                    if existing_capture:
                        self.assertEqual(capture.read_bytes(), original)
                    else:
                        self.assertFalse(capture.exists())

    def test_successful_backfill_retains_caller_commit_and_rollback_ownership(self):
        bid = self._extra_business()
        before = self.snapshot()
        self.backfill(ids=[bid], politeness=0)
        self.assertTrue(self.d.in_transaction)
        with sqlite3.connect(self.path) as other:
            self.assertEqual(other.execute(
                'SELECT count(*) FROM mm_evidence WHERE business_id=?', (bid,)).fetchone()[0], 0)
        self.d.rollback()
        self.assertEqual(self.snapshot(), before)

    def test_unreachable_outcome_recorded_as_evidence_and_moves_stage(self):
        bid = self._extra_business()
        result = self.backfill(ids=[bid], politeness=0)
        self.assertEqual(result['backfilled'], 1)
        self.assertEqual(result['moved_to_audited'], 1)
        row = result['results'][0]
        self.assertEqual(row['status'], 'unverified')
        self.assertTrue(row['stage_moved_to_audited'])
        meta = self.d.execute(
            'SELECT m.status,m.confidence,m.method FROM mm_evidence_meta m '
            'WHERE m.evidence_id=?', (row['evidence_id'],)).fetchone()
        self.assertEqual(tuple(meta), ('unverified', 0.0, 'direct_fetch'))
        self.assertTrue(self.d.execute(
            "SELECT 1 FROM mm_events WHERE business_id=? AND action='stage_transition'",
            (bid,)).fetchone())
        self.assertEqual(self.d.execute(
            "SELECT stage FROM mm_deals WHERE business_id=?", (bid,)).fetchone()[0], 'AUDITED')
        self.assertEqual(result['external_sends'], 0)

    def test_backfill_idempotent_second_run_zero(self):
        bid = self._extra_business()
        self.backfill(ids=[bid], politeness=0)
        again = self.backfill(ids=[bid], politeness=0)
        self.assertEqual(again['backfilled'], 0)
        # And a scoped default run skips businesses that already have evidence.
        scoped = self.backfill(ids=[bid, self.bid], politeness=0)
        self.assertEqual(scoped['backfilled'], 0)

    def test_backfill_never_marks_verified(self):
        bid = self._extra_business()
        result = self.backfill(ids=[bid], politeness=0)
        eid = result['results'][0]['evidence_id']
        status = self.d.execute('SELECT status FROM mm_evidence_meta WHERE evidence_id=?',
                                (eid,)).fetchone()[0]
        self.assertEqual(status, 'unverified')

    def test_excluded_prospects_are_skipped_before_fetch_or_any_write(self):
        cases = {
            'business_suppression': "UPDATE businesses SET suppression_reason='fixture opt out' WHERE id=?",
            'business_rejected': "UPDATE businesses SET current_status='rejected' WHERE id=?",
            'hold': "INSERT INTO mm_holds(business_id,reason) VALUES(?,'fixture hold')",
            'deal_suppressed': "UPDATE mm_deals SET stage='SUPPRESSED' WHERE business_id=?",
            'pipeline_rejected': "INSERT INTO pipeline_items VALUES(?,'REJECTED')",
            'pipeline_suppressed': "INSERT INTO pipeline_items VALUES(?,'SUPPRESSED')",
        }

        def forbidden(url):
            self.fail('Excluded business fetched: ' + url)

        for name, sql in cases.items():
            with self.subTest(reason=name):
                bid = self._extra_business()
                self.d.execute(sql, (bid,))
                self.d.commit()
                before = self.snapshot()
                result = self.backfill(ids=[bid], fetch=forbidden, politeness=0)
                self.assertEqual(result['backfilled'], 0)
                self.assertEqual(result['moved_to_audited'], 0)
                self.assertEqual([r['id'] for r in result['skipped']], [bid])
                self.assertTrue(result['skipped'][0]['reason'])
                with self.assertRaises(ValueError):
                    self.contacts(bid, fetch=forbidden, politeness=0)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse((self.r / 'audit-backfills' / f'business-{bid}.txt').exists())
                self.assertFalse((self.r / 'contact-captures' / f'business-{bid}').exists())

    def test_default_backfill_excludes_rejected_and_held_businesses(self):
        rejected = self._extra_business()
        held = self._extra_business()
        self.d.execute("UPDATE businesses SET current_status='rejected' WHERE id=?", (rejected,))
        self.d.execute("INSERT INTO mm_holds VALUES(?,'fixture hold')", (held,))
        self.d.commit()
        before = self.snapshot()
        result = self.backfill(politeness=0,
                               fetch=lambda url: self.fail('Excluded business fetched: ' + url))
        self.assertEqual(result['backfilled'], 0)
        self.assertEqual({r['id'] for r in result['skipped']}, {rejected, held})
        self.assertEqual(self.snapshot(), before)


class OwnSiteDiscovery(EvidenceOps):
    def test_exclusion_committed_during_fetch_prevents_capture_and_all_writes(self):
        for name, sql in self.exclusion_cases().items():
            for existing_capture in (False, True):
                with self.subTest(reason=name, existing_capture=existing_capture):
                    bid = self._extra_business()
                    capture = (self.r / 'contact-captures' / f'business-{bid}' /
                               f'{c.public_url(c.business(self.d, bid)["public_website"])}.json')
                    original = b'Synthetic earlier contact capture; preserve these bytes.'
                    if existing_capture:
                        capture.parent.mkdir(parents=True, exist_ok=True)
                        capture.write_bytes(original)
                    observed = {}
                    with self.assertRaisesRegex(ValueError, 'Evidence discovery excluded:'):
                        self.contacts(
                            bid, paths=('',), politeness=0,
                            fetch=self.late_exclusion_fetch(bid, sql, observed))
                    self.assertEqual(self.snapshot(), observed['snapshot'])
                    self.assertEqual(self.d.total_changes, observed['changes'])
                    self.assertFalse(self.d.in_transaction)
                    if existing_capture:
                        self.assertEqual(capture.read_bytes(), original)
                    else:
                        self.assertFalse(capture.exists())

    def test_successful_discovery_preserves_existing_caller_transaction(self):
        bid = self._extra_business()
        before = self.snapshot()
        self.d.execute("UPDATE businesses SET source='caller pending change' WHERE id=?", (bid,))
        page = '<a href="mailto:fixture@example.invalid">Contact</a>'
        self.contacts(bid, fetch=lambda url: (page, page.encode(), url), paths=('',), politeness=0)
        self.assertTrue(self.d.in_transaction)
        self.assertEqual(c.business(self.d, bid)['source'], 'caller pending change')
        self.d.rollback()
        self.assertEqual(self.snapshot(), before)

    def test_contacts_recorded_with_provenance_never_verified(self):
        bid = self._extra_business()
        page = ('<html><a href="mailto:Info@Fix.example.co.nz">mail</a>'
                '<a href="tel:021 555 123">t</a><form action="/contact"></form></html>')
        result = self.contacts(
            bid, fetch=lambda url: (page, page.encode(), url), politeness=0)
        self.assertGreaterEqual(result['pages_fetched'], 1)
        recipients = {r['recipient'] for r in result['recorded']}
        self.assertIn('info@fix.example.co.nz', recipients)
        for r in result['recorded']:
            self.assertFalse(r['verified'])
            self.assertEqual(r['confidence'], 0.0)
            row = self.d.execute(
                'SELECT confidence,capture_path,capture_hash,source_url '
                'FROM mm_contact_evidence WHERE business_id=? AND recipient=?',
                (bid, r['recipient'])).fetchone()
            self.assertEqual(row[0], 0.0)
            self.assertTrue(Path(row[1]).is_file())
            self.assertEqual(row[2], c.sha(Path(row[1]).read_bytes()))
        self.assertEqual(result['verified_count'], 0)

    def test_unreachable_site_records_typed_attempt(self):
        bid = self._extra_business()
        result = self.contacts(bid, politeness=0)
        self.assertEqual(result['pages_fetched'], 0)
        codes = {a['blocked_code'] for a in result['attempts']}
        self.assertTrue(codes and all(code.startswith('BLOCKED_SITE_') for code in codes),
                        result['attempts'])
        self.assertEqual(result['recorded'], [])


class GuessNeverVerified(EvidenceOps):
    def test_guess_alone_never_verified(self):
        """P8 policy: a guess recorded by discovery NEVER enters the verified
        email lane; require_email still fails closed."""
        bid = self._extra_business()
        page = '<a href="mailto:guess@unreachable-fixture.example.co.nz">x</a>'
        self.contacts(
            bid, fetch=lambda url: (page, page.encode(), url), politeness=0)
        address = 'guess@unreachable-fixture.example.co.nz'
        self.assertTrue(self.d.execute(
            'SELECT 1 FROM mm_contact_evidence WHERE business_id=? AND recipient=?',
            (bid, address)).fetchone())
        self.assertFalse(self.d.execute(
            'SELECT 1 FROM email_candidates WHERE normalized_email=? OR email=?',
            (address, address)).fetchone())
        self.assertFalse(self.d.execute(
            'SELECT 1 FROM email_verifications v JOIN email_candidates c ON c.id=v.candidate_id '
            'WHERE c.prospect_id=? AND c.email=?', (bid, address)).fetchone())
        with self.assertRaises(ValueError):
            s.require_email(self.d, bid, address)
        self.assertEqual(self.d.execute(
            'SELECT confidence FROM mm_contact_evidence WHERE recipient=?',
            (address,)).fetchone()[0], 0.0)


class TypedSearchErrors(EvidenceOps):
    def test_searxng_absent_raises_typed_error(self):
        backend = mm_discovery.mm_search_backend
        with patch.object(backend, 'search', return_value={
            'state': backend.BLOCKED_NOT_LISTENING, 'reason': 'Synthetic unavailable service',
        }), self.assertRaises(mm_discovery.SearchBlocked) as ctx:
            mm_discovery.searxng_candidates('heat pumps christchurch', 'Canterbury',
                                            endpoint='http://127.0.0.1:1', limit=5)
        self.assertTrue(ctx.exception.code.startswith('BLOCKED_SEARCH_'))

    def test_discover_search_cli_prints_typed_block(self):
        out = io.StringIO()
        blocked = mm_discovery.SearchBlocked(
            'BLOCKED_SEARCH_SERVICE_ABSENT', 'http://127.0.0.1:8888', 'fixture'
        )
        with patch.object(mm_discovery, 'searxng_candidates', side_effect=blocked), \
                contextlib.redirect_stdout(out):
            rc = mm_operator.main(['discover-search', '--query', 'heat pumps',
                                   '--region', 'Canterbury',
                                   '--endpoint', 'http://127.0.0.1:1',
                                   '--dry-run'])
        self.assertEqual(rc, 0)
        doc = json.loads(out.getvalue())
        self.assertEqual(doc['candidates'], [])
        self.assertTrue(doc['blocked']['code'].startswith('BLOCKED_SEARCH_'))

    def test_frozen_signature_still_ranked_when_service_present(self):
        backend = mm_discovery.mm_search_backend
        result = {
            'state': backend.OK,
            'results': [{'url': 'https://first.example.co.nz/x'},
                        {'url': 'https://first.example.co.nz/y'},
                        {'url': 'https://second.example.co.nz'}],
        }
        with patch.object(backend, 'search', return_value=result):
            cands = mm_discovery.searxng_candidates('q', 'Canterbury',
                                                    endpoint='http://127.0.0.1:8888', limit=5)
        self.assertEqual([x['canonical_host'] for x in cands],
                         ['first.example.co.nz', 'second.example.co.nz'])


if __name__ == '__main__':
    unittest.main()
