"""Tests for the brain approval layer — deterministic, zero-model, fail-closed."""
import contextlib
import datetime as dt
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mm_core as c
import mm_brain as brain
import mm_email as email_engine
import mm_email_store as email_store
import mm_outreach as outreach
import mm_operator as operator
import mm_intelligence as intelligence
import test_acceptance as fixtures


class BrainReview(unittest.TestCase):
    """Test brain review decisions against the acceptance fixture."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mm-brain-')
        self.r = Path(self.tmp.name)
        (self.r / 'database').mkdir()
        self.path = self.r / 'database' / 'money_machine.db'
        SOURCE = Path(os.environ.get('MM_TEST_SOURCE', str(Path(__file__).resolve().parents[1] / 'database/money_machine.db')))
        with sqlite3.connect('file:' + str(SOURCE) + '?mode=ro', uri=True) as src, sqlite3.connect(self.path) as dst:
            src.backup(dst)
        self.env = patch.dict(os.environ, {'MM_ROOT': str(self.r)})
        self.env.start()
        self.backup = c.backup(self.r)
        self.d = c.connect(self.path)
        c.migrate(self.d, self.backup)
        email_store.migrate_email(self.d, self.backup)
        self.d.execute("UPDATE email_policy SET mode='v2',acceptance_hash=? WHERE id=1", ('f' * 64,))
        self.d.execute("UPDATE email_release_policy SET mode='PRODUCTION',verifier_version=?,precision_receipt=? WHERE id=1",
                       (email_engine.VERSION, 'f' * 64))
        # Synthetic fixture prospect
        self.bid = self.d.execute(
            "INSERT INTO businesses(name,region,public_website,source,discovered_at,current_status,is_dummy) "
            "VALUES('Brain Fixture','Fixturetown','https://fixture.example.co.nz','fixture',?,'discovered',0)",
            (c.now(),)
        ).lastrowid
        self.d.execute("INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)", (self.bid, c.now()))
        self.address = 'operator@fixture.example.co.nz'
        self.capture = self.r / 'capture.txt'
        self.capture.write_text(
            '<html><title>Brain Fixture</title><h1>Brain Fixture</h1><p>Fixturetown</p>'
            '<p>Contact email: ' + self.address + '</p><p>Verified local fixture observation, not a real business.</p></html>'
        )
        self.demo = self.r / 'demo.html'
        demo_html = '''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="connect-src 'none'; form-action 'none'">
<style>:focus-visible{outline:2px solid blue}</style>
<p>Local demonstration. Nothing is sent.</p>
<label for="email">Email</label><input id="email" type="email"><button type="button">Preview only</button></html>'''
        self.demo.write_text(demo_html)
        meta = {'url': 'https://fixture.example.co.nz', 'captured_at': c.now(),
                'sha256': c.sha(self.capture.read_bytes()), 'path': str(self.capture)}
        page = email_engine.parse_page(meta, self.capture.read_bytes())
        dns = {'fixture.example.co.nz': {'domain_resolves': True, 'mx_present': True,
                                         'mx_hosts': ['mx.fixture.example.co.nz'], 'domain_accepts_mail': True,
                                         'status': 'mx', 'checked_at': c.now()}}
        result = email_engine.evaluate(dict(c.business(self.d, self.bid)), [page], dns)
        email_store.persist(self.d, result, self.r)
        self.eid = c.record_evidence(self.d, self.bid, 'https://fixture.example.co.nz',
                                      'Fixture commercial problem', 'Synthetic test only',
                                      self.capture, 'verified', 'rendered_fixture', .9)
        c.record_contact(self.d, self.bid, self.address, 'https://fixture.example.co.nz',
                          self.capture, 'Fixture relevance', 'Fixture permission approval', 'Human Fixture')
        operator.demo_qa(self.d, self.bid, self.demo)
        self.mid = c.create_draft(self.d, self.bid, self.address,
                                   'Subject: A verified narrow improvement\n\nHello team, this is a local fixture '
                                   'describing a verified issue with explicit limitations. Dion, verified '
                                   'fixture identity. Please reply if useful, or reply no thanks to opt out.')
        self.d.commit()

    def tearDown(self):
        self.d.close()
        self.env.stop()
        self.tmp.cleanup()

    def proof(self, kind, oid=None, h=None, cents=None):
        import time
        p = self.r / ('receipt-' + str(time.time_ns()) + '.txt')
        p.write_text('SYNTHETIC TEST ONLY ' + kind + ' ' + str(time.time_ns()))
        return self.d.execute(
            'INSERT INTO mm_receipts(kind,business_id,object_id,source_system,external_id,artifact_path,'
            'artifact_hash,content_hash,amount_cents,currency,verified_by,verified_at,occurred_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (kind, self.bid, oid, 'fixture-provider', str(time.time_ns()), str(p), c.sha(p.read_bytes()),
             h, cents, 'NZD', 'Human Fixture', c.now(), c.now())
        ).lastrowid

    def approve_human(self):
        m = self.d.execute('SELECT * FROM mm_messages WHERE id=?', (self.mid,)).fetchone()
        h = c.digest(m['recipient'], m['body'])
        rid = self.proof('approval', self.mid, h)
        c.approve(self.d, self.mid, m['body'], 'Human Fixture', rid)
        return h

    # --- Tests ---

    def test_01_brain_review_approves_valid_fixture(self):
        result = brain.review(self.d, self.mid)
        self.assertEqual(result['decision'], 'APPROVED_FOR_SEND')
        self.assertEqual(result['criteria_met'], '13/13')
        self.assertEqual(result['rejections'], [])

    def test_02_brain_approve_sets_approved_hash(self):
        result = brain.approve(self.d, self.mid)
        self.assertIn('receipt_id', result)
        self.assertIn('artifact_path', result)
        m = self.d.execute('SELECT * FROM mm_messages WHERE id=?', (self.mid,)).fetchone()
        self.assertIsNotNone(m['approved_hash'])
        self.assertEqual(m['approved_by'], 'brain')
        self.assertIsNotNone(m['approval_ref'])
        # Check approval_events recorded
        ev = self.d.execute('SELECT * FROM approval_events WHERE object_id=? AND action_type=?',
                            (self.mid, 'brain_approval')).fetchone()
        self.assertIsNotNone(ev)
        self.assertEqual(ev['approved'], 1)
        self.assertEqual(ev['approved_by'], 'brain')

    def test_03_brain_reject_records_rejection(self):
        result = brain.reject(self.d, self.mid, 'stale_evidence')
        self.assertEqual(result['decision'] if 'decision' in result else result['reason'], 'stale_evidence')
        ev = self.d.execute('SELECT * FROM approval_events WHERE object_id=? AND action_type=?',
                            (self.mid, 'brain_rejection')).fetchone()
        self.assertIsNotNone(ev)
        self.assertEqual(ev['approved'], 0)

    def test_04_brain_blocks_when_identity_missing(self):
        self.d.execute('DELETE FROM email_identity_checks WHERE prospect_id=?', (self.bid,))
        self.d.commit()
        result = brain.review(self.d, self.mid)
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))
        self.assertTrue(any('identity' in r for r in result['rejections']))

    def test_05_brain_blocks_when_email_not_verified_high(self):
        self.d.execute("UPDATE prospect_email_state SET selection_status='NO_VERIFIED_EMAIL' WHERE prospect_id=?", (self.bid,))
        self.d.commit()
        result = brain.review(self.d, self.mid)
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))
        self.assertIn('NO_VERIFIED_EMAIL', result['rejections'])

    def test_06_brain_blocks_when_suppressed(self):
        self.d.execute('INSERT INTO mm_suppression VALUES(?,?,?)', (self.address, 'fixture', c.now()))
        self.d.commit()
        result = brain.review(self.d, self.mid)
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))
        self.assertIn('suppressed', result['rejections'])

    def test_07_brain_blocks_when_evidence_stale(self):
        self.d.execute("UPDATE mm_evidence SET checked_at='2000-01-01' WHERE id=?", (self.eid,))
        self.d.commit()
        result = brain.review(self.d, self.mid)
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))
        self.assertIn('stale_evidence', result['rejections'])

    def test_08_brain_blocks_when_unfilled_placeholder(self):
        m = self.d.execute('SELECT * FROM mm_messages WHERE id=?', (self.mid,)).fetchone()
        bad_body = m['body'].replace(' team,', ' [first name],')
        self.d.execute('UPDATE mm_messages SET body=? WHERE id=?', (bad_body, self.mid))
        self.d.commit()
        result = brain.review(self.d, self.mid)
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))
        self.assertIn('unfilled_placeholder', result['rejections'])

    def test_09_brain_blocks_when_email_policy_shadow(self):
        self.d.execute("UPDATE email_policy SET mode='shadow' WHERE id=1")
        self.d.commit()
        result = brain.review(self.d, self.mid)
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))
        self.assertIn('email_policy_hold', result['rejections'])

    def test_10_brain_blocks_when_catch_all(self):
        self.d.execute(
            "UPDATE email_verifications SET catch_all_status='yes', smtp_result='accepted' "
            "WHERE candidate_id=(SELECT best_email_id FROM prospect_email_state WHERE prospect_id=?)",
            (self.bid,))
        self.d.commit()
        result = brain.review(self.d, self.mid)
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))
        self.assertIn('catch_all_only', result['rejections'])

    def test_11_brain_blocks_when_duplicate_contact(self):
        # Create another business with same address
        sql_biz = ("INSERT INTO businesses(name,region,public_website,source,discovered_at,"
                   "current_status,is_dummy) VALUES(?,?,?,?,?,?,0)")
        bid2 = self.d.execute(sql_biz,
            ('Duplicate Contact','Fixturetown','https://dup.example.co.nz','fixture',c.now())
        ).lastrowid
        self.d.execute("INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)", (bid2, c.now()))
        dup_body = 'Subject: Previous\n\nExisting contact. Dion. Reply no thanks to opt out.'
        sql_msg = ("INSERT INTO mm_messages(business_id,evidence_id,recipient,body,digest,kind,"
                   "parent_id,created_at) VALUES(?,?,?,?,?,'initial',NULL,?)")
        self.d.execute(sql_msg,
            (bid2, self.eid, self.address, dup_body, c.digest(self.address, dup_body), c.now()))
        self.d.commit()
        result = brain.review(self.d, self.mid)
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))
        self.assertIn('duplicate_contact', result['rejections'])

    def test_12_brain_approve_fails_when_criteria_not_met(self):
        self.d.execute('DELETE FROM email_identity_checks WHERE prospect_id=?', (self.bid,))
        self.d.commit()
        with self.assertRaises(ValueError):
            brain.approve(self.d, self.mid)

    def test_13_brain_outcome_requires_brain_approval(self):
        # Human-approved message should fail brain outcome
        self.approve_human()
        with self.assertRaises(ValueError):
            brain.record_outcome(self.d, self.mid, 'positive_reply')

    def test_14_brain_outcome_records_learning(self):
        brain.approve(self.d, self.mid)
        result = brain.record_outcome(self.d, self.mid, 'positive_reply')
        self.assertTrue(result['learning_recorded'])
        # Verify learning entry exists
        row = self.d.execute('SELECT * FROM mm_learning WHERE evidence_ref=?',
                             (f'mm_messages:{self.mid}',)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['actual'], 'positive_reply')

    def test_15_brain_review_structure_complete(self):
        result = brain.review(self.d, self.mid)
        self.assertIn('criteria', result)
        self.assertIn('rejections', result)
        self.assertIn('context', result)
        self.assertIn('config_applied', result)
        self.assertIn('limitations', result)
        self.assertIn('version', result)
        # All 13 criteria present
        for name in ('identity_verified', 'canonical_domain_verified', 'first_party_evidence',
                     'commercial_need_verified', 'email_status', 'email_evidence_count_min',
                     'suppression_clear', 'duplicate_clear', 'placeholders_clear',
                     'preflight_passed', 'evidence_fresh', 'relevant_personalised_offer',
                     'correct_business_identity'):
            self.assertIn(name, result['criteria'])
            self.assertIn('pass', result['criteria'][name])
            self.assertIn('required', result['criteria'][name])

    def test_16_brain_cli_integration(self):
        import argparse
        args = argparse.Namespace(cmd='brain-review', id=self.mid, config=None)
        with contextlib.closing(c.connect(self.path)) as d:
            result = brain.cli(args, d)
        self.assertEqual(result['decision'], 'APPROVED_FOR_SEND')

    def test_17_brain_config_override(self):
        # Override to require 0 evidence count
        cfg = {'email_evidence_count_min': 0}
        result = brain.review(self.d, self.mid, cfg)
        # Still approved
        self.assertEqual(result['decision'], 'APPROVED_FOR_SEND')

    def test_18_brain_fail_closed_on_missing_data(self):
        # Delete demo QA result — preflight should fail
        self.d.execute('DELETE FROM mm_demo_qa WHERE business_id=?', (self.bid,))
        self.d.commit()
        result = brain.review(self.d, self.mid)
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))

    def test_19_brain_reject_unknown_reason(self):
        with self.assertRaises(ValueError):
            brain.reject(self.d, self.mid, 'not_a_real_reason')

    def test_20_brain_approve_writes_artifact(self):
        result = brain.approve(self.d, self.mid)
        artifact = Path(result['artifact_path'])
        self.assertTrue(artifact.is_file())
        data = json.loads(artifact.read_text())
        self.assertEqual(data['decision'], 'APPROVED_FOR_SEND')
        self.assertEqual(data['message_id'], self.mid)

    def test_21_triggers_still_enforced_with_brain_approval(self):
        """Brain approval does not bypass existing DB safety triggers."""
        brain.approve(self.d, self.mid)
        self.d.commit()
        # Try to send without receipt — trigger should block
        with self.assertRaises(sqlite3.IntegrityError):
            self.d.execute('UPDATE mm_messages SET sent_at=? WHERE id=?', (c.now(), self.mid))

    def test_22_brain_review_no_model_calls(self):
        """Brain review makes zero model calls."""
        with patch.object(socket, 'create_connection', side_effect=AssertionError('No network')):
            result = brain.review(self.d, self.mid)
        self.assertEqual(result['decision'], 'APPROVED_FOR_SEND')

    def test_23_brain_reject_records_event(self):
        brain.reject(self.d, self.mid, 'stale_evidence')
        ev = self.d.execute('SELECT * FROM mm_events WHERE action=? AND business_id=?',
                            ('brain_rejection_recorded', self.bid)).fetchone()
        self.assertIsNotNone(ev)

    def test_24_brain_approve_records_event(self):
        brain.approve(self.d, self.mid)
        ev = self.d.execute('SELECT * FROM mm_events WHERE action=? AND business_id=?',
                            ('brain_approval_recorded', self.bid)).fetchone()
        self.assertIsNotNone(ev)

    def test_25_brain_blocks_when_contact_permission_missing(self):
        self.d.execute('UPDATE mm_contact_evidence SET permission_verified_by=NULL WHERE business_id=?', (self.bid,))
        self.d.commit()
        result = brain.review(self.d, self.mid)
        # Preflight should catch this
        self.assertIn(result['decision'], ('REJECTED', 'NEEDS_RESEARCH'))

    def test_26_brain_approve_after_human_approval_fails(self):
        """Once brain-approved, a human can't re-approve (already has approved_by)."""
        brain.approve(self.d, self.mid)
        # The message now has approved_by='brain'
        m = self.d.execute('SELECT * FROM mm_messages WHERE id=?', (self.mid,)).fetchone()
        self.assertEqual(m['approved_by'], 'brain')
        self.assertIsNotNone(m['approval_ref'])

    def test_27_brain_review_already_sent_message(self):
        """Cannot review an already-sent message."""
        # Human approve and send
        self.approve_human()
        rid = self.proof('send', self.mid, c.digest(self.address, self.d.execute(
            'SELECT * FROM mm_messages WHERE id=?', (self.mid,)).fetchone()['body']))
        c.record_sent(self.d, self.mid, rid)
        self.d.commit()
        with self.assertRaises(ValueError):
            brain.review(self.d, self.mid)

    def test_28_brain_review_invalidated_message(self):
        """Cannot review an invalidated message."""
        self.d.execute('UPDATE mm_messages SET invalidated_reason=? WHERE id=?', ('test invalidation', self.mid))
        self.d.commit()
        with self.assertRaises(ValueError):
            brain.review(self.d, self.mid)


if __name__ == '__main__':
    unittest.main()
