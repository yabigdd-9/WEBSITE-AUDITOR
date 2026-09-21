#!/usr/bin/env python3
"""Behavioral tests on disposable snapshots; never writes fixtures to the live DB."""
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
import time
import traceback
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent/'scripts'))
import mm_core as c
import mm_intelligence as i
import mm_operator as o
import mm_email as email_engine
import mm_email_store as email_store
SOURCE=Path(os.environ.get('MM_TEST_SOURCE',str(Path(__file__).resolve().parents[1]/'database/money_machine.db')))
PACKAGE=Path(__file__).resolve().parents[1]
BODY='Subject: A verified narrow improvement\n\nHello team, this is a local fixture describing a verified issue with explicit limitations. Dion, verified fixture identity. Please reply if useful, or reply no thanks to opt out.'
DEMO='''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="connect-src 'none'; form-action 'none'"><style>:focus-visible{outline:2px solid blue}</style><p>Local demonstration. Nothing is sent.</p><label for="email">Email</label><input id="email" type="email"><button type="button">Preview only</button></html>'''

class Acceptance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='mm-acceptance-');self.r=Path(self.temp.name);(self.r/'database').mkdir();self.path=self.r/'database/money_machine.db'
        with sqlite3.connect('file:'+str(SOURCE)+'?mode=ro',uri=True) as src,sqlite3.connect(self.path) as dst:src.backup(dst)
        self.env=patch.dict(os.environ,{'MM_ROOT':str(self.r)});self.env.start()
        self.backup=c.backup(self.r);self.d=c.connect(self.path);c.migrate(self.d,self.backup)
        email_store.migrate_email(self.d,self.backup)
        self.d.execute("UPDATE email_policy SET mode='v2',acceptance_hash=? WHERE id=1",('f'*64,))
        # Synthetic release receipt only inside this disposable test database.
        self.d.execute("UPDATE email_release_policy SET mode='PRODUCTION',verifier_version=?,precision_receipt=? WHERE id=1",(email_engine.VERSION,'f'*64))
        # Independent fixture prospect. No real contact or sends used by tests.
        self.bid=self.d.execute("INSERT INTO businesses(name,region,public_website,source,discovered_at,current_status,is_dummy) VALUES('Acceptance Fixture','Fixturetown','https://fixture.example.co.nz','fixture',?,'discovered',0)",(c.now(),)).lastrowid
        self.d.execute("INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)",(self.bid,c.now()));self.address='operator@fixture.example.co.nz'
        self.capture=self.r/'capture.txt';self.capture.write_text('<html><title>Acceptance Fixture</title><h1>Acceptance Fixture</h1><p>Fixturetown</p><p>Contact email: '+self.address+'</p><p>Verified local fixture observation, not a real business.</p></html>');self.demo=self.r/'demo.html';self.demo.write_text(DEMO)
        meta={'url':'https://fixture.example.co.nz','captured_at':c.now(),'sha256':c.sha(self.capture.read_bytes()),'path':str(self.capture)}
        page=email_engine.parse_page(meta,self.capture.read_bytes())
        dns={'fixture.example.co.nz':{'domain_resolves':True,'mx_present':True,'mx_hosts':['mx.fixture.example.co.nz'],'domain_accepts_mail':True,'status':'mx','checked_at':c.now()}}
        result=email_engine.evaluate(dict(c.business(self.d,self.bid)),[page],dns)
        email_store.persist(self.d,result,self.r)
        self.eid=c.record_evidence(self.d,self.bid,'https://fixture.example.co.nz','Fixture commercial problem','Synthetic test only',self.capture,'verified','rendered_fixture',.9)
        c.record_contact(self.d,self.bid,self.address,'https://fixture.example.co.nz',self.capture,'Fixture relevance','Fixture permission approval','Human Fixture')
        o.demo_qa(self.d,self.bid,self.demo);self.mid=c.create_draft(self.d,self.bid,self.address,BODY);self.d.commit()
    def tearDown(self):self.d.close();self.env.stop();self.temp.cleanup()
    def proof(self,kind,oid=None,h=None,cents=None):
        p=self.r/('receipt-'+str(time.time_ns())+'.txt');p.write_text('SYNTHETIC TEST ONLY '+kind+' '+str(time.time_ns()))
        return self.d.execute('INSERT INTO mm_receipts(kind,business_id,object_id,source_system,external_id,artifact_path,artifact_hash,content_hash,amount_cents,currency,verified_by,verified_at,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(kind,self.bid,oid,'fixture-provider',str(time.time_ns()),str(p),c.sha(p.read_bytes()),h,cents,'NZD','Human Fixture',c.now(),c.now())).lastrowid
    def approve(self,proposal=False,oid=None):
        oid=oid or self.mid;table='mm_proposals' if proposal else 'mm_messages';m=self.d.execute(f'SELECT * FROM {table} WHERE id=?',(oid,)).fetchone()
        h=c.proposal_digest(m['recipient'],m['body'],m['price_cents']) if proposal else c.digest(m['recipient'],m['body']);rid=self.proof('approval',oid,h)
        c.approve(self.d,oid,m['body'],'Human Fixture',rid,proposal);return h
    def sent(self):
        h=self.approve();rid=self.proof('send',self.mid,h);c.record_sent(self.d,self.mid,rid);return rid
    def proposal(self):return c.create_proposal(self.d,self.bid,self.address,BODY,75000)
    def pay(self,cents=75000):
        rid=self.proof('payment',cents=cents);c.cash(self.d,self.bid,cents,rid);return self.d.execute('SELECT id FROM mm_cash WHERE receipt=?',(str(rid),)).fetchone()[0],rid

    def test_01_unapproved_message_cannot_be_sent(self):
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('UPDATE mm_messages SET sent_at=? WHERE id=?',(c.now(),self.mid))
    def test_02_modified_approved_body_invalidates_approval(self):
        self.approve();self.d.execute('UPDATE mm_messages SET body=body||? WHERE id=?',(' modified',self.mid));self.assertIsNone(self.d.execute('SELECT approved_hash FROM mm_messages WHERE id=?',(self.mid,)).fetchone()[0])
    def test_03_suppressed_prospect_cannot_enter_queue(self):
        self.d.execute('INSERT INTO mm_holds VALUES(?,?)',(self.bid,'fixture hold'))
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute("INSERT INTO mm_messages(business_id,evidence_id,recipient,body,digest,kind,created_at) VALUES(?,?,?,?,?,'followup',?)",(self.bid,self.eid,self.address,BODY,'new',c.now()))
    def test_04_duplicate_payment_cannot_inflate_revenue(self):
        pid,rid=self.pay()
        with self.assertRaises(sqlite3.IntegrityError):c.cash(self.d,self.bid,75000,rid)
        self.assertEqual(o.metrics(self.d)['net_received_nzd'],750)
    def test_05_historical_unverified_sends_excluded(self):
        self.assertEqual(o.metrics(self.d)['verified_sends'],0);self.assertEqual(o.metrics(self.d)['legacy_claimed_sends_unverified'],3)
    def test_06_failed_receipt_recording_does_not_become_sent(self):
        self.approve()
        with self.assertRaises(ValueError):c.record_sent(self.d,self.mid,999999)
        self.assertIsNone(self.d.execute('SELECT sent_at FROM mm_messages WHERE id=?',(self.mid,)).fetchone()[0])
    def test_07_crm_transitions_have_timestamps_and_events(self):
        self.d.execute("UPDATE mm_deals SET stage='AUDITED',updated_at='2000-01-01' WHERE business_id=?",(self.bid,))
        self.assertTrue(c.fresh(self.d.execute('SELECT updated_at FROM mm_deals WHERE business_id=?',(self.bid,)).fetchone()[0]));self.assertTrue(self.d.execute("SELECT 1 FROM mm_events WHERE business_id=? AND action='stage_transition'",(self.bid,)).fetchone())
    def test_08_proposal_requires_approval(self):
        pid=self.proposal()
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('UPDATE mm_proposals SET sent_at=? WHERE id=?',(c.now(),pid))
    def test_09_status_uses_zero_models_and_network(self):
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')),patch.object(o,'model_request',side_effect=AssertionError('model forbidden')):
            self.assertEqual(o.run_day(self.d,False)['model_calls'],0)
    def test_10_daily_operator_does_not_send_or_change_crm(self):
        before=[tuple(r) for r in self.d.execute('SELECT * FROM mm_deals')]
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):result=o.run_day(self.d)
        self.assertEqual(result['external_sends'],0);self.assertEqual(before,[tuple(r) for r in self.d.execute('SELECT * FROM mm_deals')]);self.assertTrue((self.r/'reports/daily-operator/dashboard.json').is_file())
    def test_11_every_hermes_model_invocation_logged(self):
        self.skipTest('BLOCKED: legacy/global Hermes calls cannot be reconciled to MoneyMachine agent_runs. Separate test covers all new local model requests.')
    def test_12_retired_entrypoints_and_empty_artifacts_fail(self):
        for name in ('seed_data.py','mark_sent.py','fix_contacts.py'):
            p=PACKAGE/'scripts'/name
            run=subprocess.run([sys.executable,str(p)],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(run.returncode,0);self.assertIn('BLOCKED',run.stderr+run.stdout)
        self.demo.write_text('')
        with self.assertRaises(ValueError):o.demo_qa(self.d,self.bid,self.demo)
    def test_13_migration_requires_verified_restorable_backup(self):
        with self.assertRaises(ValueError):c.migrate(self.d,self.r/'missing')
        backupdb=self.backup/'money_machine.db'
        with sqlite3.connect(backupdb) as b:self.assertEqual(b.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_14_paid_routes_fail_closed(self):
        x=i.model_request(self.d,'expensive/paid-model','nous','fixture');self.assertEqual(x['model_calls'],0);self.assertEqual(x['status'],'blocked');self.assertIn('not permitted',x['reason'])
    def test_15_discovery_to_proposal_without_unauthorized_send(self):
        c.change_stage(self.d,self.bid,'VERIFIED','Evidence reviewed');c.change_stage(self.d,self.bid,'AUDITED','Scope fixture');c.change_stage(self.d,self.bid,'DRAFT_READY','Review fixture');self.proposal();c.change_stage(self.d,self.bid,'PROPOSAL_READY','Human review')
        self.assertEqual(o.metrics(self.d)['verified_sends'],0);self.assertEqual(self.d.execute('SELECT stage FROM mm_deals WHERE business_id=?',(self.bid,)).fetchone()[0],'PROPOSAL_READY')
    def test_16_suppression_overrides_approval(self):
        h=self.approve();rid=self.proof('send',self.mid,h);self.d.execute('INSERT INTO mm_suppression VALUES(?,?,?)',(self.address,'fixture',c.now()))
        with self.assertRaises(ValueError):c.record_sent(self.d,self.mid,rid)
        self.assertIsNone(self.d.execute('SELECT approved_hash FROM mm_messages WHERE id=?',(self.mid,)).fetchone()[0])
    def test_17_recipient_change_invalidates_approval(self):
        self.approve();self.d.execute('UPDATE mm_messages SET recipient=? WHERE id=?',('other@fixture.example.invalid',self.mid));self.assertIsNone(self.d.execute('SELECT approved_hash FROM mm_messages WHERE id=?',(self.mid,)).fetchone()[0])
    def test_18_price_change_invalidates_proposal_approval(self):
        pid=self.proposal();self.approve(True,pid);self.d.execute('UPDATE mm_proposals SET price_cents=99900 WHERE id=?',(pid,));self.assertIsNone(self.d.execute('SELECT approved_hash FROM mm_proposals WHERE id=?',(pid,)).fetchone()[0])
    def test_19_duplicate_send_protection(self):
        rid=self.sent()
        with self.assertRaises(ValueError):c.record_sent(self.d,self.mid,rid)
        self.assertEqual(o.metrics(self.d)['verified_sends'],1)
    def test_20_stale_and_future_evidence_block_approval(self):
        for stamp in ('2000-01-01','2099-01-01'):
            self.d.execute('UPDATE mm_evidence SET checked_at=? WHERE id=?',(stamp,self.eid))
            with self.assertRaises(ValueError):self.approve()
    def test_21_missing_contact_source_blocks_approval(self):
        self.d.execute('DELETE FROM mm_contact_evidence WHERE business_id=?',(self.bid,))
        with self.assertRaises(ValueError):self.approve()
    def test_22_broken_demo_blocks_draft_ready(self):
        self.demo.write_text('<html>broken</html>')
        with self.assertRaises(ValueError):c.change_stage(self.d,self.bid,'DRAFT_READY','Attempt')
    def test_23_revenue_requires_payment_evidence(self):
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('INSERT INTO mm_cash(business_id,amount_cents,receipt,received_at) VALUES(?,?,?,?)',(self.bid,75000,'made up',c.now()))
    def test_24_refunds_are_excluded_from_net_received(self):
        pid,rid=self.pay();rr=self.proof('refund',pid,cents=37500);c.refund(self.d,pid,37500,rr);self.assertEqual(o.metrics(self.d)['net_received_nzd'],375)
        rr=self.proof('refund',pid,cents=50000)
        with self.assertRaises(sqlite3.IntegrityError):c.refund(self.d,pid,50000,rr)
    def test_25_failed_job_cannot_advance_crm(self):
        i.claim_job(self.d,'failure','status',self.bid);i.finish_job(self.d,'failure',{'step':1},'fixture failure');self.assertEqual(self.d.execute('SELECT stage FROM mm_deals WHERE business_id=?',(self.bid,)).fetchone()[0],'DISCOVERED')
    def test_26_interrupted_job_resumes_checkpoint_with_retry_limit(self):
        i.claim_job(self.d,'resume','status');self.d.execute("UPDATE mm_jobs SET checkpoint='{"+'"step":1'+"}',lease_until='2000-01-01' WHERE job_key='resume'")
        j=i.claim_job(self.d,'resume','status');self.assertEqual(json.loads(j['checkpoint']),{'step':1});self.assertEqual(j['attempts'],2)
        self.d.execute("UPDATE mm_jobs SET attempts=3,lease_until='2000-01-01' WHERE job_key='resume'")
        with self.assertRaises(ValueError):i.claim_job(self.d,'resume','status')
    def test_27_duplicate_prospect_is_flagged(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            o.main(['intake','--name','Acceptance Fixture','--url','https://fixture.example.invalid','--region','fixture','--source','https://fixture.example.invalid'])
    def test_28_budget_cannot_record_positive_paid_cost(self):
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute("INSERT INTO mm_model_invocations(run_key,model,provider,purpose_hash,status,cost_usd,created_at) VALUES('x','paid','nous','x','started',1,?)",(c.now(),))
    def test_29_unavailable_free_model_fails_without_fallback(self):
        x=i.model_request(self.d,'does-not-exist:free','nous','fixture');self.assertEqual((x['status'],x['model_calls'],x['cost_usd']),('blocked',0,0))
    def test_30_send_gates_survive_connection_restart(self):
        h=self.approve();self.d.commit()
        with sqlite3.connect(self.path) as raw:
            with self.assertRaises(sqlite3.Error):raw.execute('UPDATE mm_messages SET sent_at=? WHERE id=?',(c.now(),self.mid))
    def test_31_mixed_legacy_timestamp_formats_supported(self):
        self.assertEqual(c.timestamp('2026-09-07 14:11:05'),c.timestamp('2026-09-07T14:11:05Z'));self.assertFalse(c.fresh('not a timestamp'))
    def test_32_refuted_or_partial_evidence_cannot_approve(self):
        for status in ('refuted','partial','unverified'):
            self.d.execute('UPDATE mm_evidence_meta SET status=? WHERE evidence_id=?',(status,self.eid))
            with self.assertRaises(ValueError):self.approve()
    def test_33_evidence_capture_tampering_blocks_approval(self):
        self.capture.write_text('changed')
        with self.assertRaises(ValueError):self.approve()
    def test_34_ev_formula_and_zero_cost_handling(self):
        a={'p_reply':[.1,.2],'p_conversation_given_reply':[.5,.5],'p_win_given_conversation':[.2,.4],'deal_nzd':[750,1000],'gross_margin':[.5,.8],'human_hours':[1,2]}
        x=i.expected_value(a);self.assertEqual(x['ev_nzd'],[3.75,32]);self.assertEqual(x['ev_per_human_hour_nzd'],[1.88,32]);self.assertIsNone(x['ev_per_ai_dollar'])
        a['human_hours']=[0,1]
        with self.assertRaises(ValueError):i.expected_value(a)
    def test_35_scoring_refuted_evidence_zeroes_priority(self):
        a={'p_reply':[.1,.2],'p_conversation_given_reply':[.5,.5],'p_win_given_conversation':[.2,.4],'deal_nzd':[750,1000],'gross_margin':[.5,.8],'human_hours':[1,2]}
        self.d.execute("UPDATE mm_evidence_meta SET status='refuted' WHERE evidence_id=?",(self.eid,));x=i.score(self.d,self.bid,self.eid,{k:100 for k in i.WEIGHTS},a);self.assertEqual(x['score'],0);self.assertEqual(x['ev_nzd'],[0,0])
    def test_36_pricing_floor_and_scope(self):
        p=i.pricing('lead_capture',[4,8]);self.assertGreaterEqual(p['floor_nzd'],9*65);self.assertLessEqual(p['floor_nzd'],p['recommended_nzd']);self.assertLess(p['recommended_nzd'],p['premium_nzd'])
    def test_37_learning_does_not_invent_outcomes(self):
        x=i.learn(self.d);self.assertEqual(x['verified_observations'],0);self.assertEqual(x['winners'],[]);self.assertIn('Insufficient',x['conclusion'])
    def test_38_model_attempts_log_each_rejection(self):
        before=self.d.execute('SELECT count(*) FROM mm_model_invocations').fetchone()[0]
        for model in ('valid:free','paid','unknown:free'):i.model_request(self.d,model,'nous','fixture')
        self.assertEqual(self.d.execute('SELECT count(*) FROM mm_model_invocations').fetchone()[0],before+3);self.assertEqual(self.d.execute('SELECT sum(model_calls) FROM mm_model_invocations').fetchone()[0],0)
    def test_39_payment_receipt_file_tampering_excluded(self):
        pid,rid=self.pay();r=self.d.execute('SELECT * FROM mm_receipts WHERE id=?',(rid,)).fetchone();Path(r['artifact_path']).write_text('tampered');self.assertEqual(o.metrics(self.d)['net_received_nzd'],0)
    def test_40_live_suppressed_businesses_stay_suppressed(self):
        for bid in (4,13,14):
            with self.assertRaises(ValueError):c.change_stage(self.d,bid,'DISCOVERED','Attempt')
        self.assertEqual(self.d.execute('SELECT count(*) FROM mm_holds WHERE business_id IN (4,13,14)').fetchone()[0],3)
    def test_41_receiptless_direct_sent_stage_blocked(self):
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute("UPDATE mm_deals SET stage='SENT' WHERE business_id=?",(self.bid,))
    def test_42_revenue_legacy_table_cannot_bypass_cash_proof(self):
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('INSERT INTO revenue(collected_nzd) VALUES(750)')
    def test_43_full_approval_receipt_path_works_in_fixture(self):
        self.sent();self.assertEqual(o.metrics(self.d)['verified_sends'],1);self.assertEqual(self.d.execute('SELECT stage FROM mm_deals WHERE business_id=?',(self.bid,)).fetchone()[0],'SENT')
    def test_44_external_provider_receipts_independently_verified(self):
        self.skipTest('BLOCKED: no live mail/bank receipt supplied or independent read-only provider verifier connected; local attestation importer is tested separately.')

    def test_45_unsubscribe_after_sent_is_recordable_and_suppresses(self):
        self.sent();rid=self.proof('reply',self.mid);i.record_reply(self.d,self.mid,'unsubscribe',rid)
        self.assertEqual(self.d.execute('SELECT stage FROM mm_deals WHERE business_id=?',(self.bid,)).fetchone()[0],'SUPPRESSED')
    def test_46_public_email_alone_is_not_permission(self):
        self.d.execute('UPDATE mm_contact_evidence SET permission_verified_by=NULL WHERE business_id=?',(self.bid,))
        with self.assertRaises(ValueError):self.approve()
    def test_47_new_evidence_invalidates_approval(self):
        self.approve();c.record_evidence(self.d,self.bid,'https://fixture.example.invalid','New finding','Fixture',self.capture,'refuted','rendered_fixture',.9)
        with self.assertRaises(ValueError):c.evidence(self.d,self.eid,self.bid)
        self.assertIsNone(self.d.execute('SELECT approved_hash FROM mm_messages WHERE id=?',(self.mid,)).fetchone()[0])
    def test_48_reply_opportunity_ranks_before_cleanup(self):
        self.sent();rid=self.proof('reply',self.mid);i.record_reply(self.d,self.mid,'positive',rid);q=o.run_day(self.d,False)['human_queue'];self.assertEqual((q[0]['id'],q[0]['priority']),(self.bid,1))
    def test_49_active_job_cannot_be_claimed_twice(self):
        i.claim_job(self.d,'only-one','status')
        with self.assertRaises(ValueError):i.claim_job(self.d,'only-one','status')
    def test_50_experiment_assignment_stable_and_unverified_excluded(self):
        a=i.assign_experiment(self.d,self.mid,'fixture','conversion','fixture','500-1000','plain','local');b=i.assign_experiment(self.d,self.mid,'fixture','conversion','fixture','500-1000','plain','local')
        self.assertEqual(a,b);self.assertEqual(i.learn(self.d)['verified_observations'],0)
    def test_51_migration_idempotent(self):
        self.d.commit();before=self.d.execute('SELECT count(*) FROM mm_migrations').fetchone()[0];c.migrate(self.d,self.backup);self.assertEqual(self.d.execute('SELECT count(*) FROM mm_migrations').fetchone()[0],before)
    def test_52_receipt_envelope_rejects_arbitrary_claims(self):
        p=self.r/'envelope.json';p.write_text('{"kind":"payment","external_id":"invented"}')
        with self.assertRaises(ValueError):c.import_receipt(self.d,p)
    def test_53_sent_record_cannot_be_erased(self):
        self.sent()
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('UPDATE mm_messages SET sent_at=NULL,send_receipt=NULL WHERE id=?',(self.mid,))
    def test_54_approval_cannot_be_manufactured_from_plain_fields(self):
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute("UPDATE mm_messages SET approved_hash=digest,approval_ref='made-up',approved_by='Impersonator' WHERE id=?",(self.mid,))
    def test_55_model_cli_failure_keeps_log_and_nonzero_exit(self):
        self.d.commit()
        run=subprocess.run([sys.executable,str(PACKAGE/'scripts/mm_operator.py'),'model-request','--model','test:free','--provider','nous','--purpose','fixture'],capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,2);self.assertEqual(self.d.execute('SELECT count(*) FROM mm_model_invocations WHERE model=?',('test:free',)).fetchone()[0],1)
    def test_56_status_cli_persists_no_fixture_changes(self):
        self.d.commit();before=self.d.execute('SELECT count(*) FROM mm_events').fetchone()[0]
        run=subprocess.run([sys.executable,str(PACKAGE/'scripts/mm_operator.py'),'status'],capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(json.loads(run.stdout)['model_calls'],0);self.assertEqual(before,self.d.execute('SELECT count(*) FROM mm_events').fetchone()[0])

    def test_57_raw_stage_update_cannot_bypass_demo_gate(self):
        self.demo.write_text('broken')
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute("UPDATE mm_deals SET stage='DRAFT_READY' WHERE business_id=?",(self.bid,))
    def test_58_raw_approval_update_requires_fresh_evidence(self):
        h=self.approve();rid=self.proof('approval',self.mid,h);self.d.execute("UPDATE mm_evidence SET checked_at='2000-01-01' WHERE id=?",(self.eid,))
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('UPDATE mm_messages SET approved_hash=?,approval_ref=?,approved_by=? WHERE id=?',(h,str(rid),'Human Fixture',self.mid))

class JsonResult(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.records=[]
    def startTest(self,test):self.started=time.perf_counter();super().startTest(test)
    def record(self,test,status,detail):self.records.append({'test':test._testMethodName,'status':status,'elapsed_ms':round((time.perf_counter()-self.started)*1000,2),'setup':'Disposable live SQLite snapshot, synthetic independent prospect and artifacts','expected':'Invariant enforced; no real send, payment or model call','actual':detail,'evidence':str(Path(__file__).resolve())+':'+str(getattr(Acceptance,test._testMethodName).__code__.co_firstlineno)})
    def addSuccess(self,test):super().addSuccess(test);self.record(test,'PASS','Behavioral assertions passed')
    def addFailure(self,test,err):super().addFailure(test,err);self.record(test,'FAIL',self._exc_info_to_string(err,test))
    def addError(self,test,err):super().addError(test,err);self.record(test,'FAIL',self._exc_info_to_string(err,test))
    def addSkip(self,test,reason):super().addSkip(test,reason);self.record(test,'BLOCKED',reason)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance);result=unittest.TextTestRunner(verbosity=2,resultclass=JsonResult).run(suite)
    output=Path(os.environ.get('MM_TEST_RESULTS',str(PACKAGE/'reports/acceptance-results.json')));output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'generated_at':c.now(),'source_database':str(SOURCE),'fixture_policy':'Every test uses its own temporary backup; real DB never mutated','counts':{s:sum(r['status']==s for r in result.records) for s in ('PASS','FAIL','BLOCKED')},'tests':result.records},indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
