"""Synthetic policy regressions, kept separate from real golden accuracy."""
import copy
import datetime as dt
import html
import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
import mm_email as e
from mm_email_network import smtp_evidence

ROOT = Path(__file__).resolve().parents[1]


def page(body, url='https://koruplumbing.co.nz/contact', name='Koru Plumbing', stamp=None, **extra):
    raw = ('<html><title>' + name + ' Auckland</title><h1>' + name + '</h1><p>Auckland</p>' + body + '</html>').encode()
    meta = {'url': url, 'requested_url': url, 'title': name, 'captured_at': stamp or e.utcnow(), 'sha256': e.hash_bytes(raw), 'path': 'synthetic.capture', **extra}
    return e.parse_page(meta, raw)


def good_dns(**extra):
    return {'domain_resolves': True, 'mx_present': True, 'mx_hosts': ['mx.koru.co.nz'], 'domain_accepts_mail': True, 'status': 'mx', 'checked_at': e.utcnow(), **extra}


class EmailUnit(unittest.TestCase):
    def test_normalization_and_obfuscation(self):
        self.assertEqual(e.normalize_email('  Owner(at)Example.CO.NZ  ')[0], 'Owner@example.co.nz')
        self.assertEqual(e.normalize_email('office [at] koru [dot] co [dot] nz')[0], 'office@koru.co.nz')
        self.assertIsNone(e.normalize_email('hello@bücher.de')[1])
        for bad in ('a..b@koru.co.nz', 'a@b', 'user\n@koru.co.nz', 'logo@2x.png', 'info@blizzard.co.n z', 'john@company.co.nz.evil.invalid', 'a@koru.co.nz,b@koru.co.nz'):
            with self.subTest(bad=bad): self.assertIsNotNone(e.normalize_email(bad)[1])

    def test_domain_psl_and_private_suffix(self):
        self.assertEqual(e.root_domain('https://WWW.Example.CO.NZ/contact'), 'example.co.nz')
        self.assertEqual(e.root_domain('https://example.co.nz.evil.com'), 'evil.com')
        self.assertNotEqual(e.root_domain('one.github.io'), e.root_domain('two.github.io'))

    def test_synthetic_taxonomy(self):
        cases = json.loads((ROOT / 'tests/fixtures/email_regressions.json').read_text())['cases']
        for case in cases:
            with self.subTest(case=case['id']):
                business = {'id': 1, 'name': 'Koru Plumbing', 'region': 'Auckland', 'public_website': 'https://koruplumbing.co.nz/'}
                stamp = (dt.datetime.now(e.UTC) - dt.timedelta(days=case.get('age_days', 0))).isoformat()
                pattern = case.get('method') == 'CANDIDATE_PATTERN_DERIVED'
                addr = case['email']; body = '<form></form>' if not addr or pattern else '<p>' + html.escape(case.get('context', 'Contact email:') + ' ' + addr) + '</p>'
                p = page(body, url=case.get('source', 'https://koruplumbing.co.nz/contact'), name=case.get('site_name', 'Koru Plumbing'), stamp=stamp)
                if case.get('redirect'): p['requested_url'] = 'https://koruplumbing.co.nz/'; p['url'] = case['redirect']; p['title'] = 'Different Company'; p['headings'] = ['Different Company']; p['text'] = 'Different Company Auckland'
                identity = e.identify(business, [page('<p>Contact us</p>'), p] if case.get('source') else [p])
                if not addr:
                    self.assertEqual(e.evaluate(business, [p])['selection_status'], case['expected']); continue
                dns = good_dns()
                if case.get('dns') in ('no_mx', 'null_mx'): dns.update(mx_present=False, domain_accepts_mail=False, mx_hosts=[], status=case['dns'])
                elif case.get('dns') == 'unknown': dns.update(mx_present=None, domain_accepts_mail=None, mx_hosts=[], status='unknown')
                # Direct API validation also checks malformed raw candidates that
                # extraction correctly refuses to parse into a complete mailbox.
                candidate = {'email': addr, 'method': case.get('method', 'observed'), 'observations': p['observations']}
                normalized = e.normalize_email(addr)[0]
                candidate['observations'] = [o for o in candidate['observations'] if o['email'] == normalized]
                smtp = {'result': case.get('smtp', 'not_probed'), 'catch_all_status': case.get('catch_all', 'unknown'), 'checked_at': e.utcnow()}
                result = e.verification(candidate, identity, dns, smtp, case.get('suppressed', False), {'name': case['person']} if case.get('person') else None)
                self.assertEqual(result['confidence_label'], case['expected'], result)

    def test_hidden_scripts_assets_comments_never_become_evidence(self):
        p = page('<script>var mail="spy@koruplumbing.co.nz";</script><!-- cached@123, a@koruplumbing.co.nz --><img src="logo@2x.png"><input placeholder="name@domain.com"><p hidden>secret@koruplumbing.co.nz</p>')
        self.assertEqual(p['observations'], [])

    def test_fragment_not_repaired_mailto_intact(self):
        p = page('<p>info@blizzard.co.n <span>z</span></p><a href="mailto:info@blizzard.co.nz">Email</a>')
        self.assertEqual({o['email'] for o in p['observations']}, {'info@blizzard.co.n', 'info@blizzard.co.nz'})
        self.assertIsNotNone(next(o for o in p['observations'] if o['email'].endswith('.n'))['syntax_error'])

    def test_cloudflare_decode_and_hash_tamper(self):
        addr='office@koruplumbing.co.nz'; key=37; encoded=bytes([key]+[ord(x)^key for x in addr]).hex()
        p=page('<a data-cfemail="'+encoded+'">[email protected]</a>')
        self.assertEqual(p['observations'][0]['email'],addr)
        with self.assertRaises(ValueError):e.parse_page({'sha256':'wrong'},b'bad')

    def test_catchall_and_unknown_never_confirm_mailbox(self):
        self.assertFalse(smtp_evidence(250,250)['mailbox_confirmed'])
        self.assertFalse(smtp_evidence(250)['mailbox_confirmed'])
        self.assertFalse(smtp_evidence(450,550)['mailbox_confirmed'])
        self.assertTrue(smtp_evidence(250,550)['mailbox_confirmed'])
        self.assertEqual(smtp_evidence(550,550)['result'],'rejected')
        for condition in ('greylisted','blocked','server_hides_status','temporary_failure'):
            self.assertFalse(smtp_evidence(condition=condition)['mailbox_confirmed'])

    def test_catchall_public_address_can_pass_attribution_but_not_mailbox(self):
        p=page('<p>Contact office@koruplumbing.co.nz</p>');i=e.identify({'name':'Koru Plumbing','region':'Auckland','public_website':p['url']},[p])
        v=e.verification({'email':'office@koruplumbing.co.nz','observations':p['observations']},i,good_dns(),smtp_evidence(250,250))
        self.assertEqual(v['confidence_label'],'VERIFIED_HIGH');self.assertEqual(v['mailbox_verification'],'inconclusive')

    def test_pattern_requires_identity_and_person_evidence(self):
        p=page('<p>Director Jane Smith. Contact us</p>');i=e.identify({'name':'Koru Plumbing','region':'Auckland','public_website':p['url']},[p])
        self.assertEqual(e.pattern_candidates(i,{'name':'Jane Smith'}),[])
        person={'name':'Jane Smith','role':'Director','evidence_url':p['url'],'evidence_date':e.utcnow()}
        self.assertEqual(e.pattern_candidates(i,person),[])
        candidates=e.pattern_candidates(i,person,pages=[p])
        self.assertEqual(candidates[0]['status'],'CANDIDATE')
        v=e.verification(candidates[0],i,good_dns(),smtp_evidence(250,550))
        self.assertEqual(v['confidence_label'],'CANDIDATE')

    def test_second_page_not_independent_source_and_free_mail(self):
        ps=[page('<p>Contact email: koruplumbing@gmail.com</p>',url='https://koruplumbing.co.nz/'+x) for x in ('contact','about')]
        b={'name':'Koru Plumbing','region':'Auckland','public_website':ps[0]['url']}
        r=e.evaluate(b,ps,{'gmail.com':good_dns()})
        self.assertEqual(r['selected']['confidence_label'],'VERIFIED_HIGH');self.assertEqual(r['selected']['source_count'],2);self.assertEqual(r['selected']['independent_source_count'],1)

    def test_wrong_named_person_and_employment_freshness(self):
        p=page('<p>Director Jane Smith: jane@koruplumbing.co.nz</p>');b={'name':'Koru Plumbing','region':'Auckland','public_website':p['url']}
        r=e.evaluate(b,[p],{'koruplumbing.co.nz':good_dns()},person={'name':'Jane Smith'})
        self.assertTrue(r['selected']['person_match'])
        self.assertIsNone(e.evaluate(b,[p],{'koruplumbing.co.nz':good_dns()},person={'name':'John Smith'})['selected'])

    def test_duplicate_urls_do_not_inflate_evidence(self):
        p=page('<p>Contact office@koruplumbing.co.nz</p>');b={'name':'Koru Plumbing','region':'Auckland','public_website':p['url']}
        r=e.evaluate(b,[p,p,p],{'koruplumbing.co.nz':good_dns()})
        self.assertEqual(r['selected']['source_count'],1);self.assertNotIn('second_official_page',r['selected']['score_components'])

    def test_disposable_email_hierarchy_check(self):
        # Exact domain match
        self.assertTrue(e.is_disposable_email('user@mailinator.com'))
        # Subdomain hierarchy check (parent domain in blocklist)
        self.assertTrue(e.is_disposable_email('user@mail.mailinator.com'))
        # Non-disposable domain should not be flagged
        self.assertFalse(e.is_disposable_email('user@koruplumbing.co.nz'))
        # Malformed email should not crash
        self.assertFalse(e.is_disposable_email('not-an-email'))

    def test_disposable_email_is_hard_rejected(self):
        p=page('<p>Contact office@koruplumbing.co.nz</p>');i=e.identify({'name':'Koru Plumbing','region':'Auckland','public_website':p['url']},[p])
        obs=email_obs='user@mailinator.com'
        p2=page('<p>Contact '+email_obs+'</p>')
        v=e.verification({'email':email_obs,'observations':p2['observations']},i,good_dns())
        self.assertEqual(v['disposable_status'],'known_disposable')
        self.assertEqual(v['confidence_label'],'REJECTED')
        self.assertIn('Disposable domain', v['rejection_reasons'])

    def test_valid_redirect_and_location_conflict(self):
        p=page('<p>Contact office@newkoru.co.nz</p>',url='https://newkoru.co.nz/contact',requested_url='https://koruplumbing.co.nz/')
        b={'name':'Koru Plumbing','region':'Auckland','public_website':'https://koruplumbing.co.nz/'}
        i=e.identify(b,[p]);self.assertEqual(i['canonical_root_domain'],'newkoru.co.nz')
        p['text']=p['text'].replace('Auckland','Wellington');self.assertNotEqual(e.identify(b,[p])['status'],'HIGH')

    def test_name_collision_with_conflicting_phone_and_unknown_directory(self):
        p=page('<p>Contact 09 123 4567 office@koruplumbing.co.nz</p>')
        b={'name':'Koru Plumbing','region':'Auckland','public_website':p['url'],'phone':'09 765 4321'}
        self.assertNotEqual(e.identify(b,[p])['status'],'HIGH')
        p=page('<p>Business directory — claim this business. Contact office@koruplumbing.co.nz</p>')
        self.assertEqual(e.identify(b,[p])['status'],'REJECTED')


    def test_blocklist_refresh_is_tls_and_checksum_fail_closed(self):
        payload = b"mailinator.com\nyopmail.com\n"
        expected = e.hash_bytes(payload)

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, _limit): return payload

        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / "blocklist.conf"
            with patch("urllib.request.urlopen", return_value=Response()) as opener:
                result = e.refresh_disposable_blocklist(
                    force=True,
                    destination=destination,
                    expected_sha=expected,
                )
            self.assertTrue(result["downloaded"])
            self.assertTrue(result["sha256_match"])
            self.assertEqual(destination.read_bytes(), payload)
            self.assertNotIn("context", opener.call_args.kwargs)

        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / "blocklist.conf"
            with patch("urllib.request.urlopen", return_value=Response()):
                result = e.refresh_disposable_blocklist(
                    force=True,
                    destination=destination,
                    expected_sha="0" * 64,
                )
            self.assertTrue(result["checksum_mismatch"])
            self.assertFalse(destination.exists())


if __name__ == '__main__': unittest.main()
