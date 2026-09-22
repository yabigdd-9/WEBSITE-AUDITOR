"""P5 tests: evidence throughput — audit backfill, own-site contact discovery,
typed BLOCKED_SEARCH_* errors, and the guess-alone-never-verified policy.

All fixtures synthetic/disposable. No external sends, no model calls, $0.
Network use is loopback-only (a local http.server) plus typed-failure probes.
"""
import contextlib
import http.server
import io
import json
from pathlib import Path
import sqlite3
import threading
import unittest
from unittest.mock import patch

import test_acceptance as legacy
import mm_core as c
import mm_discovery
import mm_evidence_ops as ops
import mm_email_store as s
import mm_operator


class _Quiet(http.server.BaseHTTPRequestHandler):
    body = b"<html><a href='mailto:Info@Fix.example.co.nz'>mail</a><form action='/c'></form></html>"

    def do_GET(self):
        if self.path.startswith('/dead'):
            self.send_response(500); self.end_headers(); return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *a):  # keep test output clean
        pass


class LoopbackSite:
    def __init__(self):
        self.srv = http.server.HTTPServer(('127.0.0.1', 0), _Quiet)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path=''):
        return f'http://127.0.0.1:{self.port}/{path}'

    def stop(self):
        self.srv.shutdown(); self.srv.server_close(); self.thread.join(timeout=5)


class EvidenceOps(unittest.TestCase):
    setUp = legacy.Acceptance.setUp
    tearDown = legacy.Acceptance.tearDown

    def _extra_business(self, site='https://unreachable-fixture.example.co.nz'):
        bid = self.d.execute(
            "INSERT INTO businesses(name,region,public_website,source,discovered_at,"
            "current_status,is_dummy) VALUES('Backfill Fixture','Fixturetown',?,"
            "'fixture',?,'discovered',0)", (site, c.now())).lastrowid
        self.d.execute("INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)",
                       (bid, c.now()))
        self.d.commit()
        return bid

class AuditBackfill(EvidenceOps):
    def test_unreachable_outcome_recorded_as_evidence_and_moves_stage(self):
        bid = self._extra_business()
        result = ops.audit_backfill(self.d, ids=[bid], fetch=ops.fetch_own_site, politeness=0)
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
        ops.audit_backfill(self.d, ids=[bid], politeness=0)
        again = ops.audit_backfill(self.d, ids=[bid], politeness=0)
        self.assertEqual(again['backfilled'], 0)
        # And a scoped default run skips businesses that already have evidence.
        scoped = ops.audit_backfill(self.d, ids=[bid, self.bid], politeness=0)
        self.assertEqual(scoped['backfilled'], 0)

    def test_backfill_never_marks_verified(self):
        bid = self._extra_business()
        result = ops.audit_backfill(self.d, ids=[bid], politeness=0)
        eid = result['results'][0]['evidence_id']
        status = self.d.execute('SELECT status FROM mm_evidence_meta WHERE evidence_id=?',
                                (eid,)).fetchone()[0]
        self.assertEqual(status, 'unverified')


class OwnSiteDiscovery(EvidenceOps):
    def test_contacts_recorded_with_provenance_never_verified(self):
        bid = self._extra_business()
        page = ('<html><a href="mailto:Info@Fix.example.co.nz">mail</a>'
                '<a href="tel:021 555 123">t</a><form action="/contact"></form></html>')
        result = ops.discover_own_site_contacts(
            self.d, bid, fetch=lambda url: (page, page.encode(), url), politeness=0)
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
        result = ops.discover_own_site_contacts(self.d, bid, politeness=0)
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
        ops.discover_own_site_contacts(
            self.d, bid, fetch=lambda url: (page, page.encode(), url), politeness=0)
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
        with self.assertRaises(mm_discovery.SearchBlocked) as ctx:
            mm_discovery.searxng_candidates('heat pumps christchurch', 'Canterbury',
                                            endpoint='http://127.0.0.1:1', limit=5)
        self.assertTrue(ctx.exception.code.startswith('BLOCKED_SEARCH_'))

    def test_discover_search_cli_prints_typed_block(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = mm_operator.main(['discover-search', '--query', 'heat pumps',
                                   '--region', 'Canterbury', '--dry-run'])
        self.assertEqual(rc, 0)
        doc = json.loads(out.getvalue())
        self.assertEqual(doc['candidates'], [])
        self.assertTrue(doc['blocked']['code'].startswith('BLOCKED_SEARCH_'))

    def test_frozen_signature_still_ranked_when_service_present(self):
        site = LoopbackSite()
        _Quiet.body = json.dumps({
            'results': [{'url': 'https://first.example.co.nz/x'},
                        {'url': 'https://first.example.co.nz/y'},
                        {'url': 'https://second.example.co.nz'}]}).encode()
        try:
            cands = mm_discovery.searxng_candidates('q', 'Canterbury',
                                                    endpoint=site.url(), limit=5)
        finally:
            site.stop()
        self.assertEqual([x['canonical_host'] for x in cands],
                         ['first.example.co.nz', 'second.example.co.nz'])


if __name__ == '__main__':
    unittest.main()
