"""Local outreach planning and review. No mail transport, DNS probes or model calls.

Evidence envelopes are operator attestations, not independent verification.
Generated copy is constrained to catalogue wording; arbitrary copy still needs a
human factual review. A passing audit never grants permission to send.
"""
import datetime as dt
import json
import re
from email import policy
from email.parser import BytesParser
from pathlib import Path

import mm_core as core

VERSION = 'outreach-v1.0.0'
CATALOGUE = {
    'quoting': {
        'label': 'Quote calculators and estimator tools',
        'pitch': 'an estimate calculator for repeatable jobs, using your pricing rules, with unusual work routed to your team',
        'needs': ['A redacted example enquiry and completed quote', 'Approved pricing, quantities, margins, tax and rounding rules', 'Boundary cases and a human approval route'],
        'adjacent': ['intake', 'quote_documents', 'quote_acceptance', 'follow_up', 'repeat_orders', 'crm', 'reporting'],
        'question': 'Could you share one typical enquiry and how you price it, with customer details removed?',
    },
    'website': {
        'label': 'Website and mobile enquiry improvements',
        'pitch': 'clearer service pages and a smoother mobile enquiry journey on your existing website',
        'needs': ['A fresh review of the actual pages and forms', 'Website access and a bounded change list'],
        'adjacent': ['intake', 'reviews', 'reporting'],
        'question': 'Which enquiry or customer journey would you most like to improve?',
    },
    'intake': {
        'label': 'Enquiry forms and file collection',
        'pitch': 'a guided enquiry form that collects job details and files before your team prepares a quote',
        'needs': ['Required fields and supported file types', 'File size limits, malware checks, storage and retention plan'],
        'adjacent': ['crm', 'quoting'],
        'question': 'What information is most often missing from a new enquiry?',
    },
    'quote_documents': {
        'label': 'Prepared quotes and PDF documents',
        'pitch': 'prepared quotes and branded PDFs for your team to review',
        'needs': ['Approved quote template, terms and price rules', 'Staff review before a quote is issued'],
        'adjacent': ['quote_acceptance'],
        'question': 'Could you share a redacted example of the quote you issue today?',
    },
    'quote_acceptance': {
        'label': 'Quote acceptance and handover',
        'pitch': 'a clear quote acceptance step and a handover checklist for the job',
        'needs': ['Approved terms, expiry rules and handover process', 'Identity checks and audit history'],
        'adjacent': ['crm'],
        'question': 'What needs to happen between a customer accepting a quote and the job starting?',
    },
    'follow_up': {
        'label': 'Quote follow-ups and reminders',
        'pitch': 'a follow-up queue for open quotes, with your team approving messages before they go out',
        'needs': ['Customer contact permission and opt-out handling', 'Existing mail access and approved timing', 'Any SMS provider charges separately approved'],
        'adjacent': ['crm', 'reporting'],
        'question': 'How does your team currently keep track of quotes awaiting a reply?',
    },
    'booking': {
        'label': 'Appointment scheduling',
        'pitch': 'appointment scheduling and reminders where customers actually need to reserve a time',
        'needs': ['Confirmed appointment-based workflow', 'Availability rules and existing calendar access'],
        'adjacent': ['follow_up', 'crm'],
        'question': 'Which appointments need a reserved time, and how do you manage availability?',
    },
    'crm': {
        'label': 'CRM and job tracking connections',
        'pitch': 'a connection between enquiries and your existing customer or job tracking system',
        'needs': ['Current systems, permissions and API availability', 'Duplicate handling, ownership and a rollback plan'],
        'adjacent': ['reporting'],
        'question': 'Which system does your team use to track enquiries and jobs?',
    },
    'operations': {
        'label': 'Admin and workflow automation',
        'pitch': 'automation for a repetitive admin step, with exceptions handed back to a person',
        'needs': ['A measured current process and exception examples', 'System access and staff acceptance checks'],
        'adjacent': ['crm', 'reporting'],
        'question': 'Which repetitive task takes up the most time each week?',
    },
    'repeat_orders': {
        'label': 'Repeat-order workflow',
        'pitch': 'a repeat-order flow that reuses approved job details and checks current prices',
        'needs': ['Customer identity and permissions', 'Prior job records and current price validation'],
        'adjacent': ['crm'],
        'question': 'How do customers request a repeat of a previous job?',
    },
    'reviews': {
        'label': 'Customer proof and review presentation',
        'pitch': 'clearer presentation of genuine customer reviews and completed work',
        'needs': ['Authentic reviews or work examples with permission', 'No invented reviews or selective review gating'],
        'adjacent': ['website'],
        'question': 'Which completed projects or customer feedback best show your work?',
    },
    'reporting': {
        'label': 'Enquiry and quote reporting',
        'pitch': 'a simple view of enquiries, quote progress and response times',
        'needs': ['Reliable event definitions and source records', 'Privacy and access boundaries; no invented conversion data'],
        'adjacent': [],
        'question': 'Which number would help you manage enquiries or quoting better?',
    },
}

def _one_line(value, label, limit=180):
    if not isinstance(value, str) or not value.strip() or len(value)>limit or any(ord(x)<32 for x in value):
        raise ValueError(f'{label} must be a short, nonempty single line')
    return value.strip()

def audit_copy(body, *, initial=True, strict=False):
    """Conservative copy lint. Cannot prove all free-form claims true."""
    errors=[]; warnings=[]
    text=body.casefold()
    if '\r' in body or '\x00' in body: errors.append('control_characters')
    if not body.startswith('Subject: ') or '\n\n' not in body: errors.append('subject_and_body_required')
    subject=body.split('\n',1)[0].removeprefix('Subject: ').strip()
    if not subject or len(subject)>100: errors.append('subject_length')
    if initial and re.match(r'(?i)(re|fw|fwd)\s*:', subject): errors.append('false_reply_subject')
    if re.search(r'(?im)^(to|cc|bcc|from|reply-to|content-type):', body): errors.append('embedded_mail_headers')
    if re.search(r'\[[^\]\n]+\]|\{\{.*?\}\}|<\s*(name|company|first.name)\s*>', body, re.I): errors.append('unfilled_placeholder')
    if re.search(r'\bguarantee(?:d|s)?\b|\bzero[- ](?:bounce|failure)|\b100\s*%\s*(?:deliver|success)', text): errors.append('unproven_guarantee')
    if re.search(r'\d+(?:[–-]\d+)?\s*%|\b(?:double|triple)\s+(?:your|the)\s+(?:sales|revenue)', text): errors.append('numeric_performance_claim_requires_separate_evidence_review')
    if re.search(r'lost revenue|losing (?:money|customers|sales)|competitors who|cuts no.shows|leaving money on the table', text): errors.append('unsupported_loss_or_comparison_claim')
    if re.search(r"(?:doesn.t|don.t|do not|does not) have|your (?:website|form|booking).{0,25}(?:broken|missing|outdated)|no (?:contact|enquiry|booking) form", text): errors.append('negative_website_claim_requires_scoped_review')
    if re.search(r'\b(?:independent|auckland) printings\b', text): errors.append('incorrect_industry_wording')
    if 'reply' not in text or not any(x in text for x in ('no thanks','unsubscribe')): errors.append('reply_opt_out_required')
    if re.search(r'https?://(?:bit\.ly|tinyurl\.com|t\.co)/', text): errors.append('shortened_link')
    if re.search(r'<(?:script|iframe|img)\b', text): errors.append('active_content_or_tracking')
    words=len(body.split())
    if words>190: warnings.append('long_opening_email' if initial else 'long_reply')
    if body.count('?')>1: warnings.append('multiple_questions')
    if strict and words<60: errors.append('underdeveloped_draft')
    if strict and words>190: errors.append('opening_email_over_190_words')
    return {'passed':not errors,'errors':sorted(set(errors)),'warnings':warnings,'word_count':words,
            'scope':'Pattern checks only; human claim, relevance and sender review still required.'}

def require_copy(body, initial=True):
    result=audit_copy(body,initial=initial)
    if result['errors']: raise ValueError('Outreach copy audit: '+', '.join(result['errors']))

def _signal_check(signal, company):
    if not isinstance(signal,dict): return 'malformed_signal'
    if signal.get('service') not in CATALOGUE: return 'unknown_service'
    if signal.get('kind') not in ('customer_request','verified_need','declined','existing_adequate'): return 'unknown_signal_kind'
    if signal.get('company')!=company: return 'different_business'
    if signal.get('source_kind') not in ('direct_reply','forwarded_context','user_instruction','public_capture'): return 'unknown_source_kind'
    if not core.fresh(signal.get('captured_at'),7): return 'stale_or_future_source'
    if not isinstance(signal.get('source_path'),str) or not isinstance(signal.get('source_sha256'),str): return 'source_missing_or_changed'
    if not core.artifact_valid(signal['source_path'],signal['source_sha256']): return 'source_missing_or_changed'
    quote=signal.get('quote','')
    try: source=Path(signal['source_path']).read_text()
    except (OSError,UnicodeError): return 'unreadable_source'
    if not isinstance(quote,str) or len(quote.strip())<12 or quote not in source: return 'quote_not_in_source'
    if not signal.get('reviewed_by'): return 'source_review_required'
    if signal['kind']=='verified_need' and signal['source_kind']!='public_capture': return 'observation_requires_public_capture'
    return None

def plan(brief):
    """Plan all supported and adjacent options. No keyword-only industry inference.

    Signals explicitly bind a need to a service and a captured source. Related
    services remain conditional; neither signals nor this plan prove permission.
    """
    if not isinstance(brief,dict) or not isinstance(brief.get('signals',[]),list): raise ValueError('Object brief with a signals list required')
    company=_one_line(brief.get('company'),'company',80)
    sender=_one_line(brief.get('sender_name'),'sender_name',60)
    brand=_one_line(brief.get('sender_brand'),'sender_brand',60)
    from mm_email import normalize_email
    address,error=normalize_email(_one_line(brief.get('recipient'),'recipient',254))
    if error: raise ValueError(error)
    mode=brief.get('mode','initial')
    if mode not in ('initial','reply'): raise ValueError('mode must be initial or reply')
    valid=[]; rejected=[]; blocked=set()
    for n,s in enumerate(brief.get('signals',[])):
        problem=_signal_check(s,company)
        if problem: rejected.append({'index':n,'reason':problem});continue
        valid.append((n,s))
        if s['kind'] in ('declined','existing_adequate'): blocked.add(s['service'])
    ranked={}
    for n,s in valid:
        service=s['service']
        if service in blocked or s['kind'] in ('declined','existing_adequate'): continue
        priority=100 if s['kind']=='customer_request' else 80
        if s['source_kind'] in ('forwarded_context','user_instruction'): priority-=10
        if service not in ranked or priority>ranked[service]['priority']:
            ranked[service]={'service':service,'priority':priority,'basis':s['kind'],
                'source_kind':s['source_kind'],'signal_index':n,'conditional':s['source_kind']!='direct_reply'}
    # One expansion level prevents a vague website idea growing into every service.
    for primary in list(ranked.values()):
        for service in CATALOGUE[primary['service']]['adjacent']:
            if service not in blocked and service not in ranked:
                ranked[service]={'service':service,'priority':40,'basis':'adjacent_option',
                    'source_kind':primary['source_kind'],'signal_index':primary['signal_index'],
                    'conditional':True,'related_to':primary['service']}
    ordered=sorted(ranked.values(),key=lambda x:-x['priority'])
    for option in ordered:
        option.update({k:CATALOGUE[option['service']][k] for k in ('label','needs')})
        option['feasibility']='discovery_required'
    stop=brief.get('stop_contact') is True
    # A forwarded seller reply is not evidence of a direct customer reply.
    can_reply=bool(brief.get('original_message_id')) and any(s['source_kind']=='direct_reply' for _,s in valid)
    holds=[]
    if stop: holds.append('do_not_contact_instruction')
    if not ordered: holds.append('no_current_supported_opportunity')
    if mode=='reply' and not can_reply: holds.append('direct_reply_and_original_message_id_required')
    body=None; audit={'passed':False,'errors':holds,'warnings':[]}
    chosen=ordered[:3]
    if not holds:
        lead=chosen[0]['service']
        subject=f'{company} — {"quoting and enquiry ideas" if lead=="quoting" else "a few practical improvements"}'
        if mode=='reply': subject='Re: '+re.sub(r'(?i)^re:\s*','',_one_line(brief.get('thread_subject'),'thread_subject',96))
        greeting='Hi '+_one_line(brief.get('contact_name',company+' team'),'contact_name',100)+','
        introduction=(f'Thanks for your question. I’d start with {CATALOGUE[lead]["label"].lower()}.'
                      if mode=='reply' else f'I’m {sender} from {brand}. I’d like to explore a few practical improvements for {company}, starting with {CATALOGUE[lead]["label"].lower()}.')
        bullets=['- '+CATALOGUE[x['service']]['pitch'][0].upper()+CATALOGUE[x['service']]['pitch'][1:]+'.' for x in chosen]
        body='Subject: '+subject+'\n\n'+greeting+'\n\n'+introduction+'\n\nDepending on your current setup, we could build:\n'+'\n'.join(bullets)+'\n\nWe could start with one small example, confirm the scope and cost, and build around the tools you already use.\n\n'+CATALOGUE[lead]['question']+'\n\nCheers,\n'+sender+' | '+brand+'\n\nIf this isn’t relevant, reply “no thanks” and I’ll leave it there.'
        audit=audit_copy(body,initial=mode=='initial',strict=True)
        if not audit['passed']: holds.extend(audit['errors'])
    return {'version':VERSION,'created_at':core.now(),'company':company,'recipient':address,'mode':mode,
        'brief':brief,'opportunities':ordered,'excluded_services':sorted(blocked),'rejected_signals':rejected,
        'featured_services':[x['service'] for x in chosen],'body':body,
        'digest':core.digest(address,body) if body else None,'copy_audit':audit,
        'planning_holds':holds,'external_send_allowed':False,
        'review_note':'Local preview only. Verify all source interpretations, feasibility, identity, contact permission and exact copy. No authority to send.'}

def audit_packet(packet):
    regenerated=plan(packet['brief'])
    errors=list(regenerated['planning_holds'])
    # Bind body, recipient, selected services and source interpretations together.
    for key in ('body','recipient','digest','opportunities','featured_services','excluded_services','rejected_signals','mode','company','version'):
        if packet.get(key)!=regenerated.get(key): errors.append('packet_changed:'+key)
    if packet.get('external_send_allowed') is not False: errors.append('invalid_send_authority')
    return {'passed':not errors,'errors':errors,'copy_audit':regenerated['copy_audit'],
            'external_send_allowed':False,'checked_at':core.now()}

def classify_dsn(raw, recipient, original_message_id):
    """Parse actual per-recipient DSN fields, never bounce words in body text.

    Matching IDs are correlation, not authentication. Outputs are suggestions;
    applying suppression still requires independently reviewed provider evidence.
    """
    result={'state':'unconfirmed','action':'reconcile_provider_before_any_retry',
        'automatic_retry':False,'automatic_suppression':False,'recipient':recipient,
        'provider_authentication':'not_verified','source_sha256':core.sha(raw)}
    if not recipient or not original_message_id or len(raw)>2_000_000: return result
    msg=BytesParser(policy=policy.default).parsebytes(raw)
    if msg.get_content_type()!='multipart/report' or msg.get_param('report-type')!='delivery-status': return result
    ids=[]
    for part in msg.walk():
        if part.get_content_type()=='message/rfc822':
            for original in part.get_payload(): ids.extend(str(v).strip() for v in original.get_all('Message-ID',[]))
        elif part.get_content_type()=='text/rfc822-headers':
            data=part.get_payload(decode=True) or b''
            ids.extend(str(v).strip() for v in BytesParser(policy=policy.default).parsebytes(data).get_all('Message-ID',[]))
    if ids!=[original_message_id]: return result
    matches=[]
    for part in msg.walk():
        if part.get_content_type()!='message/delivery-status': continue
        for block in part.get_payload():
            if len(block.get_all('Final-Recipient',[]))!=1: continue
            final=str(block.get('Final-Recipient','')).split(';',1)
            if len(final)!=2 or final[0].strip().casefold()!='rfc822' or final[1].strip().casefold()!=recipient.strip().casefold(): continue
            if len(block.get_all('Status',[]))!=1 or len(block.get_all('Action',[]))!=1: return result
            matches.append((str(block['Status']).strip(),str(block['Action']).strip().lower()))
    if len(matches)!=1: return result
    status,action=matches[0]
    if not re.fullmatch(r'[245]\.(?:0|[1-9][0-9]{0,2})\.(?:0|[1-9][0-9]{0,2})',status): return result
    result.update(status_code=status,dsn_action=action)
    if status.startswith('5.') and action=='failed':
        if status in ('5.1.1','5.1.2','5.1.3','5.1.6'):
            result.update(state='permanent_destination_failure',action='verify_provider_evidence_then_suppress_exact_recipient')
        elif status.startswith('5.7.') or status in ('5.1.7','5.1.8'):
            result.update(state='sender_or_policy_failure',action='hold_sender_route_and_investigate_do_not_mark_mailbox_invalid')
        else: result.update(state='permanent_failure',action='human_review_before_any_changed_message_or_destination')
    elif status.startswith('4.') and action in ('delayed','failed'):
        result.update(state='temporary_failure',action='wait_for_provider_queue_or_human_reconciliation_no_duplicate_submission')
    elif status.startswith('2.') and action in ('delivered','relayed','expanded'):
        result.update(state='reported_'+action,action='verify_report_no_resend')
    return result

def preflight(d, message_id):
    """Read-only review immediately before any separately authorized transport.

    Sender authentication and provider idempotency are deliberately unconnected.
    A DNS/MX result or lack of a bounce cannot fill those gaps.
    """
    m=d.execute('SELECT * FROM mm_messages WHERE id=?',(message_id,)).fetchone()
    if not m: raise ValueError('Unknown message')
    reasons=core.readiness(d,m['business_id'],m['evidence_id'],m['recipient'])
    copy=audit_copy(m['body'],initial=m['kind']=='initial')
    reasons.extend(copy['errors'])
    if m['sent_at']: reasons.append('already_recorded_as_sent_no_resend')
    if m['reply']: reasons.append('reply_received_review_conversation_first')
    others=list(d.execute('SELECT id,sent_at,reply FROM mm_messages WHERE lower(trim(recipient))=lower(trim(?)) AND id<>?',(m['recipient'],message_id)))
    if others: reasons.append('other_messages_to_same_recipient_require_conversation_reconciliation')
    if m['invalidated_reason']: reasons.append('invalidated_message')
    if m['approved_hash']!=core.digest(m['recipient'],m['body']): reasons.append('exact_human_approval_required')
    else:
        try: core.receipt(d,m['approval_ref'],'approval',m['business_id'],m['id'],m['approved_hash'])
        except ValueError as e: reasons.append(str(e))
    # Deliberate holds, not claims that the sender is misconfigured.
    reasons.extend(['current_sender_authentication_and_route_check_required',
                    'provider_send_history_and_idempotency_reconciliation_required',
                    'no_mail_transport_connected'])
    return {'message_id':message_id,'checked_at':core.now(),'held':True,
        'reasons':list(dict.fromkeys(reasons)),'copy_audit':copy,'mailbox_exists':'unknown',
        'delivery_guarantee':None,'related_message_ids':[x['id'] for x in others],'external_send_allowed':False}

def health(d):
    messages=list(d.execute('SELECT * FROM mm_messages'))
    attested=0; invalid_receipts=0; issues=[]
    for m in messages:
        if m['sent_at']:
            try:
                core.receipt(d,m['send_receipt'],'send',m['business_id'],m['id'],core.digest(m['recipient'],m['body']))
                attested+=1
            except ValueError: invalid_receipts+=1
        audit=audit_copy(m['body'],initial=m['kind']=='initial')
        if not audit['passed']: issues.append({'message_id':m['id'],'business_id':m['business_id'],'errors':audit['errors']})
    return {'version':VERSION,'checked_at':core.now(),'messages_checked':len(messages),
        'copy_issues':issues,'locally_attested_sends':attested,'invalid_send_receipts':invalid_receipts,
        'independently_verified_deliveries':None,'bounce_rate':None,'bounce_rate_reason':'No independently verified delivery-outcome cohort is connected; unknown is not zero.',
        'external_send_allowed':False,'model_calls':0,'paid_api_calls':0,
        'improvement':'Review the highest-priority supported need and up to two related services; measure outcomes before promoting a template.'}

def cli(args, d):
    if args.cmd=='outreach-plan': return plan(json.loads(Path(args.brief).read_text()))
    if args.cmd=='outreach-audit': return audit_packet(json.loads(Path(args.packet).read_text()))
    if args.cmd=='outreach-preflight': return preflight(d,args.id)
    if args.cmd=='outreach-dsn': return classify_dsn(Path(args.eml).read_bytes(),args.recipient,args.original_message_id)
    return health(d)
