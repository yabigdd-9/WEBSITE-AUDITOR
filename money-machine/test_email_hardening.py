"""Regressions from observed policy failures; all data and actions are isolated."""
import datetime as dt
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
import test_acceptance as legacy
from test_email_finder import page, good_dns, ROOT
import mm_email as e
import mm_email_store as store
import mm_email_cli as cli


def frozen_case(cid):
    doc=json.loads((ROOT/'reports/email-observation-evidence/cases'/f'{cid}.json').read_text())
    pages=[e.parse_page(p,(ROOT/p['path']).read_bytes()) for p in doc['pages']]
    at=dt.datetime.fromisoformat(doc['result']['results'][0]['checked_at'])
    return doc,e.evaluate(doc['case']['business'],pages,doc['dns'],at=at)

# Frozen real-observation cases are a host-only evidence corpus. When absent
# (sandbox checkout), skip explicitly instead of erroring — Master Plan P4.
from mm_test_capabilities import HAS_EMAIL_CASE_FIXTURES
_CASES_ABSENT=("BLOCKED_FIXTURE: reports/email-observation-evidence/cases corpus "
               "not present in this environment")

@unittest.skipUnless(HAS_EMAIL_CASE_FIXTURES,_CASES_ABSENT)
class HardeningEvidence(unittest.TestCase):
    def test_real_privacy_only_admin_rejected_legitimate_office_retained(self):
        _,r=frozen_case('new-039');v={v['email']:v for v in r['results']}
        self.assertEqual(v['admin@skilledelectrical.co.nz']['confidence_label'],'REJECTED')
        self.assertEqual(v['admin@skilledelectrical.co.nz']['role_account'],'privacy/legal')
        self.assertEqual(r['selected']['email'],'office@skilledelectrical.co.nz')

    def test_real_mixed_branch_and_locations_pages(self):
        _,r=frozen_case('new-094');v={v['email']:v for v in r['results']}
        self.assertEqual(r['selected']['email'],'sales@urban.co.nz')
        for email in ('coromandel@urban.co.nz','rotorua@urban.co.nz'):
            self.assertEqual(v[email]['confidence_label'],'REJECTED')
            self.assertFalse(v[email]['business_match'])
        self.assertEqual(r['identity']['matched_branches'],['waikato'])

    def test_aliases_do_not_verify_freemail_or_inflate_score(self):
        body='<p>Contact email: koruplumbing@gmail.com</p>'
        ps=[page(body,url=url) for url in ('https://www.koruplumbing.co.nz/contact/','http://koruplumbing.co.nz/contact','https://koruplumbing.co.nz/contact?tracking=one')]
        b={'name':'Koru Plumbing','region':'Auckland','public_website':ps[0]['url']}
        r=e.evaluate(b,ps,{'gmail.com':good_dns()});v=r['results'][0]
        self.assertIsNone(r['selected']);self.assertEqual(v['source_count'],1)
        self.assertNotIn('second_official_page',v['score_components'])
        self.assertEqual(v['raw_source_url_count'],3)

    def test_local_part_and_smtp_cannot_invent_named_person(self):
        b={'name':'Koru Plumbing','region':'Auckland','public_website':'https://koruplumbing.co.nz/'}
        for body in ('<p>Email jane.smith@koruplumbing.co.nz</p>', '<p>Director email jane.smith@koruplumbing.co.nz</p>', '<p>Jane Smith jane.smith@koruplumbing.co.nz</p>'):
            for catchall in ('yes','no'):
                with self.subTest(body=body,catchall=catchall):
                    r=e.evaluate(b,[page(body)],{'koruplumbing.co.nz':good_dns()},{'jane.smith@koruplumbing.co.nz':{'result':'accepted','catch_all_status':catchall,'checked_at':e.utcnow()}},person={'name':'Jane Smith'})
                    self.assertIsNone(r['selected']);self.assertFalse(r['results'][0]['person_match'])

    def test_person_card_role_required_and_neighbour_not_borrowed(self):
        b={'name':'Koru Plumbing','region':'Auckland','public_website':'https://koruplumbing.co.nz/'}
        body='<div><h3>Jane Smith</h3><p>Director</p><div><ul><li><a href="mailto:jane@koruplumbing.co.nz"><img></a></li></ul></div></div><div><h3>John Smith</h3><p>Engineer</p><a href="mailto:john@koruplumbing.co.nz"><img></a></div>'
        r=e.evaluate(b,[page(body)],{'koruplumbing.co.nz':good_dns()},person={'name':'Jane Smith','role':'Director'})
        v={v['email']:v for v in r['results']}
        self.assertTrue(v['jane@koruplumbing.co.nz']['person_match'])
        self.assertFalse(v['john@koruplumbing.co.nz']['person_match'])
        self.assertIsNotNone(v['jane@koruplumbing.co.nz']['person_company_evidence']['contexts'])

    def test_general_contact_not_poisoned_by_separate_privacy_publication(self):
        b={'name':'Koru Plumbing','region':'Auckland','public_website':'https://koruplumbing.co.nz/'}
        p=page('<p>Contact admin@koruplumbing.co.nz for quotes.</p><p>For questions about our privacy policy email admin@koruplumbing.co.nz</p>')
        self.assertEqual(e.evaluate(b,[p],{'koruplumbing.co.nz':good_dns()})['selected']['email'],'admin@koruplumbing.co.nz')

    def test_unscoped_address_cannot_inherit_branch_identity(self):
        b={'name':'Koru Plumbing','region':'Auckland','public_website':'https://koruplumbing.co.nz/'}
        p=page('<p>Contact office@koruplumbing.co.nz</p><section><h2>Wellington branch</h2><p>Street address, Wellington branch office enquiries wellington@koruplumbing.co.nz</p><a href="/locations/wellington/">Branch page</a></section>')
        r=e.evaluate(b,[p],{'koruplumbing.co.nz':good_dns()})
        self.assertIsNone(r['selected'])

class HardeningDatabase(unittest.TestCase):
    setUp=legacy.Acceptance.setUp
    tearDown=legacy.Acceptance.tearDown
    def test_missing_production_receipt_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.d.execute("UPDATE email_release_policy SET mode='PRODUCTION',precision_receipt=NULL WHERE id=1")

    def test_replace_cannot_overwrite_event_or_archived_score(self):
        event = self.d.execute('SELECT * FROM mm_events ORDER BY id LIMIT 1').fetchone()
        with self.assertRaisesRegex(sqlite3.IntegrityError,'replacement blocked'):
            self.d.execute('INSERT OR REPLACE INTO mm_events VALUES(?,?,?,?,?)',
                           (event['id'],e.utcnow(),'replaced',self.bid,'tampered'))
        score = self.d.execute('SELECT * FROM mm_score_history ORDER BY id LIMIT 1').fetchone()
        with self.assertRaisesRegex(sqlite3.IntegrityError,'replacement blocked'):
            self.d.execute('INSERT OR REPLACE INTO mm_score_history VALUES(?,?,?,?,?,?,?)',
                           (score['id'],self.bid,self.eid,'{}','{}',e.utcnow(),e.utcnow()))
    def test_null_receipt_cannot_release_observation(self):
        self.d.execute("UPDATE email_release_policy SET mode='POST_DEPLOYMENT_OBSERVATION',precision_receipt=NULL WHERE id=1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.d.execute("UPDATE email_release_policy SET mode='PRODUCTION' WHERE id=1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.d.execute("UPDATE email_release_policy SET mode='PRODUCTION',precision_receipt=? WHERE id=1",('z'*64,))

    def test_observation_blocks_cli_and_storage_before_network_or_writes(self):
        self.d.execute("UPDATE email_release_policy SET mode='POST_DEPLOYMENT_OBSERVATION',precision_receipt=NULL WHERE id=1")
        before=list(self.d.iterdump())
        with patch.object(cli,'Crawler',side_effect=AssertionError('network not permitted')):
            with self.assertRaisesRegex(ValueError,'POST_DEPLOYMENT_OBSERVATION'):cli.find_one(self.d,self.bid)
            with self.assertRaisesRegex(ValueError,'POST_DEPLOYMENT_OBSERVATION'):cli.shadow(self.d,True)
        with self.assertRaisesRegex(ValueError,'POST_DEPLOYMENT_OBSERVATION'):store.persist(self.d,{})
        with self.assertRaisesRegex(ValueError,'POST_DEPLOYMENT_OBSERVATION'):store.require_email(self.d,self.bid,self.address)
        self.assertEqual(before,list(self.d.iterdump()))
        self.assertEqual(self.d.execute('SELECT count(*) FROM email_current_high').fetchone()[0],0)
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('UPDATE mm_messages SET approved_hash=digest WHERE id=?',(self.mid,))

    def test_misordered_event_insert_fails_raw_history_preserved(self):
        before=[tuple(x) for x in self.d.execute('SELECT * FROM mm_events ORDER BY id')]
        with self.assertRaisesRegex(sqlite3.IntegrityError,'invalid event fields'):
            self.d.execute('INSERT INTO mm_events VALUES(NULL,?,?,?,?)',('evidence_recorded',self.bid,e.utcnow(),'fixture'))
        self.assertEqual(before,[tuple(x) for x in self.d.execute('SELECT * FROM mm_events ORDER BY id')])
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('DELETE FROM mm_events')

    def test_score_delete_blocked_and_replace_history_survives(self):
        self.d.execute('INSERT INTO mm_scores VALUES(?,?,?,?,?)',(self.bid,self.eid,'{}','{"score":1}',e.utcnow()))
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('DELETE FROM mm_scores')
        self.d.execute('INSERT OR REPLACE INTO mm_scores VALUES(?,?,?,?,?)',(self.bid,self.eid,'{}','{"score":2}',e.utcnow()))
        self.d.execute('UPDATE mm_scores SET computed_json=? WHERE business_id=?',('{"score":3}',self.bid))
        saved={x[0] for x in self.d.execute('SELECT computed_json FROM mm_score_history WHERE business_id=?',(self.bid,))}
        self.assertEqual(saved,{'{"score":1}','{"score":2}'})
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('DELETE FROM mm_score_history')

if __name__=='__main__':unittest.main()
