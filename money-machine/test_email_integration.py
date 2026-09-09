"""Database and adapter tests on disposable snapshots; live data read-only."""
import contextlib
import copy
import json
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_acceptance as legacy
import mm_core as c
import mm_email as e
import mm_email_store as s
from mm_email_network import Crawler, DNSChecks
from test_email_finder import page, good_dns, ROOT
import dns.resolver


class EmailIntegration(unittest.TestCase):
    setUp = legacy.Acceptance.setUp
    tearDown = legacy.Acceptance.tearDown
    proof = legacy.Acceptance.proof
    approve = legacy.Acceptance.approve
    proposal = legacy.Acceptance.proposal

    def test_migration_idempotent_and_historical_tables_unchanged(self):
        before = [tuple(r) for r in self.d.execute('SELECT * FROM contacts')]
        result = s.migrate_email(self.d, self.backup)
        self.assertFalse(result['applied']); self.assertEqual(before, [tuple(r) for r in self.d.execute('SELECT * FROM contacts')])
        self.assertEqual(self.d.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.d.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_source_substring_root_cause_closed(self):
        p=self.r/'vendor.txt';p.write_text('Website developer: outsider@vendor.co.nz')
        with self.assertRaisesRegex(ValueError,'VERIFIED_HIGH'):
            c.record_contact(self.d,self.bid,'outsider@vendor.co.nz','https://directory.co.nz/listing',p,'unsupported')
        self.assertFalse(self.d.execute("SELECT 1 FROM mm_contact_evidence WHERE recipient='outsider@vendor.co.nz'").fetchone())

    def test_forged_capture_cannot_replace_valid_provenance(self):
        p=self.r/'forged.txt';p.write_text(self.address)
        with self.assertRaisesRegex(ValueError,'provenance'):
            c.record_contact(self.d,self.bid,self.address,'https://directory.co.nz/listing',p,'unsupported')

    def test_new_negative_check_blocks_old_approval(self):
        self.approve()
        v=self.d.execute('SELECT * FROM email_verifications WHERE candidate_id=(SELECT best_email_id FROM prospect_email_state WHERE prospect_id=?) ORDER BY id DESC',(self.bid,)).fetchone()
        fields=[x[1] for x in self.d.execute('PRAGMA table_info(email_verifications)') if x[1]!='id']
        data=dict(v);data.update(confidence_label='REJECTED',confidence_score=0,smtp_status='rejected')
        self.d.execute('INSERT INTO email_verifications('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',tuple(data[k] for k in fields))
        with self.assertRaises(ValueError):s.require_email(self.d,self.bid,self.address)
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('UPDATE mm_messages SET approved_hash=approved_hash WHERE id=?',(self.mid,))
        p=e.parse_page({'url':'https://fixture.example.co.nz','path':str(self.capture),'sha256':c.sha(self.capture.read_bytes()),'captured_at':c.now()},self.capture.read_bytes())
        recheck=e.evaluate(dict(c.business(self.d,self.bid)),[p],{'fixture.example.co.nz':good_dns()})
        s.persist(self.d,recheck,self.r)
        self.assertEqual(s.status(self.d,self.bid)['email'],'NO_VERIFIED_EMAIL')

    def test_append_only_evidence_and_verification(self):
        for table in ('email_evidence','email_verifications','email_candidates','email_identity_checks'):
            with self.subTest(table=table):
                with self.assertRaises(sqlite3.IntegrityError):self.d.execute('DELETE FROM '+table)
                with self.assertRaises(sqlite3.IntegrityError):self.d.execute('UPDATE '+table+' SET id=id')

    def test_pattern_and_medium_cannot_enter_sql_draft_queue(self):
        for address in ('guess@fixture.example.co.nz','medium@fixture.example.co.nz'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.d.execute("INSERT INTO mm_messages(business_id,evidence_id,recipient,body,digest,kind,created_at) VALUES(?,?,?,?,?,'followup',?)",(self.bid,self.eid,address,legacy.BODY,c.sha(address),c.now()))

    def test_suppression_both_addresses_and_businesses_persist_without_crm_change(self):
        before=[tuple(r) for r in self.d.execute('SELECT * FROM mm_deals')]
        # Engine/persistence rerun only changes email tables.
        p=e.parse_page({'url':'https://fixture.example.co.nz','path':str(self.capture),'sha256':c.sha(self.capture.read_bytes()),'captured_at':c.now()},self.capture.read_bytes())
        result=e.evaluate(dict(c.business(self.d,self.bid)),[p],{'fixture.example.co.nz':good_dns()})
        s.persist(self.d,result,self.r)
        self.assertEqual(before,[tuple(r) for r in self.d.execute('SELECT * FROM mm_deals')])
        self.d.execute('INSERT INTO contacts(business_id,address_or_channel,do_not_contact) VALUES(?,?,1)',(self.bid,self.address))
        s.persist(self.d,result,self.r)
        self.assertEqual(s.status(self.d,self.bid)['email'],'NO_VERIFIED_EMAIL')
        with self.assertRaises(ValueError):s.require_email(self.d,self.bid,self.address)

    def test_unsubscribe_cannot_be_reset(self):
        self.d.execute("UPDATE mm_contact_evidence SET unsubscribe_state='unsubscribed' WHERE business_id=?",(self.bid,))
        with self.assertRaises(ValueError):c.record_contact(self.d,self.bid,self.address,'https://fixture.example.co.nz',self.capture,'fixture')
        self.assertEqual(self.d.execute('SELECT unsubscribe_state FROM mm_contact_evidence WHERE business_id=?',(self.bid,)).fetchone()[0],'unsubscribed')

    def test_safe_rollback_switch_retains_history_and_holds_approval(self):
        counts={t:self.d.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('email_candidates','email_evidence','email_verifications')}
        self.d.executescript((ROOT/'migrations/003_email_finder_v2_rollback.sql').read_text())
        with self.assertRaises(ValueError):s.require_email(self.d,self.bid,self.address)
        with self.assertRaises(ValueError):self.approve()
        self.assertEqual(counts,{t:self.d.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in counts})
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute("UPDATE email_policy SET mode='shadow' WHERE id=1")

    def test_missing_modified_source_invalidates_gate(self):
        self.capture.write_text('Tampered source')
        self.assertEqual(s.status(self.d,self.bid)['email'],'NO_VERIFIED_EMAIL')
        with self.assertRaises(ValueError):self.approve()

    def test_raw_proposal_and_message_gates_survive_reconnect(self):
        self.d.commit();self.d.close();self.d=c.connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute('UPDATE mm_messages SET sent_at=? WHERE id=?',(c.now(),self.mid))
        with self.assertRaises(sqlite3.IntegrityError):self.d.execute("INSERT INTO mm_proposals(business_id,evidence_id,recipient,body,price_cents,digest,created_at) VALUES(?,?,?,?,?,?,?)",(self.bid,self.eid,'wrong@elsewhere.co.nz',legacy.BODY,75000,'wrongrecipient',c.now()))


class NetworkAdapters(unittest.TestCase):
    def test_bounded_crawl_cache_resume_and_first_party_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fake(url):
                calls.append(url)
                raw=b'<html><title>Koru Plumbing</title><h1>Koru Plumbing</h1><p>Auckland</p><a href="/contact">Contact</a><a href="https://vendor.co.nz/">Vendor</a><p>office@koruplumbing.co.nz</p></html>'
                return {'url':url,'sha256':e.hash_bytes(raw),'captured_at':e.utcnow(),'content_type':'text/html'},raw
            crawler=Crawler(Path(tmp),max_pages=2,max_requests=3,fetcher=fake)
            with patch('mm_email_network.time.sleep'):
                pages,errors=crawler.crawl('https://koruplumbing.co.nz/')
                self.assertEqual(len(pages),2);self.assertLessEqual(len(calls),3);self.assertFalse(any('vendor' in x for x in calls))
                crawler.crawl('https://koruplumbing.co.nz/');self.assertEqual(len(calls),2)

    def test_retry_budget_and_failure_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fail(url):calls.append(url);raise OSError('controlled timeout')
            with patch('mm_email_network.time.sleep'):
                pages,errors=Crawler(Path(tmp),max_pages=2,max_requests=3,fetcher=fail).crawl('https://koruplumbing.co.nz/')
            self.assertEqual(len(calls),2);self.assertFalse(pages);self.assertEqual(len(errors),2)
            self.assertTrue(list((Path(tmp)/'cache/email-v2').glob('*.json')))

    def test_dns_null_mx_nxdomain_no_mx_and_unknown(self):
        class MX:
            preference=0;exchange='.'
        class Resolver:
            def __init__(self,error=None):self.error=error
            def resolve(self,*args):
                if self.error:raise self.error
                return [MX()]
        for error,expected in ((None,'null_mx'),(dns.resolver.NXDOMAIN(),'nxdomain'),(dns.resolver.NoAnswer(),'no_mx'),(dns.resolver.LifetimeTimeout(),'unknown')):
            with self.subTest(expected=expected):
                r=DNSChecks(resolver=Resolver(error)).check('koruplumbing.co.nz');self.assertEqual(r['status'],expected)
                self.assertIsNot(r['domain_accepts_mail'],True)

    def test_ssrf_private_dns_never_opens_socket(self):
        from email_baseline_capture import get_public
        with patch('email_baseline_capture.socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]),patch('email_baseline_capture.socket.create_connection',side_effect=AssertionError('No socket permitted')):
            with self.assertRaises(ValueError):get_public('https://public.example.co.nz/')


if __name__=='__main__':unittest.main()
