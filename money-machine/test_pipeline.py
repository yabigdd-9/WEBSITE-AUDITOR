"""Behavioral tests for the pipeline state machine, workers, approval, routing.

All fixtures are synthetic and disposable. No network, no model calls, no real
businesses, no sends.
"""
import datetime as dt
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import mm_core as c
import mm_pipeline as p
import mm_approval as appr
import mm_model_router as router


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
    CREATE VIEW IF NOT EXISTS email_current_high AS
        SELECT prospect_id,
               email AS normalized_email,
               id AS candidate_id,
               id AS verification_id
        FROM email_verifications
        WHERE json_extract(result_json,'$.confidence_label')='VERIFIED_HIGH';
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
        self.d.close(); self.tmp.cleanup()

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
        self.d.close(); self.tmp.cleanup()

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
        self.d.close(); self.tmp.cleanup()

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

    def test_audit_gate_accepts_complete_canonical_toolkit_report(self):
        toolkit_root = Path(self.tmp.name) / 'toolkit'
        report_dir = toolkit_root / 'run-canonical'
        report_dir.mkdir(parents=True)
        report_path = report_dir / 'report.json'
        report_path.write_text(json.dumps({
            'run_id': 'run-canonical',
            'status': 'complete',
            'url': 'https://fixture.example.co.nz',
        }))

        p.enqueue(self.d, self.bid, state='AUDIT_PENDING')
        p.advance(
            self.d,
            self.bid,
            'AUDITED',
            'w-audit',
            'canonical audit captured',
            {
                'run_id': 'run-canonical',
                'report_path': str(report_path),
                'audit_engine': 'auditor_toolkit',
            },
        )

        with patch.object(appr, 'TOOLKIT_ROOT', toolkit_root.resolve()):
            ok, evidence = appr._gate_audit_evidence(self.d, self.bid)

        self.assertTrue(ok)
        self.assertEqual(evidence['source'], 'auditor_toolkit')
        self.assertEqual(evidence['run_id'], 'run-canonical')

    def test_verified_email_gate_uses_current_high_view(self):
        self.d.execute("INSERT INTO email_verifications(prospect_id,email,result_json) "
                       "VALUES(?,?,?)", (self.bid, 'medium@fixture.example.co.nz',
                       json.dumps({'confidence_label': 'VERIFIED_MEDIUM'})))
        ok, evidence = appr._gate_verified_email(self.d, self.bid)
        self.assertFalse(ok)
        self.d.execute("INSERT INTO email_verifications(prospect_id,email,result_json) "
                       "VALUES(?,?,?)", (self.bid, 'high@fixture.example.co.nz',
                       json.dumps({'confidence_label': 'VERIFIED_HIGH'})))
        ok, evidence = appr._gate_verified_email(self.d, self.bid)
        self.assertTrue(ok)
        self.assertEqual(evidence['email'], 'high@fixture.example.co.nz')
        self.assertEqual(evidence['confidence'], 'VERIFIED_HIGH')

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
        self.d.close(); self.tmp.cleanup()

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
        self.d.close(); self.tmp.cleanup()

    def _enqueue(self, state, site='https://fixture.example.co.nz'):
        bid = add_business(self.d, site=site)
        p.enqueue(self.d, bid, state=state)
        return bid

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

    def test_contact_without_released_v2_is_held_for_review(self):
        import mm_workers as workers
        bid = self._enqueue('CONTACT_PENDING')
        p.Worker('w-contact', workers.WORKERS['contact'][0],
                 workers.WORKERS['contact'][1]).run_once(self.d)
        self.assertEqual(p.item(self.d, bid)['state'], 'NEEDS_REVIEW')
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
        self.d.close(); self.tmp.cleanup()

    def test_paid_route_hard_refused(self):
        with patch.dict(os.environ, {router.FCC_FREE_MODELS_ENV: ''}, clear=False):
            self.assertIn(
                'PAID_ROUTE_REFUSED',
                router.check_route(router.FCC_PROVIDER, 'claude-paid-model'),
            )
        self.assertIn(
            'PAID_ROUTE_REFUSED',
            router.check_route(router.HERMES_PROVIDER, 'paid/hermes-model'),
        )

    def test_zero_cost_routes_accepted(self):
        with patch.dict(os.environ, {
            router.FCC_FREE_MODELS_ENV: 'claude-fcc-free',
        }, clear=False):
            self.assertIsNone(
                router.check_route(router.FCC_PROVIDER, 'claude-fcc-free')
            )
        self.assertIsNone(
            router.check_route(router.HERMES_PROVIDER, 'fixture/hermes:free')
        )

    def test_unknown_provider_refused(self):
        self.assertIsNotNone(router.check_route('acme-paid-api', 'x:free'))

    def test_no_route_yields_blocked_cost_not_paid(self):
        res = router.plan(
            self.d, 'researcher', local_lookup=lambda kind: None
        )
        self.assertEqual(res['status'], 'blocked')
        self.assertEqual(res['cost_usd'], 0)
        row = self.d.execute(
            "SELECT * FROM mm_model_invocations WHERE run_key=?",
            (res['run_key'],),
        ).fetchone()
        self.assertEqual(row['status'], 'blocked')
        self.assertEqual(row['cost_usd'], 0)

    def test_fcc_claude_is_primary(self):
        with patch.dict(os.environ, {
            router.FCC_FREE_MODELS_ENV: 'claude-fcc-free',
        }, clear=False):
            res = router.plan(
                self.d,
                'researcher',
                local_lookup=lambda kind: (
                    'claude-fcc-free' if kind == 'fcc'
                    else 'fixture/hermes:free'
                ),
            )
        self.assertEqual(res['status'], 'planned')
        self.assertEqual(res['provider'], router.FCC_PROVIDER)
        self.assertEqual(res['model'], 'claude-fcc-free')
        self.assertEqual(res['cost_usd'], 0)

    def test_hermes_fallback_used_when_fcc_would_need_payment(self):
        with patch.dict(os.environ, {
            router.FCC_FREE_MODELS_ENV: '',
        }, clear=False):
            res = router.plan(
                self.d,
                'judge',
                local_lookup=lambda kind: (
                    'claude-paid-model' if kind == 'fcc'
                    else 'fixture/hermes:free'
                ),
            )
        self.assertEqual(res['status'], 'planned')
        self.assertEqual(res['provider'], router.HERMES_PROVIDER)
        self.assertEqual(res['model'], 'fixture/hermes:free')
        self.assertEqual(res['cost_usd'], 0)

    def test_fcc_probe_requires_explicit_zero_cost_allowlist(self):
        response = io.BytesIO(json.dumps({
            'data': [{'id': 'auto'}, {'id': 'claude-fcc-free'}],
        }).encode())
        with patch.dict(os.environ, {
            router.FCC_MODEL_ENV: 'auto',
            router.FCC_FREE_MODELS_ENV: '',
        }, clear=False), patch.object(
            router, '_open_local', return_value=response
        ):
            self.assertIsNone(router.probe_fcc())

        response = io.BytesIO(json.dumps({
            'data': [{'id': 'claude-fcc-free'}],
        }).encode())
        with patch.dict(os.environ, {
            router.FCC_MODEL_ENV: 'claude-fcc-free',
            router.FCC_FREE_MODELS_ENV: 'claude-fcc-free',
        }, clear=False), patch.object(
            router, '_open_local', return_value=response
        ):
            self.assertEqual(router.probe_fcc(), 'claude-fcc-free')

    def test_complete_uses_fcc_claude_first(self):
        with patch.dict(os.environ, {
            router.FCC_FREE_MODELS_ENV: 'claude-fcc-free',
        }, clear=False), patch.object(
            router,
            '_fcc_complete',
            return_value={
                'text': 'fcc response',
                'provider': router.FCC_PROVIDER,
                'model': 'claude-fcc-free',
                'cost_usd': 0,
            },
        ) as fcc, patch.object(router, '_hermes_complete') as hermes:
            result = router.local_complete(
                'synthetic public prompt',
                lookup=lambda kind: (
                    'claude-fcc-free' if kind == 'fcc'
                    else 'fixture/hermes:free'
                ),
            )
        self.assertEqual(result['provider'], router.FCC_PROVIDER)
        fcc.assert_called_once()
        hermes.assert_not_called()

    def test_complete_falls_back_to_hermes_when_fcc_blocks(self):
        with patch.dict(os.environ, {
            router.FCC_FREE_MODELS_ENV: 'claude-fcc-free',
        }, clear=False), patch.object(
            router,
            '_fcc_complete',
            side_effect=router.BlockedCost('fcc unavailable or no longer free'),
        ), patch.object(
            router,
            '_hermes_complete',
            return_value={
                'text': 'hermes response',
                'provider': router.HERMES_PROVIDER,
                'model': 'fixture/hermes:free',
                'cost_usd': 0,
            },
        ) as hermes:
            result = router.local_complete(
                'synthetic public prompt',
                purpose='researcher',
                lookup=lambda kind: (
                    'claude-fcc-free' if kind == 'fcc'
                    else 'fixture/hermes:free'
                ),
            )
        self.assertEqual(result['provider'], router.HERMES_PROVIDER)
        hermes.assert_called_once()

    def test_complete_blocks_cost_when_no_zero_cost_route(self):
        with self.assertRaises(router.BlockedCost):
            router.local_complete(
                'synthetic public prompt',
                lookup=lambda kind: None,
            )


class StageHandlers(unittest.TestCase):
    """Adapter handlers bridge the state machine to existing components."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)
        self.bid = add_business(self.d)

    def tearDown(self):
        self.d.close(); self.tmp.cleanup()

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

    def test_audit_handler_reuses_recent_canonical_toolkit_report(self):
        import mm_workers
        recent = {
            'run_id': 'run-recent',
            'status': 'complete',
            'profile': 'static',
            'health_score': 72,
            'defect_score': 28,
            'defects': [{'defect_key': 'viewport'}],
            'artifacts': {'json': '/tmp/run-recent/report.json'},
        }
        p.enqueue(self.d, self.bid, state='AUDIT_PENDING')
        it = p.item(self.d, self.bid)
        with patch('auditor_toolkit.storage.History') as history_cls, \
             patch('auditor_toolkit.pipeline.run_audit') as run_audit:
            history_cls.return_value.get_latest_valid_audit.return_value = recent
            nxt, reason, ev = mm_workers.audit_handler(self.d, it, None)

        self.assertEqual(nxt, 'AUDITED')
        self.assertEqual(ev['run_id'], 'run-recent')
        self.assertEqual(ev['score'], 28)
        self.assertEqual(ev['audit_engine'], 'auditor_toolkit')
        self.assertEqual(ev['model_calls'], 0)
        self.assertEqual(ev['external_sends'], 0)
        run_audit.assert_not_called()

    def test_audit_handler_runs_canonical_toolkit_with_safe_options(self):
        import mm_workers
        report = {
            'run_id': 'run-new',
            'status': 'complete',
            'profile': 'static',
            'health_score': 61,
            'defect_score': 39,
            'defects': [
                {'defect_key': 'viewport'},
                {'defect_key': 'missing_title'},
            ],
            'artifacts': {'json': '/tmp/run-new/report.json'},
            'checks': {'fetch': {'required': True, 'status': 'ok'}},
        }
        p.enqueue(self.d, self.bid, state='AUDIT_PENDING')
        it = p.item(self.d, self.bid)
        with patch('auditor_toolkit.storage.History') as history_cls, \
             patch('auditor_toolkit.pipeline.run_audit', return_value=report) as run_audit:
            history_cls.return_value.get_latest_valid_audit.return_value = None
            nxt, reason, ev = mm_workers.audit_handler(self.d, it, None)

        self.assertEqual(nxt, 'AUDITED')
        self.assertEqual(ev['run_id'], 'run-new')
        self.assertEqual(ev['defect_count'], 2)
        self.assertEqual(ev['score'], 39)
        self.assertEqual(ev['health_score'], 61)
        self.assertEqual(ev['audit_engine'], 'auditor_toolkit')
        self.assertEqual(ev['model_calls'], 0)
        self.assertEqual(ev['external_sends'], 0)
        args, kwargs = run_audit.call_args
        self.assertEqual(args[0], 'https://fixture.example.co.nz')
        options = args[1]
        self.assertEqual(options.profile, 'static')
        self.assertFalse(options.ai)
        self.assertFalse(options.browser)
        self.assertFalse(options.deep)
        self.assertFalse(options.external_tools)

    def test_audit_handler_incomplete_toolkit_report_retries(self):
        import mm_workers
        report = {
            'run_id': 'run-partial',
            'status': 'partial',
            'profile': 'static',
            'health_score': None,
            'defect_score': 10,
            'defects': [],
            'artifacts': {'json': '/tmp/run-partial/report.json'},
            'checks': {
                'fetch': {'required': True, 'status': 'error'},
                'page': {'required': True, 'status': 'skipped'},
            },
        }
        p.enqueue(self.d, self.bid, state='AUDIT_PENDING')
        it = p.item(self.d, self.bid)
        with patch('auditor_toolkit.storage.History') as history_cls, \
             patch('auditor_toolkit.pipeline.run_audit', return_value=report):
            history_cls.return_value.get_latest_valid_audit.return_value = None
            with self.assertRaises(p.RetryableError):
                mm_workers.audit_handler(self.d, it, None)

    def test_contact_handler_never_fabricates(self):
        import mm_workers
        p.enqueue(self.d, self.bid, state='CONTACT_PENDING')
        it = p.item(self.d, self.bid)
        nxt, reason, ev = mm_workers.contact_handler(self.d, it, None)
        self.assertEqual(nxt, 'NEEDS_REVIEW')
        self.assertEqual(ev['external_sends'], 0)
        self.assertFalse(ev['finder_run'])

    def test_contact_handler_legacy_medium_never_advances(self):
        import mm_workers
        self.d.execute("INSERT INTO email_verifications(prospect_id,email,result_json) "
                       "VALUES(?,?,?)", (self.bid, 'maybe@fixture.example.co.nz',
                       json.dumps({'confidence_label': 'VERIFIED_MEDIUM'})))
        p.enqueue(self.d, self.bid, state='CONTACT_PENDING')
        it = p.item(self.d, self.bid)
        nxt, _, ev = mm_workers.contact_handler(self.d, it, None)
        self.assertEqual(nxt, 'NEEDS_REVIEW')
        self.assertEqual(ev['external_sends'], 0)

    def test_contact_handler_runs_v2_finder_then_advances_from_authoritative_view(self):
        import mm_workers
        import mm_email_cli

        p.enqueue(self.d, self.bid, state='CONTACT_PENDING')
        it = p.item(self.d, self.bid)
        current = {
            'email': 'office@fixture.example.co.nz',
            'verification_id': 77,
            'confidence': 'VERIFIED_HIGH',
        }
        with patch.object(
            mm_workers,
            '_email_v2_release_state',
            return_value=(True, {
                'installed': True,
                'email_policy': 'v2',
                'release_mode': 'PRODUCTION',
                'verifier_version': 'email-v2.0.1',
            }),
        ), patch.object(
            mm_workers,
            '_current_verified_high',
            side_effect=[None, current],
        ), patch.object(
            mm_email_cli,
            'find_one',
            return_value={'candidates': [], 'contact_form_urls': []},
        ) as finder:
            nxt, reason, ev = mm_workers.contact_handler(self.d, it, None)

        self.assertEqual(nxt, 'REMEDIATION_PENDING')
        self.assertEqual(ev['email'], 'office@fixture.example.co.nz')
        self.assertTrue(ev['finder_run'])
        self.assertEqual(ev['external_sends'], 0)
        finder.assert_called_once_with(self.d, self.bid)

    def test_contact_handler_finder_completion_without_high_is_valid_terminal(self):
        import mm_workers
        import mm_email_cli

        p.enqueue(self.d, self.bid, state='CONTACT_PENDING')
        it = p.item(self.d, self.bid)
        with patch.object(
            mm_workers,
            '_email_v2_release_state',
            return_value=(True, {
                'installed': True,
                'email_policy': 'v2',
                'release_mode': 'PRODUCTION',
                'verifier_version': 'email-v2.0.1',
            }),
        ), patch.object(
            mm_workers,
            '_current_verified_high',
            side_effect=[None, None],
        ), patch.object(
            mm_email_cli,
            'find_one',
            return_value={
                'candidates': [
                    {
                        'email': 'maybe@fixture.example.co.nz',
                        'confidence_label': 'VERIFIED_MEDIUM',
                    }
                ],
                'contact_form_urls': ['https://fixture.example.co.nz/contact'],
            },
        ):
            nxt, reason, ev = mm_workers.contact_handler(self.d, it, None)

        self.assertEqual(nxt, 'NO_VERIFIED_EMAIL')
        self.assertTrue(ev['finder_run'])
        self.assertEqual(ev['candidate_count'], 1)
        self.assertEqual(ev['contact_form_count'], 1)
        self.assertEqual(ev['external_sends'], 0)

    def test_contact_handler_release_hold_does_not_call_finder(self):
        import mm_workers
        import mm_email_cli

        p.enqueue(self.d, self.bid, state='CONTACT_PENDING')
        it = p.item(self.d, self.bid)
        with patch.object(
            mm_workers,
            '_current_verified_high',
            return_value=None,
        ), patch.object(
            mm_workers,
            '_email_v2_release_state',
            return_value=(False, {
                'installed': True,
                'email_policy': 'v2',
                'release_mode': 'POST_DEPLOYMENT_OBSERVATION',
                'verifier_version': 'email-v2.0.1',
            }),
        ), patch.object(
            mm_email_cli,
            'find_one',
        ) as finder:
            nxt, reason, ev = mm_workers.contact_handler(self.d, it, None)

        self.assertEqual(nxt, 'NEEDS_REVIEW')
        self.assertEqual(ev['external_sends'], 0)
        finder.assert_not_called()

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
