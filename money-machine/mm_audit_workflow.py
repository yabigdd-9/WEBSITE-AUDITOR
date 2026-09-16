"""File-only, evidence-backed audit -> offer -> review -> human approval packet.

No database connection, model client, network call, approval import or sender.
Observed HTML facts are distinct from rendered usability and commercial hypotheses.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
import mm_email as email

PROJECT='WEBSITES/BUISNESSaudits'
CATEGORIES=('mobile_usability','accessibility','performance','seo_basics','broken_links',
            'forms','conversion_flow','trust_signals','outdated_content','visual_quality',
            'navigation','contact_visibility','analytics_presence','privacy_cookie_basics',
            'booking_quote_flow','ecommerce_flow','booking_process','quoting_process',
            'enquiry_handling','lead_capture','follow_up','crm_presence','payment_flow',
            'customer_portal','document_workflows','scheduling','automation_opportunities',
            'ai_assistance_opportunities','repetitive_admin','review_reputation_flow')

def sha(data):return hashlib.sha256(data).hexdigest()
def now():return dt.datetime.now(dt.timezone.utc).isoformat()

def load_case(path):
    path=Path(path).resolve();doc=json.loads(path.read_text())
    base=path.parent.parent
    pages=[]
    for meta in doc['pages']:
        p=(base/meta['path']).resolve()
        if not p.is_relative_to(base):raise ValueError('Capture must remain inside its evidence directory')
        raw=p.read_bytes()
        if sha(raw)!=meta['sha256']:raise ValueError('Capture hash mismatch')
        pages.append((meta,raw,email.parse_page(meta,raw)))
    at=dt.datetime.fromisoformat(doc['evaluated_at'])
    result=email.evaluate(doc['business'],[p[2] for p in pages],doc['dns'],at=at)
    if result!=doc['result']:raise ValueError('Stored engine result does not replay')
    return doc,pages

def unnamed_controls(soup):
    fields=[]
    for node in soup.select('input,select,textarea'):
        if node.get('type','').lower() in ('hidden','submit','button','reset','image'):continue
        if node.has_attr('hidden') or node.get('aria-hidden')=='true':continue
        label=node.find_parent('label')
        if node.get('id'):label=label or soup.find('label',attrs={'for':node['id']})
        refs=[soup.find(id=x) for x in node.get('aria-labelledby','').split()]
        if (label and label.get_text(' ',strip=True)) or node.get('aria-label','').strip() or (refs and all(r and r.get_text(' ',strip=True) for r in refs)) or node.get('title','').strip():continue
        fields.append(str(node)[:500])
    return fields

def load_rendered_review(path,pages):
    if path is None:return None
    path=Path(path).resolve(); review=json.loads(path.read_text())
    dom=path.with_suffix('.html').read_bytes()
    if sha(dom)!=review['dom_sha256']:raise ValueError('Rendered DOM hash mismatch')
    if review.get('http_status')!=200 or review['url'] not in {m['url'] for m,_,_ in pages}:
        raise ValueError('Rendered review must match a successful captured page')
    review['source']={'path':str(path),'sha256':sha(path.read_bytes()),'dom_sha256':sha(dom)}
    return review

def audit(doc,pages,rendered=None):
    findings=[]; seen=set()
    def add(code,category,priority,observation,meta,recommendation,effort,detail=None):
        key=(code,meta['sha256'])
        if key in seen:return
        seen.add(key)
        findings.append({'finding_id':'F'+str(len(findings)+1).zfill(3),'code':code,
            'category':category,'severity':priority,'classification':'VERIFIED' if priority=='P2' else 'NEEDS_CONFIRMATION',
            'observed_evidence':observation,'source':{'url':meta['url'],'path':meta['path'],'sha256':meta['sha256'],'captured_at':meta['captured_at']},
            'business_impact':'Possible usability or enquiry friction; customer/revenue effect is unmeasured.',
            'impact_classification':'NEEDS_CONFIRMATION','confidence':0.95,
            'recommended_change':recommendation,'estimated_effort':effort,
            'dependency':'Confirm rendered behavior and CMS access before implementation.',
            'demo_candidate':code in ('UNNAMED_FIELDS','NO_VIEWPORT'),
            'commercial_value_hypothesis':'Improve clarity and ease of enquiry; validate with owner and before/after testing.',
            'detail':detail})
    for meta,raw,_ in pages:
        if 'pdf' in meta.get('content_type',''):continue
        s=BeautifulSoup(raw,'html.parser')
        if not s.find('html'):continue
        if not s.select_one('meta[name="viewport" i]'):
            add('NO_VIEWPORT','mobile_usability','P1','No viewport meta element is present in the captured HTML.',meta,'Add responsive viewport configuration and test the enquiry flow at mobile widths.','1–2 days, provisional')
        controls=unnamed_controls(s)
        confirmed=False
        if rendered and rendered['url']==meta['url']:
            # Match visible browser controls to the original captured HTML. Hidden
            # anti-spam and conditional upload fields cannot qualify a sales claim.
            fields=[f for f in rendered['fields'] if f['visible'] is True and not any((f.get('labelTexts'),f.get('ariaLabel'),f.get('ariaLabelledBy'),f.get('title')))]
            def signature(n):
                return (n.name,n.get('id',''),n.get('name',''),tuple(n.get('class',[])),n.get('size',''),n.get('type','text'))
            visible_signatures={signature(BeautifulSoup(f['outer'],'html.parser').find()) for f in fields}
            def matches(raw):
                n=BeautifulSoup(raw,'html.parser').find()
                return signature(n) in visible_signatures
            controls=[c for c in controls if matches(c)]
            confirmed=bool(controls)
        if controls:
            count=len(controls)
            observation=f'{count} '+('visible form control has' if count==1 else 'visible form controls have') if confirmed else f'{count} HTML form controls have'
            add('UNNAMED_FIELDS','accessibility','P1',observation+' no associated label, aria-label, resolved aria-labelledby text or title'+(' in the restricted browser check.' if confirmed else '; rendered behavior needs confirmation.'),meta,'Add persistent, correctly associated field labels and test keyboard focus and mobile layout.','1–2 days, provisional',controls)
            if confirmed:
                findings[-1]['classification']='VERIFIED'
                findings[-1]['rendered_evidence']=rendered['source']
                findings[-1]['rendered_limitations']=rendered['limitation']
        description=s.select_one('meta[name="description" i]')
        if not description or not description.get('content','').strip():
            add('NO_DESCRIPTION','seo_basics','P2','No populated meta description is present in the captured HTML.',meta,'Write a page-specific description after confirming the intended service and location.','Under half a day, provisional')
    return {'project':PROJECT,'business':doc['business'],'findings':findings,
            'coverage':{c:('STATIC_HTML_ONLY' if c in ('mobile_usability','accessibility','seo_basics','forms') else 'NEEDS_CONFIRMATION') for c in CATEGORIES},
            'limitations':['Static HTML can differ from the rendered page. No forms were submitted.','CRM, analytics, booking outcomes, revenue, buying capacity and internal operations were not observed.','No legal compliance determination or comprehensive accessibility/performance certification.']}

def scorecard(audit_doc,contact):
    fs=[f for f in audit_doc['findings'] if f['classification']=='VERIFIED' and f['severity'] in ('P0','P1')]
    problem='; '.join(f['observed_evidence'] for f in fs[:2])
    dims={
      'website_or_system_problem_strength':(min(5,len(fs)*2),problem or 'No verified P0/P1 problem'),
      'evidence_quality':(4 if fs else 0,'Hashed first-party captures and restricted browser confirmation; production behavior remains untested'),
      'potential_business_value':(None,'Revenue and buying intent unmeasured'),
      'business_legitimacy':(3 if contact['identity']['status']=='HIGH' else 0,'Website identity signals only; legal registration not established'),
      'service_fit':(4 if fs else 0,'Focused website usability repair matches observed problem'),
      'reachable_contact_quality':(4 if contact['selected'] else 0,'Published attribution plus MX when selected; mailbox delivery and permission unproven'),
      'demo_feasibility':(4 if any(f['demo_candidate'] for f in fs) else 0,'Small local HTML demonstration'),
      'likely_decision_maker_access':(None,'No named decision-maker access established'),
      'estimated_delivery_complexity':(3 if fs else None,'Provisional ease-of-delivery score; CMS access unknown'),
      'expected_margin':(None,'Price and actual delivery cost not authorized/measured'),
      'repeatability':(3 if fs else None,'Same validation and packet path can process another captured business')}
    eligible=bool(fs and contact['identity']['status']=='HIGH' and problem)
    known=[v for v,_ in dims.values() if v is not None]
    return {'dimensions':{k:{'value':v,'range':[0,5],'explanation':s} for k,(v,s) in dims.items()},
       'known_score':sum(known),'known_possible':5*len(known),'unknown_dimensions':len(dims)-len(known),
       'reason_for_contact':problem,'internal_offer_eligible':eligible,'outreach_eligible':False,
       'note':'Analyst prioritization rubric, not calibrated purchase probability. Unknowns are not zeros or invented facts.'}

def stage(name,passed,summary,evidence,risks=()):
    return {'stage':name,'status':'PASS' if passed else 'FAILED','summary':summary,'evidence':evidence,
            'risks':list(risks),'next_action':'Continue internal review' if passed else 'Resolve findings; stop workflow'}

def judge(packet):
    verified={f['finding_id'] for f in packet['audit_summary']['findings'] if f['classification']=='VERIFIED'}
    return {'evidence_supported':bool(packet['offer']['evidence']) and set(packet['offer']['evidence']).issubset(verified),
        'verified_problem_required':packet['scorecard']['internal_offer_eligible'] is True and bool(packet['scorecard']['reason_for_contact']),
        'scope_defined':bool(packet['offer']['deliverables']) and bool(packet['offer']['exclusions']),
        'price_unapproved':packet['offer']['price_nzd'] is None,
        'human_gate':packet['status']=='HUMAN_APPROVAL_REQUIRED' and packet['human_approved'] is False and packet['human_review_required'] is True,
        'no_execution':all(packet[k] is False for k in ('send_enabled','outreach_eligible')) and all(packet[k]==0 for k in ('model_calls','paid_ai_cost','outbound_sent'))}

def proof(packet):
    name=packet['business_name'];contact=packet['verified_contact_evidence']
    return {'business_name':name==packet['audit_summary']['business']['name'] and name in packet['draft_message'],
        'website':packet['website']==packet['audit_summary']['business']['public_website'] and urlsplit(packet['website']).scheme in ('http','https'),
        'contact_attribution':contact is None or (contact['confidence_label']=='VERIFIED_HIGH' and contact['first_party_observed'] and bool(contact['evidence'])),
        'claims_caveated':'haven’t measured' in packet['draft_message'] and 'rendered page may behave differently' in packet['draft_message'],
        'deliverable_consistency':bool(packet['offer']['acceptance_criteria']) and packet['demo_path']=='demo.html'}

def make_packet(case_path,output,rendered_review=None):
    doc,pages=load_case(case_path);rendered=load_rendered_review(rendered_review,pages)
    a=audit(doc,pages,rendered);score=scorecard(a,doc['result'])
    if not score['internal_offer_eligible']:raise ValueError('BLOCKED_QUALIFICATION: verified business problem and identity required')
    output=Path(output)
    if output.exists():raise ValueError('New output directory required; prior evidence is immutable')
    output.mkdir(parents=True)
    fs=[f for f in a['findings'] if f['classification']=='VERIFIED' and f['severity'] in ('P0','P1')]
    offer={'problem':score['reason_for_contact'],'evidence':[f['finding_id'] for f in fs],
       'proposed_solution':'Focused field-label and keyboard usability improvement',
       'deliverables':[f['recommended_change'] for f in fs]+['One revision round and documented browser/keyboard acceptance checks'],
       'exclusions':['Full website rebuild','CRM or payment integration','Ongoing hosting','Guaranteed traffic, leads or revenue','Production publication without separate approval'],
       'assumptions':['Owner confirms the issue on the rendered site and supplies authorized CMS access','Current design and existing submission endpoint are retained where suitable'],
       'timeline_assumption':'1–2 working days after access and scope confirmation; estimate only',
       'price_nzd':None,'price_status':'Owner approval and scope confirmation required',
       'acceptance_criteria':['Every in-scope field has a persistent associated label','Keyboard focus is visible and ordered','In-scope flow fits 360px and desktop widths','No existing validated enquiry behavior is removed']}
    name=doc['business']['name']; selected=doc['result']['selected']
    detail=fs[0]['observed_evidence']
    draft=(f"Subject: A small enquiry-flow improvement for {name}\n\nHello {name} team,\n\n"
        f"I’m Dion. In a limited browser review of {fs[0]['source']['url']}, I noticed this specific point: {detail} "
        "External scripts were blocked in that check. The fully rendered page may behave differently, so I would confirm that before proposing any change. "
        "I’ve prepared a small local concept showing clearer form labels, visible keyboard focus and a mobile layout. "
        "The idea is a focused improvement to the existing enquiry flow, with scope and price agreed first. "
        "I haven’t measured any effect on your enquiries or revenue. Would it be useful to share the concept for your feedback?\n\n"
        "Dion\nIf this isn’t relevant, reply no thanks and I won’t follow up.")
    before=html.escape('\n'.join(fs[0].get('detail') or [detail]))
    demo_fields=[]
    for i,raw in enumerate(fs[0]['detail']):
        node=BeautifulSoup(raw,'html.parser').find(); hint=node.get('name','').lower()
        label='Search parts' if 'search' in hint else 'Property address' if 'address' in hint else 'Message' if node.name=='textarea' else 'Enquiry detail'
        control=f'<textarea id="field-{i}" rows="4"></textarea>' if node.name=='textarea' else f'<input id="field-{i}" type="text">'
        demo_fields.append(f'<label for="field-{i}">{label}</label>'+control)
    demo=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'"><title>{html.escape(name)} — enquiry concept</title><style>body{{font:17px/1.6 system-ui;margin:0;background:#f1f4f2;color:#18342a}}main{{max-width:960px;margin:48px auto;padding:24px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}section{{background:white;padding:28px;border-radius:16px}}h1{{font-size:clamp(28px,5vw,44px);line-height:1.15}}small{{display:block}}label{{display:block;font-weight:650;margin:16px 0 4px}}input,textarea{{box-sizing:border-box;width:100%;padding:12px;font:inherit;border:1px solid #7b8c83;border-radius:6px}}button{{margin-top:20px;padding:12px 18px;border:0;background:#174f3d;color:white;font:inherit;border-radius:6px;cursor:pointer}}:focus-visible{{outline:3px solid #be6b25;outline-offset:4px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 monospace}}@media(max-width:650px){{.grid{{grid-template-columns:1fr}}main{{margin:12px auto;padding:16px}}section{{padding:20px}}}}</style></head><body><main><small>INDEPENDENT CONCEPT · OWNER REVIEW ONLY</small><h1>A clearer enquiry flow for {html.escape(name)}</h1><p>Local demonstration. Nothing is sent. This concept was not commissioned or approved by the business.</p><div class="grid"><section><h2>Captured HTML observation</h2><p>{html.escape(detail)}</p><pre>{before}</pre><p>Confirm rendered behavior before making changes.</p></section><section><h2>Proposed enquiry details</h2><p>Persistent labels, visible focus, and a clear review step.</p><form>{''.join(demo_fields)}<button type="button" id="preview">Preview enquiry</button><p role="status" id="status"></p></form></section></div></main><script>document.getElementById('preview').addEventListener('click',()=>{{document.getElementById('status').textContent='Preview ready. Nothing has been sent or saved.'}});document.querySelector('form').addEventListener('submit',e=>e.preventDefault());</script></body></html>'''
    (output/'demo.html').write_text(demo)
    stages=[stage('delegator',True,'Defined a bounded audit from captured first-party evidence',[f['source'] for f in fs]),
            stage('executor',True,'Generated finding-specific offer and local demo',[{'file':'demo.html','sha256':sha(demo.encode())}],a['limitations']),
            stage('judge',True,'Hash replay and verified-problem gate passed; commercial impact remains a hypothesis',offer['evidence'],['Automated rule checks; not an independent human judgment']),
            stage('proofer',True,'Business name and source links retained; price unset; approval remains required',[{'contact':selected['email'] if selected else 'NO_VERIFIED_EMAIL'}],['Contact permission is unconfirmed','Independent human review outstanding'])]
    packet={'project':PROJECT,'created_at':now(),'status':'HUMAN_APPROVAL_REQUIRED','business_name':name,
       'website':doc['business']['public_website'],'audit_summary':a,'scorecard':score,'offer':offer,
       'strongest_evidence':[f['source'] for f in fs],'demo_path':'demo.html','verified_contact_evidence':selected,
       'contact_status':'PUBLIC_ATTRIBUTION_ONLY' if selected else 'NO_VERIFIED_EMAIL',
       'draft_message':draft,'risks':a['limitations']+['Permission to contact and buying capacity not established','Email engine remains POST_DEPLOYMENT_OBSERVATION'],
       'confidence':{'website_identity':doc['result']['identity']['status'],'commercial_outcome':'UNMEASURED'},
       'estimated_delivery_scope':offer['timeline_assumption'],'actions_after_approval':['Confirm recipient, purpose and permission basis','Owner approves exact message and recipient','A separately reviewed transport may send that exact message','Any later implementation, price, production publish or payment requires its own approval'],
       'stages':stages,'human_review_required':True,'human_approved':False,'outreach_eligible':False,
       'send_enabled':False,'model_calls':0,'paid_ai_cost':0,'outbound_sent':0}
    checks={'judge':judge(packet),'proofer':proof(packet)}
    packet['review_checks']=checks
    for role in ('judge','proofer'):
        passed=all(checks[role].values())
        packet['stages'][2 if role=='judge' else 3]['status']='PASS' if passed else 'FAILED'
    if not all(all(c.values()) for c in checks.values()):
        (output/'rejection.json').write_text(json.dumps(checks,indent=2))
        raise ValueError('REVIEW_REJECTED: packet remains blocked')
    (output/'packet.json').write_text(json.dumps(packet,indent=2)+'\n')
    (output/'audit-client.md').write_text('# '+name+' — internal draft for owner review\n\n'+'\n\n'.join(f['observed_evidence']+' Proposed: '+f['recommended_change'] for f in fs)+'\n\n'+ '\n'.join(a['limitations'])+'\n')
    (output/'draft-message.txt').write_text(draft+'\n')
    (output/'APPROVAL_PACKET.md').write_text('# '+name+' — HUMAN_APPROVAL_REQUIRED\n\n'+
       'Website: '+packet['website']+'\n\n'+score['reason_for_contact']+'\n\n[Local demonstration](demo.html) · [Full evidence and scope](packet.json) · [Exact unsent draft](draft-message.txt)\n\n'+
       'No message, approval, production deployment, payment or model call was performed.\n\n'+
       'Price is unset. Estimated work: '+offer['timeline_assumption']+'.\n\n'+
       'Before sending, the owner must resolve contact permission and independent email review, then approve the exact recipient and message. Sending remains disabled.\n')
    return packet

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rendered-review',type=Path)
    a=p.parse_args(argv)
    try:packet=make_packet(a.case,a.output,a.rendered_review)
    except (ValueError,KeyError,OSError) as e:print(json.dumps({'status':'BLOCKED','error':str(e)}));return 2
    print(json.dumps({'status':packet['status'],'business':packet['business_name'],'output':str(a.output),'outbound_sent':0,'paid_ai_cost':0}));return 0

if __name__=='__main__':raise SystemExit(main())
