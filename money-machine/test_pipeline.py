"""Behavioral tests for the pipeline state machine, workers, approval, routing.

All fixtures are synthetic and disposable. No network, no model calls, no real
businesses, no sends.
"""
import datetime as dt
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import mm_approval as appr
import mm_core as c
import mm_model_router as router
import mm_pipeline as p


def fresh_db(tmp):
    path = Path(tmp) / 't.db'
    sqlite3.connect(path).close()  # mode=rw opens require an existing file
    d = c.connect(path)
    d.executescript("""
    CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY, name TEXT,
        public_website TEXT, region TEXT, source TEXT, discovered_at TEXT,
        current_status TEXT, is_dummy INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS mm_evidence(id INTEGER PRIMARY KEY, business_id INTEGER);
    CREATE TABLE IF NOT EXISTS mm_contact_evidence(id INTEGER PRIMARY KEY,
        business_id INTEGER, recipient TEXT, permission_basis TEXT,
        permission_verified_by TEXT);
    CREATE TABLE IF NOT EXISTS mm_suppression(address TEXT PRIMARY KEY, reason TEXT, added_at TEXT);
    CREATE TABLE IF NOT EXISTS mm_messages(id INTEGER PRIMARY KEY, business_id INTEGER,
        recipient TEXT, body TEXT, invalidated_reason TEXT, approved_hash TEXT);
    CREATE TABLE IF NOT EXISTS email_verifications(id INTEGER PRIMARY KEY,
        prospect_id INTEGER, email TEXT, result_json TEXT);
    CREATE TABLE IF NOT EXISTS mm_model_invocations(id INTEGER PRIMARY KEY,
        run_key TEXT UNIQUE, model TEXT, provider TEXT, purpose_hash TEXT,
        status TEXT, model_calls INTEGER DEFAULT 0, input_tokens INTEGER,
        output_tokens INTEGER, cost_usd REAL DEFAULT 0 CHECK(cost_usd=0),
        created_at TEXT, finished_at TEXT, error TEXT);
    """)
    p.migrate(d)
    appr.migrate(d)
    return d


def add_business(d, name='Fixture Co', site='https://fixture.example.co.nz'):
    return d.execute("INSERT INTO businesses(name,public_website,discovered_at) "
                     "VALUES(?,?,?)", (name, site, c.now())).lastrowid


class StateMachine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)
        self.bid = add_business(self.d)

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()

    def test_happy_path_forward_edges(self):
        p.enqueue(self.d, self.bid)
        for frm, to in p._FORWARD.items():
            self.assertEqual(p.item(self.d, self.bid)['state'], frm)
            p.transition(self.d, self.bid, to, 'w-test', 'forward')
        self.assertEqual(p.item(self.d, self.bid)['state'], 'CONVERTED')

    def test_illegal_skip_fails_closed(self):
        p.enqueue(self.d, self.bid)
        with self.assertRaises(ValueError):
            p.transition(self.d, self.bid, 'SENT', 'w-test', 'skip attempt')

    def test_unknown_to_approved_impossible(self):
        p.enqueue(self.d, self.bid)
        with self.assertRaises(ValueError):
            p.transition(self.d, self.bid, 'APPROVED', 'w-test', 'no evidence')

    def test_terminal_has_no_exit(self):
        p.enqueue(self.d, self.bid)
        p.transition(self.d, self.bid, 'SUPPRESSED', 'w-test', 'opt out')
        with self.assertRaises(ValueError):
            p.transition(self.d, self.bid, 'DISCOVERED', 'w-test', 'revive')

    def test_permanent_failure_requeue_requires_reason_and_records_recovery(self):
        p.enqueue(self.d, self.bid)
        p.transition(self.d, self.bid, 'PERMANENT_FAILURE', 'w-test', 'bad runtime')
        self.d.execute('UPDATE pipeline_items SET attempts=2 WHERE business_id=?',
                       (self.bid,))
        with self.assertRaises(ValueError):
            p.requeue_permanent_failure(self.d, self.bid, '')
        row = p.requeue_permanent_failure(
            self.d, self.bid, 'Runtime dependency/contract fault fixed', 'operator-test')
        self.assertEqual(row['state'], 'AUDIT_PENDING')
        self.assertEqual(row['attempts'], 2)
        event = self.d.execute(
            "SELECT * FROM pipeline_events WHERE business_id=? ORDER BY id DESC LIMIT 1",
            (self.bid,)).fetchone()
        self.assertEqual((event['from_state'], event['to_state'], event['actor']),
                         ('PERMANENT_FAILURE', 'AUDIT_PENDING', 'operator-test'))
        self.assertEqual(json.loads(event['evidence'])['previous_attempts_preserved'], 2)
        with self.assertRaises(ValueError):
            p.requeue_permanent_failure(self.d, self.bid, 'duplicate replay')

    def test_enqueue_idempotent(self):
        p.enqueue(self.d, self.bid, payload={'a': 1})
        p.enqueue(self.d, self.bid, payload={'b': 2})
        r = p.item(self.d, self.bid)
        self.assertEqual(json.loads(r['payload']), {'a': 1})

    def test_every_transition_audited(self):
        p.enqueue(self.d, self.bid)
        p.transition(self.d, self.bid, 'IDENTITY_PENDING', 'w-a', 'r1')
        p.transition(self.d, self.bid, 'IDENTITY_RESOLVED', 'w-b', 'r2')
        evs = self.d.execute("SELECT * FROM pipeline_events WHERE business_id=?",
                             (self.bid,)).fetchall()
        self.assertEqual(len(evs), 3)  # enqueue + 2 transitions
        self.assertEqual([e['to_state'] for e in evs],
                         ['DISCOVERED', 'IDENTITY_PENDING', 'IDENTITY_RESOLVED'])


class WorkerBehaviour(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()

    def test_worker_advances_and_is_restartable(self):
        bid = add_business(self.d)
        p.enqueue(self.d, bid)
        w = p.Worker('w-1', ('DISCOVERED',),
                     lambda d, it, w: ('IDENTITY_PENDING', 'seen', None))
        self.assertEqual(w.run_once(self.d), 1)
        self.assertEqual(p.item(self.d, bid)['state'], 'IDENTITY_PENDING')
        self.assertEqual(w.run_once(self.d), 0)  # nothing left in DISCOVERED

    def test_retryable_failure_schedules_backoff(self):
        bid = add_business(self.d)
        p.enqueue(self.d, bid)
        def boom(d, it, w):
            raise p.RetryableError('transient')
        w = p.Worker('w-2', ('DISCOVERED',), boom)
        w.run_once(self.d)
        r = p.item(self.d, bid)
        self.assertEqual(r['state'], 'DISCOVERED')
        self.assertEqual(r['attempts'], 1)
        self.assertIsNotNone(r['next_retry_at'])
        self.assertIsNone(r['lease_owner'])  # lease released for another worker

    def test_dead_letter_after_max_attempts(self):
        bid = add_business(self.d)
        p.enqueue(self.d, bid, max_attempts=2)
        def boom(d, it, w):
            raise p.RetryableError('always broken')
        w = p.Worker('w-3', ('DISCOVERED',), boom)
        w.run_once(self.d)
        self.d.execute("UPDATE pipeline_items SET next_retry_at=? WHERE business_id=?",
                       (c.now(), bid))
        w.run_once(self.d)
        self.assertEqual(p.item(self.d, bid)['state'], 'RETRYABLE_FAILURE')

    def test_permanent_failure_goes_straight_to_dead_letter(self):
        bid = add_business(self.d)
        p.enqueue(self.d, bid)
        def bad(d, it, w):
            raise p.PermanentError('unfixable')
        p.Worker('w-4', ('DISCOVERED',), bad).run_once(self.d)
        self.assertEqual(p.item(self.d, bid)['state'], 'PERMANENT_FAILURE')

    def test_lease_blocks_double_claim_and_expires(self):
        bid = add_business(self.d)
        p.enqueue(self.d, bid)
        got = p.claim(self.d, ('DISCOVERED',), 'worker-a', lease_seconds=300)
        self.assertEqual(len(got), 1)
        self.assertEqual(p.claim(self.d, ('DISCOVERED',), 'worker-b'), [])
        self.d.execute("UPDATE pipeline_items SET lease_until=? WHERE business_id=?",
                       ('2000-01-01T00:00:00+00:00', bid))
        self.assertEqual(len(p.claim(self.d, ('DISCOVERED',), 'worker-b')), 1)

    def test_circuit_breaker_opens_and_recovers(self):
        for _ in range(5):
            p.breaker_failure(self.d, 'dns')
        self.assertFalse(p.breaker_allow(self.d, 'dns'))
        self.d.execute("UPDATE circuit_breakers SET cooldown_until=? WHERE service='dns'",
                       ('2000-01-01T00:00:00+00:00',))
        self.assertTrue(p.breaker_allow(self.d, 'dns'))  # half-open probe
        p.breaker_success(self.d, 'dns')
        self.assertEqual(p.breaker(self.d, 'dns')['state'], 'closed')

    def test_rate_limit_enforced(self):
        self.assertTrue(p.rate_ok(self.d, 'test-bucket', 2, 86400))
        self.assertTrue(p.rate_ok(self.d, 'test-bucket', 2, 86400))
        self.assertFalse(p.rate_ok(self.d, 'test-bucket', 2, 86400))

    def test_blocked_cost_defers_without_paid_fallback(self):
        bid = add_business(self.d)
        p.enqueue(self.d, bid)
        def needs_model(d, it, w):
            raise p.BlockedCost('no free route')
        p.Worker('w-5', ('DISCOVERED',), needs_model).run_once(self.d)
        r = p.item(self.d, bid)
        self.assertEqual(r['state'], 'DISCOVERED')
        self.assertIn('BLOCKED_COST', r['last_error'])

    def test_health_snapshot(self):
        bid = add_business(self.d)
        p.enqueue(self.d, bid)
        h = p.health(self.d)
        self.assertEqual(h['states']['DISCOVERED'], 1)
        self.assertIn('metrics', h)


if __name__ == '__main__':
    unittest.main()
class ApprovalEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)
        self.bid = add_business(self.d)

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()

    def _fully_evidence(self):
        """Give the fixture business every piece of required evidence."""
        p.enqueue(self.d, self.bid, state='OUTREACH_PENDING')
        self.d.execute("INSERT INTO mm_evidence(business_id) VALUES(?)", (self.bid,))
        self.d.execute("INSERT INTO email_verifications(prospect_id,email,result_json) "
                       "VALUES(?,?,?)", (self.bid, 'office@fixture.example.co.nz',
                       json.dumps({'confidence_label': 'VERIFIED_HIGH'})))
        self.d.execute("INSERT INTO mm_contact_evidence(business_id,recipient,"
                       "permission_basis,permission_verified_by) VALUES(?,?,?,?)",
                       (self.bid, 'office@fixture.example.co.nz',
                        'INFERRED: published contact block invites quote enquiries',
                        'Dion'))
        self.d.execute("INSERT INTO mm_messages(business_id,recipient,body) VALUES(?,?,?)",
                       (self.bid, 'office@fixture.example.co.nz',
                        'Subject: fix\n\nFixture body.'))

    def test_missing_evidence_never_approves(self):
        aid = appr.request_approval(self.d, self.bid)
        res = appr.decide(self.d, aid, 'hermes-test', 'initial check')
        self.assertEqual(res['status'], 'NEEDS_REVIEW')
        self.assertFalse(all(g['passed'] for g in res['gates'].values()))

    def test_suppressed_contact_hard_rejects(self):
        self._fully_evidence()
        self.d.execute("INSERT INTO mm_suppression(address,reason,added_at) VALUES(?,?,?)",
                       ('office@fixture.example.co.nz', 'opt-out', c.now()))
        aid = appr.request_approval(self.d, self.bid)
        self.assertEqual(appr.decide(self.d, aid, 'hermes-test', 'r')['status'], 'REJECTED')

    def test_full_evidence_approves_and_send_is_idempotent(self):
        self._fully_evidence()
        aid = appr.request_approval(self.d, self.bid)
        res = appr.decide(self.d, aid, 'hermes-test', 'all gates verified')
        self.assertEqual(res['status'], 'APPROVED')
        body = 'Subject: fix\n\nFixture body.'
        row = appr.plan_send(self.d, self.bid, 'office@fixture.example.co.nz',
                             body, 'trial-campaign')
        self.assertEqual(row['status'], 'planned')
        again = appr.plan_send(self.d, self.bid, 'office@fixture.example.co.nz',
                               body, 'trial-campaign')
        self.assertEqual(again['idempotency_key'], row['idempotency_key'])
        n = self.d.execute("SELECT count(*) FROM outreach_send_ledger").fetchone()[0]
        self.assertEqual(n, 1)  # no duplicate record

    def test_send_requires_exact_approved_content(self):
        self._fully_evidence()
        aid = appr.request_approval(self.d, self.bid)
        appr.decide(self.d, aid, 'hermes-test', 'ok')
        with self.assertRaisesRegex(ValueError, 'CONTENT_MISMATCH'):
            appr.plan_send(self.d, self.bid, 'office@fixture.example.co.nz',
                           'Subject: CHANGED\n\ntampered body.', 'trial-campaign')

    def test_send_without_approval_blocked(self):
        self._fully_evidence()
        with self.assertRaisesRegex(ValueError, 'NO_APPROVAL'):
            appr.plan_send(self.d, self.bid, 'office@fixture.example.co.nz',
                           'Subject: fix\n\nFixture body.', 'trial-campaign')

    def test_bounce_quarantine_halts_sending(self):
        self._fully_evidence()
        for i in range(4):
            self.d.execute("INSERT INTO outreach_send_ledger(idempotency_key,"
                           "business_id,recipient,content_hash,campaign,status,"
                           "created_at,updated_at) VALUES(?,?,?,?,?,'sent',?,?)",
                           ('k%d' % i, self.bid, 'x%d@x.nz' % i, 'h', 'c',
                            c.now(), c.now()))
        for i in range(2):  # 2/6 = 33% bounce > 20% threshold
            self.d.execute("INSERT INTO outreach_send_ledger(idempotency_key,"
                           "business_id,recipient,content_hash,campaign,status,"
                           "created_at,updated_at) VALUES(?,?,?,?,?,'bounced',?,?)",
                           ('kb%d' % i, self.bid, 'b%d@x.nz' % i, 'h', 'c',
                            c.now(), c.now()))
        self.assertTrue(appr.quarantine_check(self.d)['quarantined'])
        aid = appr.request_approval(self.d, self.bid)
        appr.decide(self.d, aid, 'hermes-test', 'ok')
        with self.assertRaisesRegex(ValueError, 'QUARANTINED'):
            appr.plan_send(self.d, self.bid, 'office@fixture.example.co.nz',
                           'Subject: fix\n\nFixture body.', 'trial-campaign')

    def test_secret_in_draft_fails_content_gate(self):
        self.assertIsNotNone(appr.contains_secret('key: sk-ABCDEFGHIJKLMNOPQRSTUVWX'))
        self.assertIsNone(appr.contains_secret('Perfectly normal outreach copy.'))


class AdvanceSemantics(unittest.TestCase):
    """advance() must walk declared gate states instead of skipping them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)
        self.bid = add_business(self.d)

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()

    def test_advance_records_every_intermediate_edge(self):
        p.enqueue(self.d, self.bid)
        p.advance(self.d, self.bid, 'AUDIT_PENDING', 'w-audit', 'audit captured')
        chain = [e['to_state'] for e in self.d.execute(
            "SELECT * FROM pipeline_events WHERE business_id=? ORDER BY id",
            (self.bid,))]
        self.assertEqual(chain, ['DISCOVERED', 'IDENTITY_PENDING',
                                 'IDENTITY_RESOLVED', 'AUDIT_PENDING'])
        self.assertEqual(p.item(self.d, self.bid)['state'], 'AUDIT_PENDING')

    def test_advance_is_idempotent_when_already_at_target(self):
        p.enqueue(self.d, self.bid)
        p.advance(self.d, self.bid, 'AUDIT_PENDING', 'w', 'r')
        before = self.d.execute("SELECT count(*) FROM pipeline_events").fetchone()[0]
        p.advance(self.d, self.bid, 'AUDIT_PENDING', 'w', 'r')
        after = self.d.execute("SELECT count(*) FROM pipeline_events").fetchone()[0]
        self.assertEqual(before, after)

    def test_advance_refuses_backward_move(self):
        p.enqueue(self.d, self.bid)
        p.advance(self.d, self.bid, 'QUALIFIED', 'w', 'r')
        with self.assertRaises(ValueError):
            p.advance(self.d, self.bid, 'AUDIT_PENDING', 'w', 'rewind')

    def test_advance_supports_alternate_targets(self):
        p.enqueue(self.d, self.bid)
        p.advance(self.d, self.bid, 'NEEDS_REVIEW', 'w', 'needs a human')
        self.assertEqual(p.item(self.d, self.bid)['state'], 'NEEDS_REVIEW')

    def test_legacy_events_table_is_widened_and_rows_preserved(self):
        """Database consistency: schema drift is repaired, history is kept."""
        self.d.execute("DROP TABLE pipeline_events")
        self.d.execute("CREATE TABLE pipeline_events(id INTEGER PRIMARY KEY,"
                       "business_id INTEGER NOT NULL,stage TEXT,event_at TEXT,"
                       "detail TEXT)")
        self.d.execute("INSERT INTO pipeline_events(business_id,stage,event_at,"
                       "detail) VALUES(?,?,?,?)",
                       (self.bid, 'DISCOVERED', c.now(), 'legacy intake row'))
        p.migrate(self.d)
        cols = {r[1] for r in self.d.execute('PRAGMA table_info(pipeline_events)')}
        self.assertTrue({'from_state', 'to_state', 'actor', 'reason'} <= cols)
        row = self.d.execute("SELECT * FROM pipeline_events WHERE business_id=?",
                             (self.bid,)).fetchone()
        self.assertEqual(row['to_state'], 'DISCOVERED')
        self.assertEqual(row['reason'], 'legacy intake row')  # history intact
        self.assertEqual(row['actor'], 'legacy')
        # And the repaired table accepts new-style events.
        p.enqueue(self.d, self.bid)
        n = self.d.execute("SELECT count(*) FROM pipeline_events WHERE "
                           "business_id=?", (self.bid,)).fetchone()[0]
        self.assertEqual(n, 2)


class WorkerHandlers(unittest.TestCase):
    """Every declared stage handler must reach a legal target from its inputs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)
        p.migrate(self.d)

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()

    def _enqueue(self, state, site='https://fixture.example.co.nz'):
        bid = add_business(self.d, site=site)
        p.enqueue(self.d, bid, state=state)
        return bid

    def test_qualification_export_requires_current_matching_audit_and_captures(self):
        import mm_workers as workers

        bid = add_business(self.d)
        audit = {
            'audit_run_id': 'audit-run-export',
            'findings': [],
            'finding_evidence_complete': True,
            'score_method': 'toolkit-p5-v1',
            'score': 0,
        }
        qualification = {
            'audit_run_id': 'audit-run-export',
            'commercial_score': 45,
            'commercial_score_evidence_ids': [7],
            'commercial_score_industry': 'electrical',
            'commercial_score_basis': 'verified_capture',
            'technical_score': 0,
            'technical_score_method': 'toolkit-p5-v1',
            'technical_score_finding_ids': [],
            'technical_score_evidence_complete': True,
        }
        self.d.execute(
            'INSERT INTO pipeline_events(business_id,to_state,actor,reason,evidence,event_at) '
            'VALUES(?,?,?,?,?,?)',
            (bid, 'AUDITED', 'test', 'synthetic audit', json.dumps(audit), c.now()),
        )
        self.d.execute(
            'INSERT INTO pipeline_events(business_id,to_state,actor,reason,evidence,event_at) '
            'VALUES(?,?,?,?,?,?)',
            (bid, 'CONTACT_PENDING', 'test', 'synthetic qualification',
             json.dumps(qualification), c.now()),
        )
        current = {'evidence_ids': [7], 'industry': 'electrical'}
        with patch.object(workers, '_business', return_value={'id': bid}), \
                patch.object(workers, '_commercial_signal_context', return_value=current):
            exported = workers.qualification_evidence_for_packet(
                self.d, bid, 'audit-run-export'
            )
            self.assertEqual(exported['commercial_score_evidence_ids'], [7])
            self.assertEqual(exported['technical_score'], 0)
            with self.assertRaisesRegex(ValueError, 'latest persisted audit'):
                workers.qualification_evidence_for_packet(
                    self.d, bid, 'older-audit-run'
                )

        self.d.commit()
        import mm_operator

        output = io.StringIO()
        open_database = c.connect

        def open_test_database(readonly=False):
            if not readonly:
                raise AssertionError('qualification export must open the database read-only')
            return open_database(Path(self.tmp.name) / 't.db', readonly=readonly)

        with patch.object(c, 'connect', side_effect=open_test_database), \
                patch.object(workers, '_commercial_signal_context', return_value=current), \
                redirect_stdout(output):
            result = mm_operator.main([
                'pipeline-qualification-export', str(bid),
                '--run-id', 'audit-run-export',
            ])
        self.assertEqual(result, 0)
        self.assertEqual(
            json.loads(output.getvalue())['commercial_score_evidence_ids'], [7]
        )

        stale = {'evidence_ids': [8], 'industry': 'electrical'}
        with patch.object(workers, '_business', return_value={'id': bid}), \
                patch.object(workers, '_commercial_signal_context', return_value=stale):
            with self.assertRaisesRegex(ValueError, 'changed or expired'):
                workers.qualification_evidence_for_packet(
                    self.d, bid, 'audit-run-export'
                )

    def test_audit_handler_uses_canonical_audit_findings(self):
        import mm_workers as workers

        bid = self._enqueue('AUDIT_PENDING')
        report = {
            'run_id': 'toolkit-run-1',
            'status': 'complete',
            'defects': [
                {'finding_id': 'title-1', 'defect_key': 'missing-title',
                 'severity': 'high', 'defect': 'Page has no title.',
                 'observed': 'title tag missing', 'evidence_summary': 'title tag missing',
                 'evidence_ref': 'page', 'confidence': 'observed'},
                {'finding_id': 'meta-1', 'defect_key': 'missing-meta',
                 'severity': 'medium', 'defect': 'Page has no description.',
                 'observed': 'description tag missing', 'evidence_summary': 'description tag missing',
                 'evidence_ref': 'page', 'confidence': 'observed'},
            ],
            'breakdown': {'health_score': 76, 'severity_total': 24},
            'coverage': {'required': 4, 'passed': 4},
        }
        with patch('auditor_toolkit.storage.History') as history, \
             patch('auditor_toolkit.pipeline.run_audit', return_value=report) as run_audit:
            history.return_value.get_latest_valid_audit.return_value = None
            state, _, evidence = workers.audit_handler(
                self.d, {'business_id': bid}, None
            )
        self.assertEqual(state, 'AUDITED')
        self.assertEqual(evidence['audit_run_id'], 'toolkit-run-1')
        self.assertEqual(evidence['defect_count'], 2)
        self.assertEqual(evidence['score'], 24)
        self.assertEqual(evidence['score_method'], 'toolkit-p5-v1')
        self.assertTrue(evidence['finding_evidence_complete'])
        self.assertTrue(evidence['reported_score_matches_findings'])
        self.assertEqual(
            [finding['evidence_summary'] for finding in evidence['findings']],
            ['title tag missing', 'description tag missing'],
        )
        options = run_audit.call_args.args[1]
        self.assertFalse(options.allow_private)
        self.assertFalse(options.browser)
        self.assertFalse(options.external_tools)

    def test_audit_handler_partial_run_cannot_create_technical_score(self):
        import mm_workers as workers

        bid = self._enqueue('AUDIT_PENDING')
        report = {
            'run_id': 'partial-run',
            'status': 'partial',
            'defects': [
                {'finding_id': 'finding-1', 'defect_key': 'missing-title',
                 'severity': 'high', 'defect': 'Page has no title.',
                 'observed': 'title tag missing', 'evidence_summary': 'title tag missing',
                 'evidence_ref': 'page', 'confidence': 'observed'},
            ],
            'breakdown': {'health_score': None, 'severity_total': 16},
            'coverage': {'required': 5, 'passed': 4},
        }
        with patch('auditor_toolkit.storage.History') as history, \
             patch('auditor_toolkit.pipeline.run_audit', return_value=report):
            history.return_value.get_latest_valid_audit.return_value = None
            state, _, evidence = workers.audit_handler(
                self.d, {'business_id': bid}, None
            )
        self.assertEqual(state, 'AUDITED')
        self.assertEqual(evidence['score'], 0)
        self.assertFalse(evidence['finding_evidence_complete'])

    def test_qualification_invalid_scores_fail_closed(self):
        import mm_workers as workers

        bid = self._enqueue('QUALIFICATION_PENDING')
        commercial = {'qualification_score': 10, 'tier': 'COLD', 'reasons': []}
        for score in (None, '55', True, float('nan'), float('inf'), -5):
            item = {
                'business_id': bid,
                'payload': json.dumps({'score': score, 'defect_count': 'unknown'}),
            }
            with patch('mm_lead_qualifier.qualify_lead', return_value=commercial):
                state, _, evidence = workers.qualification_handler(
                    self.d, item, None
                )
            self.assertEqual(state, 'REJECTED')
            self.assertEqual(evidence['technical_score'], 0)
            self.assertEqual(evidence['defect_count'], 0)

        item = {
            'business_id': bid,
            'payload': json.dumps({'score': 100, 'defect_count': 3}),
        }
        with patch('mm_lead_qualifier.qualify_lead', return_value=commercial):
            state, _, evidence = workers.qualification_handler(
                self.d, item, None
            )
        self.assertEqual(state, 'REJECTED')
        self.assertEqual(evidence['technical_score'], 0)
        self.assertEqual(evidence['technical_score_finding_ids'], [])
        self.assertFalse(evidence['technical_score_evidence_complete'])

    def test_qualification_uses_only_fresh_verified_commercial_evidence(self):
        import mm_workers as workers

        bid = self._enqueue('QUALIFICATION_PENDING')
        self.d.execute('ALTER TABLE businesses ADD COLUMN industry_id INTEGER')
        self.d.execute(
            'CREATE TABLE industries(id INTEGER PRIMARY KEY,name TEXT NOT NULL)'
        )
        self.d.execute('INSERT INTO industries(id,name) VALUES(1,?)', ('electrical',))
        self.d.execute('UPDATE businesses SET industry_id=1 WHERE id=?', (bid,))
        for name, declaration in (
            ('url', 'TEXT'), ('observation', 'TEXT'),
            ('limitation', 'TEXT'), ('checked_at', 'TEXT'),
        ):
            self.d.execute(f'ALTER TABLE mm_evidence ADD COLUMN {name} {declaration}')
        self.d.execute(
            'CREATE TABLE mm_evidence_meta('
            'evidence_id INTEGER PRIMARY KEY,status TEXT,method TEXT,confidence REAL,'
            'claim_type TEXT,commercial_relevance TEXT,expires_at TEXT,'
            'capture_path TEXT,capture_hash TEXT,verified_by TEXT,verification_count INTEGER)'
        )

        expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
        verified_evidence_id = None
        for status, observation in (
            ('verified', 'We are hiring a senior electrician to join our team.'),
            ('unverified', 'We approved a $50,000 website investment budget.'),
        ):
            capture = Path(self.tmp.name) / f'{status}.txt'
            capture.write_text(observation)
            capture_hash = hashlib.sha256(capture.read_bytes()).hexdigest()
            cursor = self.d.execute(
                'INSERT INTO mm_evidence(business_id,url,observation,limitation,checked_at) '
                'VALUES(?,?,?,?,?)',
                (bid, 'https://fixture.example.co.nz/about', observation,
                 'synthetic test capture', c.now()),
            )
            evidence_id = cursor.lastrowid
            if status == 'verified':
                verified_evidence_id = evidence_id
            self.d.execute(
                'INSERT INTO mm_evidence_meta VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (evidence_id, status, 'public_capture', 0.95, 'observed_fact',
                 'business hiring signal', expires, str(capture), capture_hash,
                 'test-reviewer', 1),
            )

        item = {'business_id': bid, 'payload': '{}'}
        state, _, evidence = workers.qualification_handler(self.d, item, None)

        self.assertEqual(state, 'CONTACT_PENDING')
        self.assertGreaterEqual(evidence['commercial_score'], 30)
        self.assertEqual(evidence['commercial_score_evidence_ids'], [verified_evidence_id])
        self.assertEqual(evidence['commercial_score_industry'], 'electrical')

    def test_qualification_keeps_commercial_and_technical_tiers_separate(self):
        import mm_workers as workers

        bid = self._enqueue('QUALIFICATION_PENDING')
        commercial = {'qualification_score': 10, 'tier': 'COLD', 'reasons': []}
        item = {
            'business_id': bid,
            'payload': json.dumps({
                'score': 90,
                'defect_count': 3,
                'score_method': 'detector-severity-v1',
                'finding_evidence_complete': True,
                'audit_run_id': 'test-run',
                'findings': [
                    {'finding_id': 'critical-a', 'defect_key': 'critical-a',
                     'severity': 'critical', 'finding': 'Critical issue A',
                     'evidence': 'captured evidence A'},
                    {'finding_id': 'critical-b', 'defect_key': 'critical-b',
                     'severity': 'critical', 'finding': 'Critical issue B',
                     'evidence': 'captured evidence B'},
                    {'finding_id': 'critical-c', 'defect_key': 'critical-c',
                     'severity': 'critical', 'finding': 'Critical issue C',
                     'evidence': 'captured evidence C'},
                ],
            }),
        }
        with patch('mm_lead_qualifier.qualify_lead', return_value=commercial):
            state, _, evidence = workers.qualification_handler(
                self.d, item, None
            )
        self.assertEqual(state, 'CONTACT_PENDING')
        self.assertEqual(evidence['commercial_score'], 10)
        self.assertEqual(evidence['technical_score'], 90)
        self.assertEqual(evidence['commercial_tier'], 'COLD')
        self.assertEqual(evidence['technical_tier'], 'HIGH_OPPORTUNITY')
        self.assertEqual(evidence['qualification_basis'], 'technical')
        self.assertEqual(evidence['tier'], 'TECHNICAL_OPPORTUNITY')
        self.assertEqual(evidence['technical_score_method'], 'detector-severity-v1')
        self.assertEqual(evidence['technical_score_finding_ids'], [
            'critical-a', 'critical-b', 'critical-c',
        ])
        self.assertTrue(evidence['technical_score_evidence_complete'])

    def test_pipeline_qualification_uses_persisted_audit_event_evidence(self):
        import mm_workers as workers

        bid = self._enqueue('AUDIT_PENDING')
        audit = p.Worker(
            'w-audit-evidence', ('AUDIT_PENDING',),
            lambda d, item, worker: (
                'AUDITED', 'synthetic audit captured',
                {
                    'audit_run_id': 'audit-run-1',
                    'score_method': 'detector-severity-v1',
                    'finding_evidence_complete': True,
                    'defect_count': 2,
                    'score': 48,
                    'findings': [
                        {'finding_id': 'finding-a', 'defect_key': 'a',
                         'severity': 'critical', 'finding': 'Critical issue',
                         'evidence': 'captured evidence'},
                        {'finding_id': 'finding-b', 'defect_key': 'b',
                         'severity': 'high', 'finding': 'High issue',
                         'evidence': 'captured evidence'},
                    ],
                },
            ),
        )
        understanding = p.Worker(
            'w-understanding-evidence', ('AUDITED',),
            lambda d, item, worker: (
                'QUALIFICATION_PENDING', 'synthetic context prepared', {},
            ),
        )
        commercial = {'qualification_score': 10, 'tier': 'COLD', 'reasons': []}
        self.assertEqual(audit.run_once(self.d), 1)
        self.assertEqual(understanding.run_once(self.d), 1)
        with patch('mm_lead_qualifier.qualify_lead', return_value=commercial):
            qualify = p.Worker(
                'w-qualification-evidence', workers.WORKERS['qualification'][0],
                workers.WORKERS['qualification'][1],
            )
            self.assertEqual(qualify.run_once(self.d), 1)

        self.assertEqual(p.item(self.d, bid)['state'], 'CONTACT_PENDING')
        event = self.d.execute(
            "SELECT evidence FROM pipeline_events WHERE business_id=? "
            "AND to_state='CONTACT_PENDING' ORDER BY id DESC LIMIT 1",
            (bid,),
        ).fetchone()
        qualification = json.loads(event['evidence'])
        self.assertEqual(qualification['technical_score'], 48)
        self.assertEqual(qualification['commercial_score'], 10)
        self.assertEqual(qualification['qualification_basis'], 'technical')
        self.assertEqual(qualification['audit_run_id'], 'audit-run-1')
        self.assertEqual(qualification['technical_score_finding_ids'], [
            'finding-a', 'finding-b',
        ])

    def test_handler_targets_are_reachable_from_declared_inputs(self):
        """Regression: earlier handlers returned states the machine rejected."""
        import mm_workers as workers
        for name, (states, handler) in workers.WORKERS.items():
            if name == 'audit':
                continue  # needs live HTTP; the state machine edge is covered below
            for state in states:
                bid = self._enqueue(state)
                p.Worker('w-' + name, states, handler).run_once(self.d)
                r = p.item(self.d, bid)
                self.assertNotIn('Illegal transition', r['last_error'] or '',
                                 '%s from %s produced an illegal target' % (name, state))
                self.assertNotIn('completion rejected', r['last_error'] or '',
                                 '%s from %s could not complete' % (name, state))

    def test_handler_cannot_cross_the_approval_boundary(self):
        """A stage handler must never be able to walk an item into SENT."""
        for target in p.POST_APPROVAL:
            bid = self._enqueue('OUTREACH_PENDING')
            with self.assertRaises(ValueError):
                p.advance(self.d, bid, target, 'w-rogue', 'skip the gates')

    def test_sent_requires_provider_verified_ledger_evidence(self):
        bid = self._enqueue('APPROVED')
        # The approval/send lane (not a stage handler) owns these edges.
        p.transition(self.d, bid, 'READY_TO_SEND', 'approval-engine', 'approved')
        with self.assertRaises(ValueError):
            p.mark_sent(self.d, bid, 'w-send', 'invented-message-id')
        self.assertEqual(p.item(self.d, bid)['state'], 'READY_TO_SEND')

    def test_identity_without_website_is_permanent(self):
        import mm_workers as workers
        bid = self._enqueue('DISCOVERED', site=None)
        p.Worker('w-id', workers.WORKERS['identity'][0],
                 workers.WORKERS['identity'][1]).run_once(self.d)
        self.assertEqual(p.item(self.d, bid)['state'], 'PERMANENT_FAILURE')

    def test_contact_without_verified_email_is_a_valid_final_state(self):
        import mm_workers as workers
        bid = self._enqueue('CONTACT_PENDING')
        p.Worker('w-contact', workers.WORKERS['contact'][0],
                 workers.WORKERS['contact'][1]).run_once(self.d)
        self.assertEqual(p.item(self.d, bid)['state'], 'NO_VERIFIED_EMAIL')
        n = self.d.execute("SELECT count(*) FROM email_verifications").fetchone()[0]
        self.assertEqual(n, 0)  # nothing fabricated into the evidence tables

    def test_outreach_gate_never_sends_and_never_approves_itself(self):
        import mm_workers as workers
        bid = self._enqueue('OUTREACH_PENDING')
        p.Worker('w-out', workers.WORKERS['outreach_gate'][0],
                 workers.WORKERS['outreach_gate'][1]).run_once(self.d)
        # Incomplete evidence must route to review, never to approval.
        self.assertEqual(p.item(self.d, bid)['state'], 'NEEDS_REVIEW')
        self.assertEqual(self.d.execute(
            "SELECT count(*) FROM outreach_send_ledger").fetchone()[0], 0)
        self.assertEqual(self.d.execute(
            "SELECT count(*) FROM approval_records").fetchone()[0], 0)

    def test_bad_handler_target_does_not_crash_the_worker(self):
        bid = self._enqueue('DISCOVERED')
        def bad(d, it, w):
            return ('SENT', 'handler tries to skip ahead', None)
        w = p.Worker('w-bad', ('DISCOVERED',), bad)
        self.assertEqual(w.run_once(self.d), 0)  # isolated, not raised
        r = p.item(self.d, bid)
        self.assertEqual(r['state'], 'DISCOVERED')
        self.assertIn('completion rejected', r['last_error'])
        self.assertEqual(r['attempts'], 1)


class ModelRouter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()

    def test_paid_route_hard_refused(self):
        self.assertIn('PAID_ROUTE_REFUSED',
                      router.check_route('openrouter', 'anthropic/claude-sonnet-4'))
        with self.assertRaises(router.PaidRouteRefused):
            # plan() treats a non-free id in config as a hard error, never routes
            router.PURPOSE_ROUTES['test-role'] = [('openrouter', 'paid/model-1')]
            try:
                router.plan(self.d, 'test-role')
            finally:
                router.PURPOSE_ROUTES.pop('test-role')

    def test_free_routes_accepted(self):
        self.assertIsNone(router.check_route('openrouter', 'meituan/longcat-2.0:free'))
        self.assertIsNone(router.check_route('local:llamacpp', None))

    def test_unknown_provider_refused(self):
        self.assertIsNotNone(router.check_route('acme-paid-api', 'x:free'))

    def test_no_route_yields_blocked_cost_not_paid(self):
        os.environ.pop('OPENROUTER_API_KEY', None)
        res = router.plan(self.d, 'researcher', local_lookup=lambda kind: None)
        self.assertEqual(res['status'], 'blocked')
        self.assertEqual(res['cost_usd'], 0)
        r = self.d.execute("SELECT * FROM mm_model_invocations WHERE run_key=?",
                           (res['run_key'],)).fetchone()
        self.assertEqual(r['status'], 'blocked')
        self.assertEqual(r['cost_usd'], 0)

    def test_local_route_is_preferred_and_free(self):
        """A local server must win over any external route, at zero cost."""
        os.environ.pop('OPENROUTER_API_KEY', None)  # no external route available
        res = router.plan(self.d, 'researcher',
                          local_lookup=lambda kind: 'stub-local-4b' if kind == 'llamacpp' else None)
        self.assertEqual(res['status'], 'planned')
        self.assertEqual(res['provider'], 'local:llamacpp')
        self.assertEqual(res['model'], 'stub-local-4b')
        self.assertEqual(res['cost_usd'], 0)
        self.assertEqual(res['model_calls'], 0)

    def test_external_route_used_only_when_no_local_route_exists(self):
        os.environ['OPENROUTER_API_KEY'] = 'stub-key-never-called'
        os.environ['MM_ALLOW_EXTERNAL_FREE_MODELS'] = '1'
        try:
            res = router.plan(self.d, 'judge', local_lookup=lambda kind: None)
            self.assertEqual(res['status'], 'planned')
            self.assertTrue(res['model'].endswith(':free'))
            self.assertEqual(res['cost_usd'], 0)
        finally:
            os.environ.pop('OPENROUTER_API_KEY', None)
            os.environ.pop('MM_ALLOW_EXTERNAL_FREE_MODELS', None)

    def test_external_free_route_requires_explicit_opt_in(self):
        os.environ['OPENROUTER_API_KEY'] = 'stub-key-never-called'
        os.environ.pop('MM_ALLOW_EXTERNAL_FREE_MODELS', None)
        try:
            res = router.plan(self.d, 'judge', local_lookup=lambda kind: None)
            self.assertEqual(res['status'], 'blocked')
            self.assertEqual(res['cost_usd'], 0)
            self.assertIn('external free models disabled', res['reason'])
        finally:
            os.environ.pop('OPENROUTER_API_KEY', None)

    def test_llamacpp_probe_parses_openai_model_list(self):
        original = router._get_json
        router._get_json = lambda url, timeout=3: {'data': [{'id': 'ggml-org/Qwen3-4B-GGUF:Q4_K_M'}]}
        try:
            self.assertEqual(router.probe_llamacpp(),
                             'ggml-org/Qwen3-4B-GGUF:Q4_K_M')
        finally:
            router._get_json = original

    def test_ollama_probe_parses_local_model_tags(self):
        with patch.object(
            router,
            '_get_json',
            return_value={'models': [{'name': 'qwen3:4b'}, {'model': 'phi4:mini'}]},
        ) as get_json:
            self.assertEqual(router.probe_ollama('qwen3:4b'), 'qwen3:4b')
            get_json.assert_called_once_with(
                router.OLLAMA_BASE.rstrip('/') + '/api/tags', 3
            )

    def test_local_route_uses_ollama_after_llamacpp_is_unavailable(self):
        with patch.dict(os.environ, {'MM_ALLOW_EXTERNAL_FREE_MODELS': '0'}):
            result = router.plan(
                self.d,
                'researcher',
                local_lookup=lambda kind: 'qwen3:4b' if kind == 'ollama' else None,
            )
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(result['provider'], 'local:ollama')
        self.assertEqual(result['model'], 'qwen3:4b')
        self.assertEqual(result['cost_usd'], 0)
        self.assertEqual(result['model_calls'], 0)

    def test_local_complete_uses_ollama_chat_without_external_egress(self):
        response = io.BytesIO(json.dumps({
            'message': {'content': 'synthetic local response'},
        }).encode())
        requests = []

        def open_local(request, timeout):
            requests.append((request, timeout))
            return response

        with patch.object(router, '_open_local', side_effect=open_local):
            result = router.local_complete(
                'synthetic prompt',
                max_tokens=17,
                timeout=4,
                lookup=lambda kind: 'qwen3:4b' if kind == 'ollama' else None,
            )

        self.assertEqual(result['text'], 'synthetic local response')
        self.assertEqual(result['provider'], 'local:ollama')
        self.assertEqual(result['model'], 'qwen3:4b')
        self.assertEqual(result['cost_usd'], 0)
        request, timeout = requests[0]
        self.assertEqual(request.full_url, 'http://127.0.0.1:11434/api/chat')
        self.assertEqual(timeout, 4)
        payload = json.loads(request.data)
        self.assertEqual(payload['model'], 'qwen3:4b')
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['options'], {'num_predict': 17, 'temperature': 0})

    def test_ollama_route_rejects_non_loopback_endpoint(self):
        with patch.object(router, 'OLLAMA_BASE', 'http://192.0.2.10:11434'), \
                patch.object(router, '_open_local') as open_local:
            with self.assertRaises(router.BlockedCost):
                router.local_complete(
                    'synthetic prompt',
                    lookup=lambda kind: 'qwen3:4b' if kind == 'ollama' else None,
                )
        open_local.assert_not_called()

    def test_local_complete_blocks_cost_when_no_local_route(self):
        with self.assertRaises(router.BlockedCost):
            router.local_complete('hello', lookup=lambda kind: None)


if __name__ == '__main__':
    unittest.main()

class StageHandlers(unittest.TestCase):
    """Adapter handlers bridge the state machine to existing components."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)
        self.bid = add_business(self.d)

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()

    def test_identity_rejects_private_url(self):
        import mm_workers
        bid = add_business(self.d, 'Internal', 'http://192.168.1.10/x')
        p.enqueue(self.d, bid)
        it = p.item(self.d, bid)
        # public_url raises ValueError -> Worker wraps as retryable; call direct
        with self.assertRaises(Exception):
            mm_workers.identity_handler(self.d, it, None)

    def test_identity_resolves_public_site(self):
        import mm_workers
        p.enqueue(self.d, self.bid)
        it = p.item(self.d, self.bid)
        nxt, reason, ev = mm_workers.identity_handler(self.d, it, None)
        self.assertEqual(nxt, 'AUDIT_PENDING')
        self.assertEqual(ev['canonical_host'], 'fixture.example.co.nz')

    def test_contact_handler_never_fabricates(self):
        import mm_workers
        p.enqueue(self.d, self.bid, state='CONTACT_PENDING')
        it = p.item(self.d, self.bid)
        nxt, reason, ev = mm_workers.contact_handler(self.d, it, None)
        self.assertEqual(nxt, 'NO_VERIFIED_EMAIL')

    def test_contact_handler_uses_verified_high_only(self):
        import mm_workers
        self.d.execute("INSERT INTO email_verifications(prospect_id,email,result_json) "
                       "VALUES(?,?,?)", (self.bid, 'maybe@fixture.example.co.nz',
                       json.dumps({'confidence_label': 'VERIFIED_MEDIUM'})))
        p.enqueue(self.d, self.bid, state='CONTACT_PENDING')
        it = p.item(self.d, self.bid)
        nxt, _, _ = mm_workers.contact_handler(self.d, it, None)
        self.assertEqual(nxt, 'NO_VERIFIED_EMAIL')  # MEDIUM never routes to send lane

    def test_demo_handler_requires_artifact(self):
        import mm_workers
        p.enqueue(self.d, self.bid, state='DEMO_PENDING')
        it = p.item(self.d, self.bid)
        nxt, _, _ = mm_workers.demo_handler(self.d, it, None)
        self.assertEqual(nxt, 'NEEDS_REVIEW')  # no fabricated DEMO_READY

    def test_outreach_gate_blocks_unverified(self):
        import mm_workers
        p.enqueue(self.d, self.bid, state='OUTREACH_PENDING')
        it = p.item(self.d, self.bid)
        nxt, reason, ev = mm_workers.outreach_handler(self.d, it, None)
        self.assertEqual(nxt, 'NEEDS_REVIEW')
        self.assertIn('email_verified_high', ev['gates'])


if __name__ == '__main__':
    unittest.main()
