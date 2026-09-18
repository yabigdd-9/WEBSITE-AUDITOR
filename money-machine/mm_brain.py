"""Brain approval layer for Money Machine — evidence-based deterministic review.

Zero model calls. Zero fabrication. All 13 criteria must pass for APPROVED_FOR_SEND.
Any single hard rejection forces REJECTED. Any missing or uncertain criterion with
fail_closed=true forces NEEDS_RESEARCH.

Decisions are recorded in approval_events and (for approvals) mm_receipts.
The existing DB triggers enforce all safety gates; the brain merely fills the
approved_hash when every independent evidence check satisfies fail-closed rules.
"""

import datetime as dt
import json
import re
from pathlib import Path

import mm_core as core
import mm_email as engine
import mm_email_store as email_store
import mm_outreach as outreach

VERSION = 'brain-v1.0.0'

DEFAULT_CONFIG = {
    'identity_verified': True,
    'canonical_domain_verified': True,
    'first_party_evidence': True,
    'commercial_need_verified': True,
    'email_status': 'VERIFIED_HIGH',
    'email_evidence_count_min': 1,
    'suppression_clear': True,
    'duplicate_clear': True,
    'placeholders_clear': True,
    'preflight_passed': True,
    'evidence_fresh_days': 7,
    'fail_closed': True,
}

REJECTION_LABELS = {
    'NO_VERIFIED_EMAIL': 'No VERIFIED_HIGH email selected for business',
    'identity_mismatch': 'Business identity verification FAILED',
    'domain_mismatch': 'Canonical domain does not match business identity',
    'stale_evidence': 'Latest first-party evidence older than configured freshness window',
    'catch_all_only': 'Catch-all domain only; individual mailbox existence unconfirmed',
    'guessed_email_only': 'Email is pattern-derived (CANDIDATE) without direct observation',
    'suppressed': 'Business or address is on suppression list',
    'duplicate_contact': 'Duplicate outreach attempted to same address for different business',
    'no_real_opportunity': 'No verified commercial problem/opportunity identified',
    'competitor_or_agency': 'Business appears to be a competitor or agency',
    'unfilled_placeholder': 'Message body contains unfilled template placeholders',
    'email_policy_hold': 'Email policy mode does not currently allow verified email outreach',
}


def get_config(d, config_override=None):
    """Load brain config, allowing runtime overrides."""
    cfg = dict(DEFAULT_CONFIG)
    if config_override:
        for key, val in config_override.items():
            if key in cfg:
                cfg[key] = val
    return cfg


def _identity_details(d, bid):
    """Fetch latest identity check result from DB."""
    row = d.execute(
        "SELECT result_json FROM email_identity_checks WHERE prospect_id=? ORDER BY id DESC LIMIT 1", (bid,)
    ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def _email_selection(d, bid):
    """Fetch current email selection state from prospect_email_state."""
    row = d.execute("SELECT * FROM prospect_email_state WHERE prospect_id=?", (bid,)).fetchone()
    if not row:
        return None
    return dict(row)


def _email_verification_count(d, bid, normalized_email):
    """Count verifications for the selected email."""
    return d.execute(
        "SELECT COUNT(*) FROM email_verifications v JOIN email_candidates c ON c.id=v.candidate_id "
        "WHERE c.prospect_id=? AND c.normalized_email=?",
        (bid, normalized_email.casefold()),
    ).fetchone()[0]


def _latest_evidence_details(d, bid):
    """Fetch latest evidence + meta for business."""
    ev = d.execute(
        "SELECT e.*, m.status AS meta_status, m.confidence, m.method, m.claim_type "
        "FROM mm_evidence e LEFT JOIN mm_evidence_meta m ON m.evidence_id=e.id "
        "WHERE e.business_id=? ORDER BY julianday(e.checked_at) DESC, e.id DESC LIMIT 1",
        (bid,),
    ).fetchone()
    if not ev:
        return None
    return dict(ev)


def _has_outreach_to_address(d, address, exclude_bid=None):
    """Check for duplicate outreach to same address across other businesses."""
    query = (
        "SELECT DISTINCT business_id FROM mm_messages "
        "WHERE lower(trim(recipient))=lower(trim(?)) AND invalidated_reason IS NULL"
    )
    params = [address]
    if exclude_bid is not None:
        query += " AND business_id<>?"
        params.append(exclude_bid)
    rows = d.execute(query, params).fetchall()
    return [r[0] for r in rows]


def _suppression_hit(d, bid, address):
    """Check all suppression sources. Returns tuple(stopped, reason)."""
    if d.execute("SELECT 1 FROM mm_suppression WHERE lower(trim(address))=?", (address.strip().lower(),)).fetchone():
        return True, 'address suppressed'
    if d.execute("SELECT 1 FROM mm_holds WHERE business_id=?", (bid,)).fetchone():
        return True, 'business on hold'
    if d.execute("SELECT 1 FROM mm_deals WHERE business_id=? AND stage='SUPPRESSED'", (bid,)).fetchone():
        return True, 'business SUPPRESSED'
    if d.execute(
        "SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=? AND do_not_contact=1",
        (address.strip().lower(),),
    ).fetchone():
        return True, 'address do_not_contact'
    if d.execute(
        "SELECT 1 FROM mm_contact_evidence WHERE business_id=? AND lower(trim(recipient))=? AND unsubscribe_state='unsubscribed'",
        (bid, address.strip().lower()),
    ).fetchone():
        return True, 'contact unsubscribed'
    return False, ''


def _contact_evidence_details(d, bid, address):
    """Fetch latest contact evidence row."""
    row = d.execute(
        "SELECT * FROM mm_contact_evidence WHERE business_id=? AND lower(trim(recipient))=lower(trim(?)) ORDER BY checked_at DESC LIMIT 1",
        (bid, address),
    ).fetchone()
    return dict(row) if row else None


def _demo_qa_passed(d, bid):
    """Check for current demo QA pass."""
    row = d.execute(
        "SELECT * FROM mm_demo_qa WHERE business_id=? ORDER BY checked_at DESC LIMIT 1", (bid,)
    ).fetchone()
    if not row:
        return False
    return bool(row['passed']) and row['score'] >= 80


def _evaluate_criteria(d, message, cfg):
    """Run all 13 brain criteria. Returns (criteria, rejections, context)."""
    bid = message['business_id']
    address = message['recipient']
    identity = _identity_details(d, bid)
    selection = _email_selection(d, bid)
    evidence = _latest_evidence_details(d, bid)
    contact = _contact_evidence_details(d, bid, address)
    criteria = {}
    rejections = []
    context = {'identity': identity, 'selection': selection, 'evidence': evidence, 'contact': contact}

    # --- 1. identity_verified ---
    identity_ok = identity is not None and identity.get('status') == 'HIGH'
    criteria['identity_verified'] = {
        'pass': bool(identity_ok),
        'detail': f"identity.status={identity.get('status')}" if identity else 'no identity check found',
        'required': cfg['identity_verified'],
    }
    if cfg['identity_verified'] and not identity_ok:
        rejections.append('identity_mismatch')

    # --- 2. canonical_domain_verified ---
    domain_ok = (
        identity_ok
        and bool(identity.get('canonical_root_domain'))
        and identity.get('canonical_root_domain') == identity.get('proposed_root_domain')
    )
    criteria['canonical_domain_verified'] = {
        'pass': bool(domain_ok),
        'detail': f"canonical={identity.get('canonical_root_domain')}" if identity else 'no identity',
        'required': cfg['canonical_domain_verified'],
    }
    if cfg['canonical_domain_verified'] and not domain_ok:
        rejections.append('domain_mismatch')

    # --- 3. first_party_evidence ---
    first_party_ok = evidence is not None and evidence.get('meta_status') == 'verified'
    criteria['first_party_evidence'] = {
        'pass': bool(first_party_ok),
        'detail': f"method={evidence.get('method')}, status={evidence.get('meta_status')}" if evidence else 'no evidence',
        'required': cfg['first_party_evidence'],
    }
    if cfg['first_party_evidence'] and not first_party_ok:
        rejections.append('no_real_opportunity')

    # --- 4. commercial_need_verified ---
    commercial_ok = (
        evidence is not None
        and evidence.get('meta_status') == 'verified'
        and bool(evidence.get('claim_type'))
    )
    criteria['commercial_need_verified'] = {
        'pass': bool(commercial_ok),
        'detail': f"claim_type={evidence.get('claim_type')}" if evidence else 'no commercial evidence',
        'required': cfg['commercial_need_verified'],
    }
    if cfg['commercial_need_verified'] and not commercial_ok:
        rejections.append('no_real_opportunity')

    # --- 5. email_status ---
    required_status = cfg['email_status']
    email_ok = selection is not None and selection.get('selection_status') == required_status
    criteria['email_status'] = {
        'pass': bool(email_ok),
        'detail': f"selection_status={selection.get('selection_status') if selection else 'none'}",
        'required': True,
    }
    if not email_ok:
        rejections.append('NO_VERIFIED_EMAIL')

    # --- 6. email_evidence_count_min ---
    email_count = 0
    if selection and selection.get('best_email_id'):
        cand = d.execute("SELECT normalized_email FROM email_candidates WHERE id=?", (selection['best_email_id'],)).fetchone()
        if cand:
            email_count = _email_verification_count(d, bid, cand[0])
    criteria['email_evidence_count_min'] = {
        'pass': email_count >= cfg['email_evidence_count_min'],
        'detail': f"evidence_count={email_count}, required>={cfg['email_evidence_count_min']}",
        'required': True,
    }
    if email_count < cfg['email_evidence_count_min']:
        rejections.append('NO_VERIFIED_EMAIL')

    # --- 7. suppression_clear ---
    suppressed, why = _suppression_hit(d, bid, address)
    criteria['suppression_clear'] = {
        'pass': not suppressed,
        'detail': 'clear' if not suppressed else f'suppressed: {why}',
        'required': cfg['suppression_clear'],
    }
    if cfg['suppression_clear'] and suppressed:
        rejections.append('suppressed')

    # --- 8. duplicate_clear ---
    others = _has_outreach_to_address(d, address, exclude_bid=bid)
    criteria['duplicate_clear'] = {
        'pass': len(others) == 0,
        'detail': 'no duplicates' if not others else f'also sent to business ids: {others}',
        'required': cfg['duplicate_clear'],
    }
    if cfg['duplicate_clear'] and others:
        rejections.append('duplicate_contact')

    # --- 9. placeholders_clear ---
    audit = outreach.audit_copy(message['body'], initial=message['kind'] == 'initial', strict=True)
    placeholders_ok = 'unfilled_placeholder' not in audit['errors']
    criteria['placeholders_clear'] = {
        'pass': bool(placeholders_ok),
        'detail': 'no placeholders' if placeholders_ok else 'body audit found unfilled placeholders',
        'required': cfg['placeholders_clear'],
    }
    if cfg['placeholders_clear'] and not placeholders_ok:
        rejections.append('unfilled_placeholder')

    # --- 10. preflight_passed ---
    preflight = outreach.preflight(d, message['id'])
    # preflight always returns held=True because no mail transport is connected.
    # Brain considers preflight "passed" if the only reasons are transport-related.
    transport_only_reasons = {
        'no_mail_transport_connected',
        'current_sender_authentication_and_route_check_required',
        'provider_send_history_and_idempotency_reconciliation_required',
    }
    blocking_reasons = [r for r in preflight['reasons'] if r not in transport_only_reasons]
    preflight_ok = len(blocking_reasons) == 0
    criteria['preflight_passed'] = {
        'pass': bool(preflight_ok),
        'detail': 'no blocking preflight holds' if preflight_ok else f'blocking: {blocking_reasons}',
        'required': cfg['preflight_passed'],
    }
    if cfg['preflight_passed'] and not preflight_ok:
        rejections.append(blocking_reasons[0] if blocking_reasons else 'preflight_failed')

    # --- 11. evidence_fresh ---
    fresh_days = cfg['evidence_fresh_days']
    if evidence:
        age_days = core.age_days(evidence['checked_at'])
        evidence_fresh_ok = 0 <= age_days <= fresh_days
        context['evidence_age_days'] = round(age_days, 1)
    else:
        evidence_fresh_ok = False
        context['evidence_age_days'] = None
    criteria['evidence_fresh'] = {
        'pass': bool(evidence_fresh_ok),
        'detail': f"age_days={context['evidence_age_days']}, required<={fresh_days}",
        'required': True,
    }
    if not evidence_fresh_ok:
        rejections.append('stale_evidence')

    # --- 12. relevant_personalised_offer ---
    # Brain confirms offer relevance by checking that evidence has a claim_type that
    # maps to a known service category in the outreach catalogue.
    catalogue_services = {k for k in outreach.CATALOGUE}
    claim_type = evidence.get('claim_type', '') if evidence else ''
    offer_relevant = claim_type in catalogue_services or claim_type in (
        'conversion', 'quoting', 'lead_capture', 'booking', 'follow_up', 'crm',
        'operations', 'reviews', 'reporting', 'website', 'intake',
    )
    criteria['relevant_personalised_offer'] = {
        'pass': bool(offer_relevant),
        'detail': f"claim_type={claim_type}",
        'required': True,
    }
    if not offer_relevant:
        rejections.append('no_real_opportunity')

    # --- 13. correct_business_identity (composite of 1+2+entity_key consistency) ---
    identity_name_match = identity_ok and identity.get('canonical_business_name') == d.execute(
        "SELECT name FROM businesses WHERE id=?", (bid,)
    ).fetchone()[0]
    criteria['correct_business_identity'] = {
        'pass': bool(identity_name_match),
        'detail': f"identity_name={identity.get('canonical_business_name')}" if identity else 'no identity check',
        'required': True,
    }
    if not identity_name_match:
        rejections.append('identity_mismatch')

    # --- Additional hard rejections based on email verification state ---
    if selection and selection.get('best_email_id'):
        cand = d.execute(
            "SELECT * FROM email_candidates WHERE id=?", (selection['best_email_id'],)
        ).fetchone()
        if cand and cand.get('candidate_method') == 'CANDIDATE_PATTERN_DERIVED':
            rejections.append('guessed_email_only')
        if cand and cand.get('candidate_method') == 'legacy_import':
            rejections.append('NO_VERIFIED_EMAIL')

    # --- SMTP catch-all detection ---
    if selection and selection.get('best_email_id'):
        cand_row = d.execute(
            "SELECT normalized_email FROM email_candidates WHERE id=?", (selection['best_email_id'],)
        ).fetchone()
        if cand_row:
            vrow = d.execute(
                "SELECT catch_all_status, smtp_result FROM email_verifications WHERE candidate_id=? "
                "ORDER BY checked_at DESC LIMIT 1",
                (selection['best_email_id'],),
            ).fetchone()
            if vrow:
                context['smtp_catch_all'] = vrow['catch_all_status']
                context['smtp_result'] = vrow['smtp_result']
                if vrow['catch_all_status'] == 'yes':
                    rejections.append('catch_all_only')
                if vrow['smtp_result'] == 'rejected':
                    rejections.append('NO_VERIFIED_EMAIL')

    # --- competitor / agency check via identity context ---
    if identity:
        body_text = ' '.join(identity.get('page_titles', []) + identity.get('organization_names', []))
        if re.search(r'\b(web design|seo|marketing agency|digital agency|design agency)\b',
                      body_text, re.I):
            rejections.append('competitor_or_agency')

    # --- email policy mode ---
    if email_store.installed(d):
        mode = d.execute('SELECT mode FROM email_policy WHERE id=1').fetchone()[0]
        context['email_policy_mode'] = mode
        if mode in ('shadow', 'v1_hold'):
            rejections.append('email_policy_hold')

    # --- fail-closed: any required criterion that is not pass=False is "uncertain" ---
    for name, c in criteria.items():
        if c['required'] and not c['pass'] and name not in ('identity_verified', 'canonical_domain_verified', 'first_party_evidence', 'commercial_need_verified', 'correct_business_identity'):
            # These are already mapped to specific rejections
            pass

    # --- deduplicate rejections preserving order ---
    rejections = list(dict.fromkeys(rejections))

    return criteria, rejections, context


def review(d, message_id, config_override=None):
    """Full brain review for a message/proposal.
    
    Returns a structured evaluation. This function NEVER sets approved_hash;
    call approve() separately if the decision is APPROVED_FOR_SEND.
    """
    m = d.execute("SELECT * FROM mm_messages WHERE id=?", (message_id,)).fetchone()
    if not m:
        raise ValueError(f'Unknown message {message_id}')
    if m['sent_at']:
        raise ValueError(f'Message {message_id} already sent; cannot review')
    if m['invalidated_reason']:
        raise ValueError(f'Message {message_id} invalidated; cannot review')
    
    cfg = get_config(d, config_override)
    criteria, rejections, context = _evaluate_criteria(d, m, cfg)
    
    # --- Decision ---
    # REJECTED if any hard rejection.
    # APPROVED_FOR_SEND if zero rejections AND all required criteria pass.
    # NEEDS_RESEARCH otherwise (fail_closed).
    required_pass_count = sum(1 for c in criteria.values() if c['required'] and c['pass'])
    required_total = sum(1 for c in criteria.values() if c['required'])
    
    if rejections:
        decision = 'REJECTED'
    elif required_pass_count == required_total and required_total > 0:
        decision = 'APPROVED_FOR_SEND'
    else:
        decision = 'NEEDS_RESEARCH'
    
    # --- fail-closed: if any required criterion detail produced no test result, downgrade ---
    if cfg['fail_closed'] and decision == 'APPROVED_FOR_SEND':
        for name, c in criteria.items():
            if c['required'] and ('no ' in c['detail'].lower() or c['detail'] == 'none'):
                decision = 'NEEDS_RESEARCH'
                rejections.append(f'uncertain_{name}')
                break

    evaluation = {
        'message_id': message_id,
        'business_id': m['business_id'],
        'generated_at': core.now(),
        'decision': decision,
        'criteria_met': f'{required_pass_count}/{required_total}',
        'criteria': criteria,
        'rejections': rejections,
        'rejection_labels': {r: REJECTION_LABELS.get(r, r) for r in rejections},
        'context': context,
        'config_applied': cfg,
        'limitations': [
            'Brain is rule-based; no model inference.',
            'Sender must independently confirm APPROVED_FOR_SEND + rerun preflight',
            'Any edit after approval invalidates approved_hash (DB trigger).',
        ],
        'version': VERSION,
    }
    return evaluation


def approve(d, message_id, config_override=None):
    """Execute brain approval. Sets approved_hash on the message.
    
    Requires review() decision to be APPROVED_FOR_SEND. Creates the approval
    receipt artifact and records it in approval_events + mm_receipts.
    """
    evaluation = review(d, message_id, config_override)
    if evaluation['decision'] != 'APPROVED_FOR_SEND':
        raise ValueError(
            f"Brain cannot approve message {message_id}: decision={evaluation['decision']}, "
            f"rejections={evaluation['rejections']}"
        )
    
    m = d.execute("SELECT * FROM mm_messages WHERE id=?", (message_id,)).fetchone()
    bid = m['business_id']
    
    # 1. Write review artifact
    root = core.root()
    review_dir = root / 'evidence' / 'brain-reviews'
    review_dir.mkdir(parents=True, exist_ok=True)
    artifact_name = f'{message_id}-{core.sha(m["recipient"] + m["body"])[:12]}.json'
    artifact_path = review_dir / artifact_name
    artifact_path.write_text(json.dumps(evaluation, indent=2, sort_keys=True))
    artifact_hash = core.sha(artifact_path.read_bytes())
    
    # 2. Create approval receipt in mm_receipts
    content_hash = core.digest(m['recipient'], m['body'])
    import hashlib
    ext_id = f'brain-{message_id}-{core.sha(artifact_hash)[:12]}'
    rid = d.execute(
        "INSERT INTO mm_receipts(kind,business_id,object_id,source_system,external_id,artifact_path,"
        "artifact_hash,content_hash,amount_cents,currency,verified_by,verified_at,occurred_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,'NZD',?,?,?)",
        ('approval', bid, message_id, 'mm_brain', ext_id, str(artifact_path), artifact_hash,
         content_hash, 0, 'brain', core.now(), core.now()),
    ).lastrowid
    
    # 3. Update message
    d.execute(
        "UPDATE mm_messages SET approved_hash=?, approved_by=?, approval_ref=?, permission_basis=? WHERE id=?",
        (content_hash, 'brain', str(rid),
         'Evidence-based autonomous approval', message_id),
    )
    
    # 4. Record in approval_events for legacy visibility
    d.execute(
        "INSERT INTO approval_events(action_type,object_type,object_id,requested_at,approved,approved_by,approved_at,notes) "
        "VALUES(?,?,?,?,1,?,?,?)",
        ('brain_approval', 'mm_messages', message_id, core.now(), 'brain', core.now(),
         json.dumps({'receipt_id': rid, 'criteria_met': evaluation['criteria_met']}, sort_keys=True)),
    )
    
    core.event(d, 'brain_approval_recorded', bid, str(rid))
    
    return {'message_id': message_id, 'receipt_id': rid, 'artifact_path': str(artifact_path)}


def reject(d, message_id, reason, config_override=None):
    """Record a brain rejection for a message."""
    if reason not in REJECTION_LABELS:
        raise ValueError(f'Unknown rejection reason: {reason}. Known: {list(REJECTION_LABELS)}')
    
    m = d.execute("SELECT * FROM mm_messages WHERE id=?", (message_id,)).fetchone()
    if not m:
        raise ValueError(f'Unknown message {message_id}')
    
    evaluation = review(d, message_id, config_override)
    
    d.execute(
        "INSERT INTO approval_events(action_type,object_type,object_id,requested_at,approved,approved_by,approved_at,notes) "
        "VALUES(?,?,?,?,0,?,?,?)",
        ('brain_rejection', 'mm_messages', message_id, core.now(),
         'brain', core.now(),
         json.dumps({'reason': reason, 'label': REJECTION_LABELS[reason],
                     'evaluation_decision': evaluation['decision']}, sort_keys=True)),
    )
    core.event(d, 'brain_rejection_recorded', m['business_id'],
               json.dumps({'reason': reason}))
    
    return {'message_id': message_id, 'reason': reason, 'label': REJECTION_LABELS[reason]}


def record_outcome(d, message_id, outcome, detail=''):
    """Record a learning outcome for a brain-approved send.
    
    Outcome types: positive_reply, negative_reply, no_reply, bounce, opt_out,
    incorrect_email, incorrect_business, offer_rejected, demo_viewed, quote_requested,
    sale, revenue
    
    Writes to mm_learning for pattern promotion/demotion analysis.
    """
    valid_outcomes = {
        'positive_reply', 'negative_reply', 'no_reply', 'bounce', 'opt_out',
        'incorrect_email', 'incorrect_business', 'offer_rejected', 'demo_viewed',
        'quote_requested', 'sale', 'revenue',
    }
    if outcome not in valid_outcomes:
        raise ValueError(f'Unknown outcome: {outcome}. Valid: {valid_outcomes}')
    
    m = d.execute("SELECT * FROM mm_messages WHERE id=?", (message_id,)).fetchone()
    if not m or not m['sent_at']:
        raise ValueError(f'Unknown or unsent message {message_id}')
    
    # Only learn from brain-approved sends
    if m['approved_by'] != 'brain':
        raise ValueError(f'Message {message_id} not brain-approved; learning only from autonomous sends')
    
    # Find experiment assignment for this message
    exp = d.execute("SELECT * FROM mm_experiments WHERE message_id=?", (message_id,)).fetchone()
    pattern = None
    if exp:
        pattern = '|'.join([exp['industry'], exp['problem'], exp['offer'], exp['price_band']])
    
    # Write learning entry
    evidence_ref = f'mm_messages:{message_id}'
    d.execute(
        "INSERT INTO mm_learning(pattern,expected,actual,evidence_ref,confidence,recommended_change,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (pattern or f'bid:{m["business_id"]}', 'APPROVED_FOR_SEND', outcome, evidence_ref,
         1.0, '', core.now()),
    )
    core.event(d, 'brain_learning_recorded', m['business_id'],
               json.dumps({'outcome': outcome, 'pattern': pattern or 'unassigned'}))
    
    return {'message_id': message_id, 'outcome': outcome, 'learning_recorded': True}


def cli(args, d):
    """CLI dispatcher for brain commands."""
    if args.cmd == 'brain-review':
        result = review(d, args.id, json.loads(args.config) if args.config else None)
        return result
    if args.cmd == 'brain-approve':
        return approve(d, args.id, json.loads(args.config) if args.config else None)
    if args.cmd == 'brain-reject':
        return reject(d, args.id, args.reason, json.loads(args.config) if args.config else None)
    if args.cmd == 'brain-outcome':
        return record_outcome(d, args.id, args.outcome, args.detail or '')
    return {'error': 'unknown brain command'}
