#!/usr/bin/env python3
"""WEBSITES/BUISNESSaudits: deterministic local operator. Never sends or calls a model."""
import argparse
import contextlib
import datetime as dt
from html.parser import HTMLParser
import html
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from mm_core import *
from mm_intelligence import *
# Keep the CLI's parser dependencies explicit.  The wildcard import above is
# retained for the legacy operator helpers, but command registration must not
# depend on it exposing a validation constant.
from mm_core import CLAIM_TYPES

class DemoParser(HTMLParser):
    def __init__(self):super().__init__();self.tags=[]
    def handle_starttag(self,tag,attrs):self.tags.append((tag,dict(attrs)))

def demo_qa(d,bid,path):
    business(d,bid);p=Path(path).resolve()
    if not p.is_file() or not p.stat().st_size:raise ValueError('Nonempty demo file required')
    text=p.read_text();a=DemoParser();a.feed(text);tags=a.tags
    labels={attrs.get('for') for tag,attrs in tags if tag=='label'}
    fields=[x for t,x in tags if t in ('input','select','textarea')]
    checks={
      'html_document':'<!doctype html' in text.lower(),
      'mobile_viewport':any(t=='meta' and v.get('name')=='viewport' for t,v in tags),
      'language':any(t=='html' and v.get('lang') for t,v in tags),
      'field_labels':all(x.get('id') in labels or x.get('aria-label') for x in fields),
      'local_only_csp':"connect-src 'none'" in text and "form-action 'none'" in text,
      'no_external_assets':not any(v.get('src','').startswith(('http','//')) for t,v in tags if t in ('script','iframe','img')),
      'no_form_destination':not any(v.get('action') for t,v in tags if t=='form'),
      'honest_demo_label':'local demonstration' in text.lower() and 'nothing is sent' in text.lower(),
      'no_fabricated_reviews':not any(x in text for x in ('Sarah M.','James T.','Michelle K.','★★★★★')),
      'visible_focus':':focus-visible' in text,
    }
    score=sum(checks.values())*10;passed=score>=80 and all(checks[k] for k in ['field_labels','local_only_csp','honest_demo_label','no_fabricated_reviews','no_form_destination'])
    data={'automated':checks,'limitations':'Static checks only. Visual/mobile/interaction review recorded separately; not proof of live integration.'}
    d.execute('INSERT INTO mm_demo_qa VALUES(?,?,?,?,?,?,?) ON CONFLICT(business_id) DO UPDATE SET path=excluded.path,file_hash=excluded.file_hash,score=excluded.score,checks_json=excluded.checks_json,passed=excluded.passed,checked_at=excluded.checked_at',(bid,str(p),sha(p.read_bytes()),score,json.dumps(data),int(passed),now()))
    return {'score':score,'passed':passed,**data}

def atomic_write(path,text):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+p.name,dir=p.parent)
    try:
        with os.fdopen(fd,'w') as f:f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def metrics(d):
    get=lambda sql:d.execute(sql).fetchone()[0]
    proven=[]
    for m in d.execute('SELECT * FROM mm_messages WHERE sent_at IS NOT NULL AND send_receipt IS NOT NULL'):
        try:receipt(d,m['send_receipt'],'send',m['business_id'],m['id'],digest(m['recipient'],m['body']));proven.append(m)
        except ValueError:pass
    revenue=0;refunds=0
    for c in d.execute('SELECT * FROM mm_cash'):
        try:
            r=receipt(d,c['receipt'],'payment',c['business_id'])
            if r['amount_cents']!=c['amount_cents'] or r['currency']!='NZD':continue
            revenue+=c['amount_cents']
        except ValueError:continue
    # Subtract recorded refunds even if a receipt file disappears; never inflate net.
    refunds=get('SELECT coalesce(sum(amount_cents),0) FROM mm_refunds')
    verified=0;fresh_legacy=0
    for row in d.execute('SELECT DISTINCT business_id FROM mm_evidence'):
        bid=row[0];eid=latest_evidence(d,bid)
        checked=d.execute('SELECT checked_at FROM mm_evidence WHERE id=?',(eid,)).fetchone()[0]
        fresh_legacy+=fresh(checked)
        try:evidence(d,eid,bid);verified+=1
        except ValueError:pass
    return {'real_prospects':get('SELECT count(*) FROM businesses WHERE is_dummy=0'),'fresh_legacy_observation_prospects':fresh_legacy,'independently_verified_current_claims':verified,'prospects_without_any_evidence':get('SELECT count(*) FROM businesses b WHERE is_dummy=0 AND NOT EXISTS(SELECT 1 FROM mm_evidence e WHERE e.business_id=b.id)'),
        'verified_sends':len(proven),'verified_replies':sum(human_reply_verified(d,m['id'],m['business_id'],m['reply']) for m in proven),
        'legacy_claimed_sends_unverified':get('SELECT count(*) FROM outreach WHERE sent_at IS NOT NULL'),
        'suppressed_businesses':get("SELECT count(*) FROM mm_deals WHERE stage='SUPPRESSED'"),'suppressed_addresses':get('SELECT count(*) FROM mm_suppression'),
        'active_drafts':get('SELECT count(*) FROM mm_messages WHERE sent_at IS NULL AND invalidated_reason IS NULL'),'invalidated_drafts':get('SELECT count(*) FROM mm_messages WHERE invalidated_reason IS NOT NULL'),
        'proposal_drafts':get('SELECT count(*) FROM mm_proposals WHERE sent_at IS NULL AND invalidated_reason IS NULL'),'gross_received_nzd':round(revenue/100,2),'refunded_nzd':round(refunds/100,2),'net_received_nzd':round(max(0,revenue-refunds)/100,2),
        'model_calls_this_workflow':0,'model_cost_this_workflow_usd':0,'models_enabled':False,
        'historical_billing_status':'Not reconciled against provider statements; zero ledger values are not proof of historical zero spend'}

def run_day(d,write=True):
    start=time.perf_counter();queue=[];blocked=[];stale=[]
    for b in d.execute('SELECT b.id,b.name,m.stage,m.next_action,m.due FROM businesses b JOIN mm_deals m ON m.business_id=b.id WHERE b.is_dummy=0'):
        bid=b['id'];name=b['name']
        try:eligible(d,bid)
        except ValueError as e:blocked.append({'id':bid,'name':name,'reason':str(e)});continue
        s=d.execute('SELECT * FROM mm_scores WHERE business_id=?',(bid,)).fetchone();ev=0
        if s:
            inputs=json.loads(s['inputs_json']);computed=score(d,bid,s['evidence_id'],**inputs);ev=computed['ev_per_human_hour_nzd'][0]
        replies=d.execute("SELECT m.id FROM mm_messages m JOIN mm_receipts r ON r.object_id=m.id AND r.business_id=m.business_id AND r.kind='reply' WHERE m.business_id=? AND m.reply IN ('positive','question','price_objection') AND m.sent_at IS NOT NULL LIMIT 1",(bid,)).fetchone()
        if replies:queue.append({'priority':1,'id':bid,'name':name,'action':REPLY_ACTIONS[d.execute('SELECT reply FROM mm_messages WHERE id=?',(replies[0],)).fetchone()[0]],'ev_hour_low':ev});continue
        p=d.execute('SELECT * FROM mm_proposals WHERE business_id=? AND sent_at IS NULL AND invalidated_reason IS NULL ORDER BY id DESC LIMIT 1',(bid,)).fetchone()
        m=d.execute('SELECT * FROM mm_messages WHERE business_id=? AND sent_at IS NULL AND invalidated_reason IS NULL ORDER BY id DESC LIMIT 1',(bid,)).fetchone()
        chosen=p or m
        if chosen:
            reasons=readiness(d,bid,chosen['evidence_id'],chosen['recipient'])
            if not reasons:
                priority=2 if p else (3 if m['kind']=='followup' and m['approved_hash'] else 4)
                queue.append({'priority':priority,'id':bid,'name':name,'action':'Human review of exact proposal' if p else 'Human review of exact outreach; no automatic send','ev_hour_low':ev});continue
            blocked.append({'id':bid,'name':name,'reason':'; '.join(reasons)})
        e=d.execute('SELECT * FROM mm_evidence WHERE business_id=? ORDER BY julianday(checked_at) DESC,id DESC LIMIT 1',(bid,)).fetchone()
        if not e or not fresh(e['checked_at']):stale.append({'id':bid,'name':name,'reason':'Missing' if not e else 'Expired'})
        # Diagnosis beats further demo work where the sales premise was refuted.
        priority=5 if bid==5 else 6 if e else 7
        queue.append({'priority':priority,'id':bid,'name':name,'action':b['next_action'] if e else 'Capture current website evidence; verify a commercial problem before offering work','ev_hour_low':ev})
    queue.sort(key=lambda x:(x['priority'],-x['ev_hour_low'],x['id']))
    email_contacts=[]
    if d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='email_policy'").fetchone():
        from mm_email_store import status as email_status
        for row in d.execute('SELECT id FROM businesses WHERE is_dummy=0 ORDER BY id').fetchall():
            contact=email_status(d,row[0]);selected=contact.get('selected') or {};identity=contact.get('identity') or {}
            email_contacts.append({'business_id':row[0],'business':contact['business'],'website':contact.get('website'),'canonical_domain':identity.get('canonical_root_domain'),'email':contact['email'],'confidence':contact.get('confidence'),'why':selected.get('reasons') or identity.get('reasons'),'evidence_count':selected.get('source_count',0),'verification':selected.get('confidence_label','NO_VERIFIED_EMAIL'),'catch_all':selected.get('catch_all_status','unknown'),'last_checked':contact.get('last_checked'),'human_review':'REQUIRED','outreach_eligible':contact.get('outreach_eligible',False)})
    data={'project':'WEBSITES/BUISNESSaudits','workspace':str(root()),'generated_at':now(),'metrics':metrics(d),'email_contacts':email_contacts,'pipeline_stages':dict(d.execute('SELECT stage,count(*) FROM mm_deals GROUP BY stage')),'human_queue':queue,'blocked':blocked,'missing_or_stale':stale,'next_revenue_action':queue[0] if queue else None,'elapsed_ms':round((time.perf_counter()-start)*1000,2),'model_calls':0,'external_sends':0}
    from mm_outreach import health as outreach_health
    data['outreach_self_audit']=outreach_health(d)
    if write:
        out=root()/'reports/daily-operator'
        atomic_write(out/'dashboard.json',json.dumps(data,indent=2))
        sections=''.join('<li><strong>'+html.escape(q['name'])+'</strong> — '+html.escape(q['action'])+'</li>' for q in queue)
        html_doc='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WEBSITES/BUISNESSaudits · Today</title><style>body{font:17px/1.6 system-ui;max-width:1000px;margin:32px auto;padding:20px;color:#16352c;background:#f4f7f5}li{margin:20px 0}pre{white-space:pre-wrap;background:white;padding:24px}h1{font-size:38px}</style><h1>WEBSITES/BUISNESSaudits · Today</h1><p>Human decisions only. Nothing is sent. Model execution is paused.</p><p>Net received: NZ$'+str(data['metrics']['net_received_nzd'])+' · Verified sends: '+str(data['metrics']['verified_sends'])+'</p><ol>'+sections+'</ol><h2>Records needing evidence</h2><pre>'+html.escape(json.dumps(blocked,indent=2))+'</pre></html>'
        email_rows=''.join('<tr><td>'+html.escape(x['business'])+'</td><td>'+html.escape(x['canonical_domain'] or 'Unconfirmed')+'</td><td>'+html.escape(x['email'])+'</td><td>'+html.escape(str(x['confidence'] or '—'))+'</td><td>'+str(x['evidence_count'])+'</td><td>Required</td></tr>' for x in email_contacts)
        html_doc=html_doc.replace('</html>','<h2>Verified contact evidence</h2><p>Public attribution with mail routing; mailbox existence and permission are separate. Use <code>mm email-status ID</code> for source evidence.</p><table><thead><tr><th>Business</th><th>Domain</th><th>Email</th><th>Confidence</th><th>Sources</th><th>Human review</th></tr></thead><tbody>'+email_rows+'</tbody></table></html>')
        html_doc=html_doc.replace('</html>','<h2>Outreach self-audit</h2><p>Copy issues: '+str(len(data['outreach_self_audit']['copy_issues']))+'. Delivery and bounce rates: unknown. No transport is connected.</p><p>Use <code>mm outreach-health</code> for details and <code>mm outreach-plan --brief PATH</code> for a relevant service portfolio.</p></html>')
        atomic_write(out/'index.html',html_doc)
        atomic_write(root()/'reports/DAILY_OPERATOR.md','# Current daily operator\n\nGenerated '+data['generated_at']+' by `mm run-day`.\n\n'+'\n'.join(f"{i+1}. **{q['name']}** — {q['action']}" for i,q in enumerate(queue))+'\n\nModel calls: 0. External sends: 0. Net received NZ$'+str(data['metrics']['net_received_nzd'])+'\n')
        atomic_write(root()/'reports/KPI_DASHBOARD.md','# Evidence-based KPI snapshot\n\n'+json.dumps(data['metrics'],indent=2)+'\n\nStages: '+json.dumps(data['pipeline_stages'])+'\n')
    return data

def doctor(d, profile='default'):
    import shutil
    import ast
    tools={}
    for name in ('hermes','python3','git','node','npm','npx','goose','opencode','gh','docker','himalaya'):
        p=shutil.which(name)
        tools[name]={'path':p,'status':'MISSING' if not p else 'EMPTY_STUB' if Path(p).stat().st_size==0 else 'PRESENT_NOT_EXECUTED'}
    broken=[]
    for p in (Path(__file__).resolve().parent/'scripts').glob('*.py'):
        try:
            if not p.stat().st_size:raise ValueError('Empty script')
            ast.parse(p.read_text())
        except (ValueError,SyntaxError) as e:broken.append({'path':str(p),'error':str(e)})
    return {'generated_at':now(),'profile':profile,'tools':tools,'broken_python':broken,'db_integrity':d.execute('PRAGMA integrity_check').fetchone()[0],'foreign_key_errors':[list(x) for x in d.execute('PRAGMA foreign_key_check')],'models_enabled':False,'model_calls':0,'limitation':'Read-only inventory. Presence does not prove a service works. Runtime processes and system cron may need separate host access.'}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='cmd',required=True)
    for cmd in ('daily','run-day','status','money','learn','backup','init','health','metrics','errors','queue','dead-letter','observability-snapshot'):s.add_parser(cmd)
    q=s.add_parser('doctor');q.add_argument('--profile',default='default')
    s.add_parser('obsidian-sync')
    s.add_parser('obsidian-status')
    q=s.add_parser('supervisor')
    q.add_argument('action',choices=['start','stop','restart','status','health','logs'])
    q.add_argument('--sleep',type=float,default=5)
    q.add_argument('--tail',type=int,default=50)
    q.add_argument('--timeout',type=float,default=15)
    q=s.add_parser('outreach-plan');q.add_argument('--brief',required=True)
    s.add_parser('polish-status')
    s.add_parser('module-status')
    q=s.add_parser('audit-packet');q.add_argument('--case',required=True);q.add_argument('--output',required=True);q.add_argument('--rendered-review')
    q=s.add_parser('outreach-audit');q.add_argument('--packet',required=True)
    q=s.add_parser('outreach-preflight');q.add_argument('id',type=int)
    q=s.add_parser('outreach-dsn');q.add_argument('--eml',required=True);q.add_argument('--recipient',required=True);q.add_argument('--original-message-id',required=True)
    s.add_parser('outreach-health')
    s.add_parser('transport-status')
    q=s.add_parser('transport-preflight');q.add_argument('--packet',required=True)
    s.add_parser('outcomes')
    q=s.add_parser('outcome-record');q.add_argument('id',type=int);q.add_argument('--outcome',required=True);q.add_argument('--evidence',required=True);q.add_argument('--sha256',required=True);q.add_argument('--actor',required=True);q.add_argument('--note',default='')
    q=s.add_parser('email-migrate');q.add_argument('--backup',required=True)
    q=s.add_parser('email-status');q.add_argument('id',type=int);q.add_argument('--json',action='store_true')
    q=s.add_parser('email-find');q.add_argument('id',type=int);q.add_argument('--json',action='store_true')
    q=s.add_parser('email-shadow');q.add_argument('--persist',action='store_true')
    s.add_parser('email-duplicates')
    q=s.add_parser('email-v1');q.add_argument('id',type=int)
    s.add_parser('email-rollback')
    q=s.add_parser('discover-import');q.add_argument('--file',required=True);q.add_argument('--region',default='');q.add_argument('--source',default='import');q.add_argument('--dry-run',action='store_true')
    q=s.add_parser('discover-search');q.add_argument('--query',required=True);q.add_argument('--region',required=True);q.add_argument('--endpoint',default='http://127.0.0.1:8888');q.add_argument('--limit',type=int,default=20);q.add_argument('--dry-run',action='store_true')
    q=s.add_parser('intake');q.add_argument('--name',required=True);q.add_argument('--url',required=True);q.add_argument('--region',required=True);q.add_argument('--source',required=True)
    q=s.add_parser('audit');q.add_argument('id',type=int);q.add_argument('--url',required=True);q.add_argument('--observation',required=True);q.add_argument('--limitation',required=True);q.add_argument('--capture',required=True);q.add_argument('--status',choices=['verified','partial','refuted','unverified'],required=True);q.add_argument('--method',required=True);q.add_argument('--confidence',type=float,required=True);q.add_argument('--claim-type',choices=CLAIM_TYPES,default='observed_fact')
    q=s.add_parser('contact');q.add_argument('id',type=int);q.add_argument('--recipient',required=True);q.add_argument('--url',required=True);q.add_argument('--capture',required=True);q.add_argument('--relevance',required=True)
    q=s.add_parser('draft');q.add_argument('id',type=int);q.add_argument('--recipient',required=True);q.add_argument('--body-file',required=True);q.add_argument('--parent',type=int)
    q=s.add_parser('review');q.add_argument('id',type=int);q.add_argument('--body-file',required=True);q.add_argument('--human',required=True);q.add_argument('--approval-receipt',type=int,required=True);q.add_argument('--proposal',action='store_true')
    q=s.add_parser('record-sent');q.add_argument('id',type=int);q.add_argument('--receipt',type=int,required=True);q.add_argument('--proposal',action='store_true')
    q=s.add_parser('receipt-import');q.add_argument('--envelope',required=True)
    q=s.add_parser('cash');q.add_argument('id',type=int);q.add_argument('--cents',type=int,required=True);q.add_argument('--receipt',type=int,required=True)
    q=s.add_parser('refund');q.add_argument('id',type=int);q.add_argument('--cents',type=int,required=True);q.add_argument('--receipt',type=int,required=True)
    q=s.add_parser('reply');q.add_argument('id',type=int);q.add_argument('--classification',choices=list(REPLY_ACTIONS),required=True);q.add_argument('--receipt',type=int,required=True)
    q=s.add_parser('suppress');q.add_argument('--address',required=True);q.add_argument('--reason',required=True)
    q=s.add_parser('stage');q.add_argument('id',type=int);q.add_argument('--stage',choices=STAGES,required=True);q.add_argument('--next-action',required=True);q.add_argument('--due')
    q=s.add_parser('quote');q.add_argument('id',type=int);q.add_argument('--recipient',required=True);q.add_argument('--body-file',required=True);q.add_argument('--price-nzd',type=int,required=True)
    q=s.add_parser('price');q.add_argument('--problem',choices=list(OFFERS),required=True);q.add_argument('--hours-low',type=float);q.add_argument('--hours-high',type=float)
    q=s.add_parser('score');q.add_argument('id',type=int);q.add_argument('--inputs',required=True)
    q=s.add_parser('demo-qa');q.add_argument('id',type=int);q.add_argument('--path',required=True)
    q=s.add_parser('model-request');q.add_argument('--model',required=True);q.add_argument('--provider',required=True);q.add_argument('--purpose',required=True)
    q=s.add_parser('experiment');q.add_argument('id',type=int);q.add_argument('--industry',required=True);q.add_argument('--problem',choices=ONTOLOGY,required=True);q.add_argument('--offer',required=True);q.add_argument('--price-band',required=True);q.add_argument('--style',required=True);q.add_argument('--demo-type',required=True)
    q=s.add_parser('run-job');q.add_argument('--key',required=True);q.add_argument('--kind',choices=['status','learn'],required=True)
    q=s.add_parser('pipeline-run');q.add_argument('--worker',action='append');q.add_argument('--limit',type=int,default=1)
    s.add_parser('pipeline-status')
    q=s.add_parser('pipeline-enqueue');q.add_argument('id',type=int);q.add_argument('--state',default='DISCOVERED')
    q=s.add_parser('pipeline-transition');q.add_argument('id',type=int);q.add_argument('--to',required=True);q.add_argument('--actor',required=True);q.add_argument('--reason',required=True)
    s.add_parser('pipeline-health')
    q=s.add_parser('approval-check');q.add_argument('id',type=int)
    q=s.add_parser('approval-decide');q.add_argument('approval_id',type=int);q.add_argument('--actor',required=True);q.add_argument('--reason',required=True)
    s.add_parser('model-routes')
    q=s.add_parser('agent-policy-check');q.add_argument('--file',required=True)
    q=s.add_parser('challenger-eval');q.add_argument('--golden',required=True);q.add_argument('--baseline',required=True);q.add_argument('--challenger',required=True);q.add_argument('--min-improvement',type=float,default=0.01)
    q=s.add_parser('model-plan');q.add_argument('--purpose',required=True)
    q=s.add_parser('deploy-check');q.add_argument('--candidate');q.add_argument('--execute',action='store_true')
    a=p.parse_args(argv)
    if a.cmd in ('health','metrics','errors','queue','dead-letter','observability-snapshot'):
        import mm_observability
        functions={
            'health':mm_observability.health,
            'metrics':mm_observability.metrics,
            'errors':mm_observability.errors,
            'queue':mm_observability.queue,
            'dead-letter':mm_observability.dead_letter,
            'observability-snapshot':mm_observability.write_snapshots,
        }
        result=functions[a.cmd]()
        print(json.dumps(result,indent=2,default=str));return 0
    if a.cmd in ('obsidian-sync','obsidian-status'):
        import mm_obsidian
        result=mm_obsidian.sync() if a.cmd=='obsidian-sync' else mm_obsidian.status()
        print(json.dumps(result,indent=2,default=str));return 0
    if a.cmd in ('transport-status','transport-preflight'):
        import mm_transport
        result=mm_transport.status() if a.cmd=='transport-status' else mm_transport.preflight_packet(json.loads(Path(a.packet).read_text()))
        print(json.dumps(result,indent=2,default=str));return 0
    if a.cmd in ('outcomes','outcome-record'):
        import mm_outcomes
        readonly=a.cmd=='outcomes'
        with contextlib.closing(connect(readonly=readonly)) as d:
            if a.cmd=='outcomes':
                result=mm_outcomes.summary(d)
            else:
                with d:
                    result=mm_outcomes.record(d,a.id,a.outcome,a.evidence,a.sha256,a.actor,a.note)
        print(json.dumps(result,indent=2,default=str));return 0
    if a.cmd=='polish-status':
        report=json.loads((root()/'reports/polish-status.json').read_text())
        report.update(workspace=str(root()),python=sys.executable,snapshot_only=True)
        print(json.dumps(report,indent=2));return 0
    if a.cmd=='module-status':
        import mm_module_registry
        print(json.dumps(mm_module_registry.status(),indent=2));return 0
    if a.cmd=='audit-packet':
        import mm_audit_workflow
        return mm_audit_workflow.main(['--case',a.case,'--output',a.output]+(['--rendered-review',a.rendered_review] if a.rendered_review else []))
    if a.cmd.startswith('outreach-'):
        import mm_outreach
        with contextlib.closing(connect(readonly=True)) as d:
            result=mm_outreach.cli(a,d)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 2 if (a.cmd=='outreach-audit' and not result['passed']) or (a.cmd=='outreach-plan' and result['planning_holds']) or a.cmd=='outreach-preflight' else 0
    if a.cmd.startswith('email-'):
        import mm_email_store as email_store
        import mm_email_cli as email_cli
        with contextlib.closing(connect(readonly=a.cmd in ('email-status','email-duplicates','email-v1'))) as d, d:
            if a.cmd=='email-migrate':result=email_store.migrate_email(d,a.backup)
            elif a.cmd=='email-status':result=email_store.status(d,a.id)
            elif a.cmd=='email-find':result=email_cli.find_one(d,a.id)
            elif a.cmd=='email-shadow':result=email_cli.shadow(d,a.persist)
            elif a.cmd=='email-duplicates':result=email_store.duplicate_entities(d)
            elif a.cmd=='email-v1':result={'business':dict(business(d,a.id)),'legacy_contacts':[dict(x) for x in d.execute('SELECT address_or_channel,source,last_verified,do_not_contact FROM contacts WHERE business_id=?',(a.id,))],'legacy_captures':[dict(x) for x in d.execute('SELECT recipient,source_url,checked_at,confidence FROM mm_contact_evidence WHERE business_id=?',(a.id,))],'email_status':'UNVERIFIED_LEGACY_VIEW','outreach_eligible':False,'note':'Historical confidence is a capture-only score; it is not email verification.'}
            elif a.cmd=='email-rollback':
                d.executescript((Path(__file__).resolve().parent/'003_email_finder_v2_rollback.sql').read_text())
                result={'mode':'v1_hold','history_retained':True,'new_approvals_held':True,'external_sends':0}
        print(email_cli.human_text(result) if a.cmd in ('email-status','email-find') and not a.json else json.dumps(result,indent=2))
        return 0
    if a.cmd in ('discover-import','discover-search'):
        import mm_discovery
        if a.cmd=='discover-import':
            candidates,rejected=mm_discovery.read_candidates(a.file,a.region,a.source)
        else:
            candidates=mm_discovery.searxng_candidates(a.query,a.region,a.endpoint,a.limit)
            rejected=[]
        with contextlib.closing(connect()) as d,d:
            result=mm_discovery.ingest(d,candidates,actor='mm-'+a.cmd,dry_run=a.dry_run)
        result['source_rejections']=rejected
        result['external_sends']=0
        print(json.dumps(result,indent=2,default=str));return 0
    if a.cmd=='backup':print(backup());return 0
    if a.cmd=='supervisor':
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from supervisor import cli as _sc
        result=_sc.COMMANDS[a.action](a)
        print(json.dumps(result,indent=2,default=str))
        return 0
    if a.cmd=='model-routes':
        import mm_model_router
        print(json.dumps({'routes':mm_model_router.routes_report(),'paid_allowed':False,'max_cost_usd':0,'fallback':'DEFER'},indent=2));return 0
    if a.cmd=='agent-policy-check':
        import mm_agent_policy
        assignments=json.loads(Path(a.file).read_text())
        print(json.dumps(mm_agent_policy.validate_assignments(assignments),indent=2));return 0
    if a.cmd=='challenger-eval':
        import mm_challenger
        result=mm_challenger.compare(
            mm_challenger.load_jsonl(a.golden),
            mm_challenger.load_jsonl(a.baseline),
            mm_challenger.load_jsonl(a.challenger),
            a.min_improvement,
        )
        print(json.dumps(result,indent=2));return 0
    if a.cmd in ('pipeline-run','pipeline-status','pipeline-enqueue','pipeline-transition','pipeline-health','approval-check','approval-decide','model-plan','deploy-check'):
        import mm_pipeline, mm_approval, mm_model_router, mm_workers
        readonly=a.cmd in ('approval-check',)
        with contextlib.closing(connect(readonly=readonly)) as d, d:
            mm_pipeline.migrate(d);mm_approval.migrate(d)
            if a.cmd=='pipeline-status':result=mm_pipeline.health(d)
            elif a.cmd=='pipeline-health':result=mm_pipeline.health(d)
            elif a.cmd=='pipeline-enqueue':result=dict(mm_pipeline.enqueue(d,a.id,a.state))
            elif a.cmd=='pipeline-transition':result=dict(mm_pipeline.transition(d,a.id,a.to,a.actor,a.reason))
            elif a.cmd=='approval-check':result=mm_approval.evaluate(d,a.id)
            elif a.cmd=='approval-decide':result=mm_approval.decide(d,a.approval_id,a.actor,a.reason)
            elif a.cmd=='model-plan':result=mm_model_router.plan(d,a.purpose)
            elif a.cmd=='deploy-check':
                if not a.execute:result={'status':'DRY_RUN','required_gates':list(__import__('mm_deploy').REQUIRED_GATES),'note':'Pass --execute to run gates. Deployment is local-workstation only.'}
                else:
                    import mm_deploy
                    tests=['test_acceptance','test_email_finder','test_email_hardening','test_email_integration','test_lead_qualifier','test_outreach','test_pipeline','test_polish']
                    result=mm_deploy.deploy(d,sys.executable,tests,a.candidate)
            elif a.cmd=='pipeline-run':
                names=getattr(a,'worker',None) or list(mm_workers.WORKERS)
                workers=[mm_pipeline.Worker('worker-'+name,*mm_workers.WORKERS[name],
                    lease_seconds=int(getattr(a,'lease',300))) for name in sorted(names) if name in mm_workers.WORKERS]
                cycles=mm_pipeline.run_pipelineloop(d,workers,
                    sleep_seconds=float(getattr(a,'sleep',60)),
                    max_cycles=int(getattr(a,'cycles',0) or 0),
                    report_every=int(getattr(a,'report_every',10)))
                result={'cycles':cycles,'workers':sorted(names)}
        print(json.dumps(result,indent=2,default=str));return 0
    if a.cmd=='init':
        b=backup()
        with contextlib.closing(connect()) as d,d:migrate(d,b)
        print('Migration checked; backup '+str(b));return 0
    if a.cmd=='price':
        if (a.hours_low is None)!=(a.hours_high is None):raise ValueError('Both hour bounds required')
        result=pricing(a.problem,[a.hours_low,a.hours_high] if a.hours_low is not None else None)
    else:
        with contextlib.closing(connect()) as d,d:
            if a.cmd in ('daily','run-day','status'):result=run_day(d,write=a.cmd!='status')
            elif a.cmd=='money':result=run_day(d,False)['next_revenue_action']
            elif a.cmd=='learn':result=learn(d)
            elif a.cmd=='doctor':result=doctor(d,a.profile)
            elif a.cmd=='experiment':result=assign_experiment(d,a.id,a.industry,a.problem,a.offer,a.price_band,a.style,a.demo_type)
            elif a.cmd=='intake':
                host=public_url(a.url);public_url(a.source)
                for b in d.execute('SELECT id,name,public_website FROM businesses WHERE is_dummy=0'):
                    if b['name'].strip().casefold()==a.name.strip().casefold():
                        raise ValueError('Duplicate prospect '+str(b['id']))
                    # Historical records may contain malformed or now-disallowed URLs.
                    # They must not prevent a duplicate-name check or invalidate a
                    # separate, valid intake request.
                    try:
                        existing_host=public_url(b['public_website']) if b['public_website'] else None
                    except ValueError:
                        existing_host=None
                    if existing_host==host:raise ValueError('Duplicate prospect '+str(b['id']))
                c=d.execute("INSERT INTO businesses(name,region,public_website,source,discovered_at,current_status,is_dummy) VALUES(?,?,?,?,?,'discovered',0)",(a.name.strip(),a.region,a.url,a.source,now()));bid=c.lastrowid
                d.execute("INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)",(bid,now()));event(d,'intake',bid,a.source);result={'business_id':bid}
            elif a.cmd=='audit':result={'evidence_id':record_evidence(d,a.id,a.url,a.observation,a.limitation,a.capture,a.status,a.method,a.confidence,a.claim_type)}
            elif a.cmd=='contact':record_contact(d,a.id,a.recipient,a.url,a.capture,a.relevance);result={'contact_source':'captured','permission':'Human review required'}
            elif a.cmd=='draft':result={'draft_id':create_draft(d,a.id,a.recipient,Path(a.body_file).read_text(),a.parent)}
            elif a.cmd=='review':approve(d,a.id,Path(a.body_file).read_text(),a.human,a.approval_receipt,a.proposal);result={'approval':'Recorded from evidence'}
            elif a.cmd=='record-sent':record_sent(d,a.id,a.receipt,a.proposal);result={'recorded':True,'sent_by_this_command':False}
            elif a.cmd=='receipt-import':result={'receipt_id':import_receipt(d,a.envelope),'verification':'Human attestation; no live provider query'}
            elif a.cmd=='cash':cash(d,a.id,a.cents,a.receipt);result=metrics(d)
            elif a.cmd=='refund':refund(d,a.id,a.cents,a.receipt);result=metrics(d)
            elif a.cmd=='reply':record_reply(d,a.id,a.classification,a.receipt);result={'action':REPLY_ACTIONS[a.classification]}
            elif a.cmd=='suppress':d.execute('INSERT OR IGNORE INTO mm_suppression VALUES(?,?,?)',(a.address.strip().lower(),a.reason,now()));event(d,'suppress',None,a.address.strip().lower());result={'suppressed':True}
            elif a.cmd=='stage':change_stage(d,a.id,a.stage,a.next_action,a.due);result={'stage':a.stage}
            elif a.cmd=='quote':result={'proposal_id':create_proposal(d,a.id,a.recipient,Path(a.body_file).read_text(),a.price_nzd*100)}
            elif a.cmd=='score':result=save_score(d,a.id,latest_evidence(d,a.id),**json.loads(Path(a.inputs).read_text()))
            elif a.cmd=='demo-qa':result=demo_qa(d,a.id,a.path)
            elif a.cmd=='model-request':result=model_request(d,a.model,a.provider,a.purpose)
            elif a.cmd=='run-job':
                d.execute('BEGIN IMMEDIATE');j=claim_job(d,a.key,a.kind);d.commit()
                if j['state']=='completed':result={'cached_checkpoint':json.loads(j['checkpoint'])}
                else:
                    try:
                        result=run_day(d,False) if a.kind=='status' else learn(d)
                        finish_job(d,a.key,result)
                    except Exception as ex:
                        finish_job(d,a.key,{},str(ex));d.commit();raise
    print(json.dumps(result,indent=2))
    return 2 if a.cmd=='model-request' else 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,sqlite3.Error,OSError,KeyError) as e:print('BLOCKED: '+str(e),file=sys.stderr);sys.exit(2)
