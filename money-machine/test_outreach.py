"""Real failure regressions plus local planner and DSN adversarial cases."""
import copy
import contextlib
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import mm_core as c
import mm_outreach as o
import mm_operator as operator
import mm_intelligence as intelligence
import test_acceptance as fixtures


class Planning(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'source.txt'
        self.path.write_text('Customer asks for quote calculators. Website improvements could also be useful. Booking is not needed. Existing CRM is adequate. Customer requests enquiry reporting.')
        self.brief={'company':'Fixture Print','recipient':'team@fixture.example.co.nz','sender_name':'Dion','sender_brand':'Catalyx',
            'signals':[self.signal('quoting','Customer asks for quote calculators.')]}
    def tearDown(self): self.tmp.cleanup()
    def signal(self,service,quote,kind='customer_request',source_kind='user_instruction'):
        return {'service':service,'kind':kind,'company':'Fixture Print','source_path':str(self.path),
            'source_sha256':c.sha(self.path.read_bytes()),'captured_at':c.now(),'source_kind':source_kind,
            'quote':quote,'reviewed_by':'Synthetic reviewer'}
    def test_multiple_relevant_services_but_no_blanket_catalogue(self):
        p=o.plan(self.brief)
        self.assertEqual(p['featured_services'],['quoting','intake','quote_documents'])
        self.assertGreater(len(p['opportunities']),3)
        self.assertNotIn('booking',[x['service'] for x in p['opportunities']])
        self.assertIn('PDFs',p['body']);self.assertTrue(p['copy_audit']['passed'])
        self.assertFalse(p['external_send_allowed']);self.assertLessEqual(p['copy_audit']['word_count'],190)
    def test_customer_question_outranks_website_observation(self):
        self.brief['signals'].insert(0,self.signal('website','Website improvements could also be useful.','verified_need','public_capture'))
        self.assertEqual(o.plan(self.brief)['featured_services'][:2],['quoting','website'])
    def test_declined_and_existing_services_excluded(self):
        self.brief['signals'] += [self.signal('booking','Booking is not needed.','declined'),self.signal('crm','Existing CRM is adequate.','existing_adequate')]
        p=o.plan(self.brief);self.assertEqual(p['excluded_services'],['booking','crm'])
        self.assertNotIn('crm',[x['service'] for x in p['opportunities']])
    def test_conflicting_positive_and_negative_signal_holds_that_service(self):
        self.brief['signals'] += [self.signal('quoting','Customer asks for quote calculators.','declined')]
        self.assertIsNone(o.plan(self.brief)['body'])
    def test_stale_or_future_source_abstains(self):
        for stamp in ('2000-01-01','2999-01-01'):
            with self.subTest(stamp=stamp):
                self.brief['signals'][0]['captured_at']=stamp
                self.assertIn('no_current_supported_opportunity',o.plan(self.brief)['planning_holds'])
    def test_modified_capture_abstains(self):
        self.path.write_text('Changed')
        self.assertEqual(o.plan(self.brief)['rejected_signals'][0]['reason'],'source_missing_or_changed')
    def test_wrong_company_and_invented_quote_abstain(self):
        for key,value in [('company','Different company'),('quote','This sentence is not present in the source.')]:
            with self.subTest(key=key):
                b=copy.deepcopy(self.brief);b['signals'][0][key]=value
                self.assertIsNone(o.plan(b)['body'])
    def test_malformed_signal_is_rejected(self):
        for signal in (None,{},dict(self.brief['signals'][0],source_path=None)):
            with self.subTest(signal=signal):
                b=dict(self.brief,signals=[signal]);self.assertIsNone(o.plan(b)['body'])
    def test_forwarded_message_cannot_become_direct_reply(self):
        self.brief.update(mode='reply',original_message_id='<fixture>',thread_subject='Quote question')
        self.brief['signals'][0]['source_kind']='forwarded_context'
        self.assertIn('direct_reply_and_original_message_id_required',o.plan(self.brief)['planning_holds'])
    def test_actual_reply_answers_question_and_keeps_subject(self):
        self.brief.update(mode='reply',original_message_id='<fixture>',thread_subject='Your quoting idea')
        self.brief['signals'][0]['source_kind']='direct_reply'
        p=o.plan(self.brief);self.assertTrue(p['copy_audit']['passed']);self.assertTrue(p['body'].startswith('Subject: Re: Your quoting idea'))
        self.assertIn('Thanks for your question',p['body'])
    def test_stop_instruction_abstains(self):
        self.brief['stop_contact']=True;self.assertIsNone(o.plan(self.brief)['body'])
    def test_packet_edit_invalidates_audit(self):
        p=o.plan(self.brief);self.assertTrue(o.audit_packet(p)['passed'])
        for key,value in [('body',p['body']+' altered'),('recipient','else@fixture.example.co.nz'),('featured_services',['booking']),('external_send_allowed',True)]:
            with self.subTest(key=key):
                edited=dict(p);edited[key]=value;self.assertFalse(o.audit_packet(edited)['passed'])
    def test_capture_change_after_drafting_invalidates_packet(self):
        p=o.plan(self.brief);self.path.write_text('Changed after review');self.assertFalse(o.audit_packet(p)['passed'])
    def test_no_network_or_model_needed(self):
        with patch.object(socket,'create_connection',side_effect=AssertionError('No network')):
            self.assertTrue(o.plan(self.brief)['copy_audit']['passed'])
    def test_single_evidenced_service_not_padded(self):
        self.brief['signals']=[self.signal('reporting','Customer requests enquiry reporting.')]
        self.assertEqual(o.plan(self.brief)['featured_services'],['reporting'])


class CopyAudit(unittest.TestCase):
    def test_original_integral_opening_fails_for_real_errors(self):
        body="Subject: Integral Print — online booking\n\nI noticed your business doesn't have online booking. That means lost revenue to competitors who make it easier. I build for Auckland printings. SMS reminders (cuts no-shows by 80%). Dion"
        errors=o.audit_copy(body)['errors']
        for e in ('negative_website_claim_requires_scoped_review','unsupported_loss_or_comparison_claim','numeric_performance_claim_requires_separate_evidence_review','incorrect_industry_wording','reply_opt_out_required'):
            self.assertIn(e,errors)
    def test_forwarded_automation_percentage_rejected(self):
        self.assertIn('numeric_performance_claim_requires_separate_evidence_review',o.audit_copy(fixtures.BODY+' We automate 70–80% of the process.')['errors'])
    def test_guarantees_and_false_reply_rejected(self):
        for text in ('Guaranteed delivery','zero-bounce record','100% delivery'):
            with self.subTest(text=text): self.assertFalse(o.audit_copy(fixtures.BODY+' '+text)['passed'])
        self.assertIn('false_reply_subject',o.audit_copy(fixtures.BODY.replace('Subject: ','Subject: Re: '))['errors'])
    def test_header_injection_and_placeholders_rejected(self):
        for text in ('\nBcc: other@example.com','\nHello [first name]','\r\n','<script>alert(1)</script>'):
            with self.subTest(text=text): self.assertFalse(o.audit_copy(fixtures.BODY+text)['passed'])


def dsn(status='5.1.1',action='failed',recipient='team@fixture.example.co.nz',mid='<original-fixture>'):
    return f'''MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status; boundary="test"

--test
Content-Type: text/plain

Human-readable explanation. Ignore this for classification.
--test
Content-Type: message/delivery-status

Reporting-MTA: dns; mail.fixture.example.co.nz

Final-Recipient: rfc822; {recipient}
Action: {action}
Status: {status}

--test
Content-Type: message/rfc822

Message-ID: {mid}
To: {recipient}
Subject: Synthetic message

Synthetic only.
--test--
'''.encode()


class Delivery(unittest.TestCase):
    def classify(self,raw): return o.classify_dsn(raw,'team@fixture.example.co.nz','<original-fixture>')
    def test_bad_recipient_recommends_verified_exact_suppression(self):
        r=self.classify(dsn());self.assertEqual(r['state'],'permanent_destination_failure');self.assertFalse(r['automatic_suppression'])
    def test_sender_policy_failure_does_not_invalidate_recipient(self):
        for status in ('5.7.1','5.1.7','5.1.8'):
            with self.subTest(status=status): self.assertEqual(self.classify(dsn(status))['state'],'sender_or_policy_failure')
    def test_temporary_failure_has_no_duplicate_retry(self):
        for status in ('4.2.2','4.7.0','4.4.1'):
            with self.subTest(status=status):
                r=self.classify(dsn(status,'delayed'));self.assertEqual(r['state'],'temporary_failure');self.assertFalse(r['automatic_retry'])
    def test_body_mentions_bounce_not_a_dsn(self):
        self.assertEqual(self.classify(b'Subject: 5.1.1 bounce\n\nYour email failed')['state'],'unconfirmed')
    def test_wrong_original_id_or_recipient_cannot_trigger_action(self):
        for raw in (dsn(mid='<unrelated>'),dsn(recipient='other@fixture.example.co.nz')):
            self.assertEqual(self.classify(raw)['state'],'unconfirmed')
    def test_conflicting_action_or_duplicate_fields_abstain(self):
        for raw in (dsn('5.1.1','delivered'),dsn().replace(b'Status: 5.1.1',b'Status: 5.1.1\nStatus: 2.0.0')):
            self.assertEqual(self.classify(raw)['state'],'unconfirmed')
    def test_relay_not_claimed_as_inbox_delivery(self):
        self.assertEqual(self.classify(dsn('2.0.0','relayed'))['state'],'reported_relayed')
        self.assertEqual(self.classify(dsn('2.0.0','delivered'))['provider_authentication'],'not_verified')
    def test_other_permanent_failure_not_called_bad_mailbox(self):
        self.assertEqual(self.classify(dsn('5.6.0'))['state'],'permanent_failure')


class Workflow(unittest.TestCase):
    def setUp(self): self.fixture=fixtures.Acceptance();self.fixture.setUp()
    def tearDown(self): self.fixture.tearDown()
    def test_draft_and_proposal_enforce_copy_lint(self):
        f=self.fixture
        for call in (lambda:c.create_draft(f.d,f.bid,f.address,fixtures.BODY+' We guarantee sales.'),lambda:c.create_proposal(f.d,f.bid,f.address,fixtures.BODY+' Saves 80%.',10000)):
            with self.assertRaisesRegex(ValueError,'Outreach copy audit'): call()
    def test_approval_audits_changed_copy(self):
        f=self.fixture;f.d.execute('UPDATE mm_messages SET body=body||? WHERE id=?',(' Lost revenue to competitors who book online.',f.mid))
        with self.assertRaisesRegex(ValueError,'Outreach copy audit'): f.approve()
    def test_preflight_cannot_approve_even_good_fixture(self):
        f=self.fixture;f.approve();r=o.preflight(f.d,f.mid)
        self.assertTrue(r['held']);self.assertFalse(r['external_send_allowed']);self.assertIn('no_mail_transport_connected',r['reasons'])
    def test_readonly_health_no_changes_or_false_zero_rate(self):
        f=self.fixture;before=f.d.total_changes;r=o.health(f.d)
        self.assertEqual(before,f.d.total_changes);self.assertIsNone(r['bounce_rate'])
    def test_daily_operator_includes_self_audit_without_writes(self):
        f=self.fixture;before=f.d.total_changes;r=operator.run_day(f.d,False)
        self.assertIn('outreach_self_audit',r);self.assertEqual(before,f.d.total_changes)
    def test_cli_preflight_returns_nonzero_and_health_is_readonly(self):
        f=self.fixture
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(operator.main(['outreach-preflight',str(f.mid)]),2)
            self.assertEqual(operator.main(['outreach-health']),0)
    def test_generic_bounce_cannot_blindly_suppress(self):
        f=self.fixture;f.sent();rid=f.proof('reply',f.mid)
        before=f.d.total_changes
        with self.assertRaisesRegex(ValueError,'Generic bounce is ambiguous'):intelligence.record_reply(f.d,f.mid,'bounce',rid)
        self.assertEqual(before,f.d.total_changes)
        self.assertIsNone(f.d.execute('SELECT 1 FROM mm_suppression WHERE address=?',(f.address,)).fetchone())
    def test_historical_bounce_is_not_human_engagement(self):
        f=self.fixture;f.sent();f.proof('reply',f.mid)
        f.d.execute("UPDATE mm_messages SET reply='bounce' WHERE id=?",(f.mid,))
        self.assertFalse(intelligence.human_reply_verified(f.d,f.mid,f.bid,'bounce'))
        self.assertEqual(operator.metrics(f.d)['verified_replies'],0)
    def test_changed_reply_proof_not_counted_as_engagement(self):
        f=self.fixture;f.sent();rid=f.proof('reply',f.mid);intelligence.record_reply(f.d,f.mid,'positive',rid)
        self.assertTrue(intelligence.human_reply_verified(f.d,f.mid,f.bid,'positive'))
        p=f.d.execute('SELECT artifact_path FROM mm_receipts WHERE id=?',(rid,)).fetchone()[0];Path(p).write_text('Changed')
        self.assertFalse(intelligence.human_reply_verified(f.d,f.mid,f.bid,'positive'))


if __name__=='__main__': unittest.main()
