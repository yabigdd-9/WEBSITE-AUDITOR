"""Behavioral repair checks. Synthetic cases stay in disposable directories."""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import mm_email as email
import mm_audit_workflow as flow

ROOT=Path(__file__).resolve().parents[1]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class Polish(unittest.TestCase):
    def case(self,folder,body='<input id="person" placeholder="Your name">'):
        raw=('<html><head><title>Koru Plumbing Auckland</title><meta name="viewport" content="width=device-width"></head><body><h1>Koru Plumbing</h1><p>Auckland</p><p>Contact office@koruplumbing.co.nz</p>'+body+'</body></html>').encode()
        root=Path(folder);(root/'cases').mkdir();(root/'capture.html').write_bytes(raw)
        stamp=dt.datetime.now(dt.timezone.utc);meta={'url':'https://koruplumbing.co.nz/contact','sha256':flow.sha(raw),'captured_at':stamp.isoformat(),'path':'capture.html','content_type':'text/html'}
        b={'name':'Koru Plumbing','region':'Auckland','public_website':meta['url']}
        dns={'koruplumbing.co.nz':{'domain_resolves':True,'mx_present':True,'mx_hosts':['mx.koru.co.nz'],'domain_accepts_mail':True,'status':'mx','checked_at':stamp.isoformat()}}
        result=email.evaluate(b,[email.parse_page(meta,raw)],dns,at=stamp)
        doc={'business':b,'pages':[meta],'dns':dns,'evaluated_at':stamp.isoformat(),'result':result}
        path=root/'cases/case.json';path.write_text(json.dumps(doc))
        (root/'rendered.html').write_bytes(raw)
        fields=[]
        for n in flow.BeautifulSoup(raw,'html.parser').select('input,textarea,select'):
            fields.append({'tag':n.name.upper(),'id':n.get('id',''),'name':n.get('name',''),'visible':True,'outer':str(n)})
        (root/'rendered.json').write_text(json.dumps({'url':meta['url'],'http_status':200,'dom_sha256':flow.sha(raw),'fields':fields,'limitation':'Synthetic visible DOM fixture'}))
        return path

    def test_full_chain_stops_before_any_external_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=self.case(tmp)
            with patch.object(socket,'socket',side_effect=AssertionError('No network')):
                p=flow.make_packet(case,Path(tmp)/'packet',Path(tmp)/'rendered.json')
            self.assertEqual(p['status'],'HUMAN_APPROVAL_REQUIRED');self.assertFalse(p['send_enabled']);self.assertFalse(p['human_approved'])
            self.assertEqual([s['status'] for s in p['stages']],['PASS']*4)
            p['offer']['evidence']=['INVENTED'];self.assertFalse(flow.judge(p)['evidence_supported'])
            p['human_approved']=True;self.assertFalse(flow.judge(p)['human_gate'])
            p['business_name']='Different Business';self.assertFalse(flow.proof(p)['business_name'])

    def test_static_and_hidden_fields_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=self.case(tmp)
            with self.assertRaisesRegex(ValueError,'QUALIFICATION'):
                flow.make_packet(case,Path(tmp)/'static')
            review=Path(tmp)/'rendered.json';r=json.loads(review.read_text())
            r['fields'][0]['visible']=False;review.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'QUALIFICATION'):
                flow.make_packet(case,Path(tmp)/'hidden',review)
            (Path(tmp)/'rendered.html').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'hash'):
                flow.make_packet(case,Path(tmp)/'bad',review)

    def test_capture_tampering_blocks_before_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=self.case(tmp);(Path(tmp)/'capture.html').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'hash'):flow.make_packet(case,Path(tmp)/'packet')
            self.assertFalse((Path(tmp)/'packet').exists())

    def test_hidden_duplicate_name_is_not_a_visible_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=self.case(tmp,'<input name="search" class="desktop"><input name="search" class="mobile">')
            review=Path(tmp)/'rendered.json';r=json.loads(review.read_text())
            r['fields'][1]['visible']=False;review.write_text(json.dumps(r))
            p=flow.make_packet(case,Path(tmp)/'packet',review)
            finding=next(f for f in p['audit_summary']['findings'] if f['code']=='UNNAMED_FIELDS')
            self.assertEqual(len(finding['detail']),1)
            self.assertNotIn('class="mobile"',finding['detail'][0])

    def test_email_alone_never_qualifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=self.case(tmp,'<label for="person">Your name</label><input id="person">')
            with self.assertRaisesRegex(ValueError,'QUALIFICATION'):flow.make_packet(case,Path(tmp)/'packet')

    def test_malformed_result_does_not_bypass_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=self.case(tmp);d=json.loads(case.read_text());d['result']['selected']['email']='invented@koruplumbing.co.nz';case.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'replay'):flow.load_case(case)

    def test_relocated_cli_and_desktop_runtime_match(self):
        runtime_env=dict(os.environ,MM_PYTHON=sys.executable)
        cli=subprocess.run([str(ROOT/'mm'),'--runtime'],capture_output=True,text=True,check=True,env=runtime_env)
        desktop=subprocess.run(['bash',str(ROOT/'money-machine/Daily Operator.command'),'--runtime'],capture_output=True,text=True,check=True,env=runtime_env)
        self.assertEqual(json.loads(cli.stdout),json.loads(desktop.stdout))
        with patch.dict('os.environ',{'MM_PYTHON':'/missing/python'}):
            r=subprocess.run([str(ROOT/'mm'),'--help'],capture_output=True,text=True)
        self.assertEqual(r.returncode,2);self.assertIn('BLOCKED_RUNTIME',r.stderr)

    def test_legacy_send_and_selftest_block_before_credentials(self):
        sys.path.insert(0,str(ROOT/'outreach'))
        sender=module('legacy_sender',ROOT/'outreach/send.py');smtp=module('legacy_smtp',ROOT/'outreach/catalyx_send.py')
        with patch.object(sender,'service',side_effect=AssertionError('No credentials')),patch.object(smtp,'_keychain_app_pw',side_effect=AssertionError('No keychain')):
            for call in (lambda:sender.send([],True),sender.selftest,lambda:smtp.send_email('fixture@example.invalid','x','y')):
                with self.assertRaisesRegex(PermissionError,'HUMAN_APPROVAL_REQUIRED'):call()

    def test_hermes_missing_nonzero_and_malformed_help(self):
        adapter=module('adapter',ROOT/'money-machine/scripts/hermes_adapter.py')
        self.assertEqual(adapter.inspect('/missing/hermes')['status'],'BLOCKED_MISSING')
        for returncode,output,status in [(7,'provider unavailable','FAILED'),(0,'nonsense','BLOCKED_INTERFACE')]:
            r=subprocess.CompletedProcess([],returncode,output,'fixture failure')
            with patch.object(adapter.subprocess,'run',return_value=r):
                self.assertEqual(adapter.inspect(sys.executable)['status'],status)

    def test_network_uncertainty_not_a_website_defect(self):
        detector=module('detector',ROOT/'engines/detect.py')
        page={'ok':True,'status':200,'final_url':'https://koruplumbing.co.nz','html':'<html><meta name="viewport"><title>Koru Plumbing Auckland</title><a href="/contact">Contact</a><a href="tel:0123456789">Phone</a></html>','bytes':160,'ms':20}
        denied={'ok':False,'status':403,'error':'HTTP 403'}
        with patch.object(detector,'check_ssl',return_value={'valid':None,'error':'timeout'}),patch.object(detector,'fetch',side_effect=[page,denied]):
            result=detector.detect('https://koruplumbing.co.nz')
        self.assertNotIn('NO_VALID_HTTPS',[d['code'] for d in result['defects']]);self.assertNotIn('BROKEN_LINKS',[d['code'] for d in result['defects']])
        self.assertEqual(len(result['errors']),2)

if __name__=='__main__':unittest.main()
