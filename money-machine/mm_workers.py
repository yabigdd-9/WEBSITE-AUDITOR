"""Deterministic stage handlers for the continuous-operation pipeline.

Each handler(d, item, worker) -> (next_state, reason, evidence). Handlers do
no paid inference: audit/qualification are pure deterministic adapters around
existing engines; anything that would need a model raises BlockedCost.

The outreach worker NEVER sends: it performs the eligibility chain and moves
items to APPROVAL_PENDING, where the evidence-gated approval engine decides.
"""
import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from mm_core import root, public_url
from mm_management_worker import management_worker_handler
from mm_pipeline import RetryableError, PermanentError, BlockedCost
from mm_preparation_worker import preparation_worker_handler
from mm_understanding_worker import understanding_worker_handler

REPO = Path(__file__).resolve().parents[1]
AUDIT_TIMEOUT = 60


def _business(d, bid):
    r = d.execute("SELECT * FROM businesses WHERE id=?", (bid,)).fetchone()
    if not r:
        raise PermanentError('business row missing')
    return r


def identity_handler(d, it, worker):
    """Resolve canonical identity from the declared public website."""
    b = _business(d, it['business_id'])
    if not b['public_website']:
        raise PermanentError('no public website; identity cannot be resolved')
    host = public_url(b['public_website'])  # raises ValueError on private/odd
    return ('AUDIT_PENDING', 'identity resolved from declared website',
            {'canonical_host': host})


def audit_handler(d, it, worker):
    """Run the deterministic Website Rescue detector for the business site."""
    b = _business(d, it['business_id'])
    url = b['public_website']
    host = urlparse(url).netloc if url else None

    # Check for recent valid audit to reuse
    if host:
        from auditor_toolkit.storage import History
        history = History(str(REPO / 'outputs' / 'toolkit'))
        # Look for audit from last 7 days
        recent_audit = history.get_latest_valid_audit(host, max_age_days=7)
        if recent_audit:
            # Reuse existing audit results
            defects = recent_audit.get('defects', [])
            score = recent_audit.get('score', recent_audit.get('defect_score', 0))
            return ('AUDITED', 'audit reused (recent)',
                    {'defect_count': len(defects), 'score': score})

    # No recent audit found, run new detection
    try:
        r = subprocess.run(
            ['python3', str(REPO / 'engines' / 'detect.py'), url],
            capture_output=True, text=True, timeout=AUDIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RetryableError('audit timed out')
    if r.returncode != 0 or not r.stdout.strip():
        raise RetryableError('detector failed: ' + (r.stderr or '')[-200:])
    try:
        result = json.loads(r.stdout)
    except ValueError:
        raise RetryableError('detector output not JSON')
    result = result[0] if isinstance(result, list) else result
    if isinstance(result, dict) and result.get('error'):
        raise RetryableError('site unreachable: ' + str(result['error'])[:200])
    defects = result.get('defects', result.get('findings', []))
    return ('AUDITED', 'audit captured',
            {'defect_count': len(defects), 'score': result.get('score')})


def qualification_handler(d, it, worker):
    """Deterministic qualification: separate commercial relevance from technical fitness."""
    import mm_lead_qualifier as lq
    b = _business(d, it['business_id'])

    # Get audit results from payload (set by audit_handler)
    audit_payload = it.get('payload', {})
    audit_score = audit_payload.get('score', 0)  # defect score from audit (higher = more defects)
    defect_count = audit_payload.get('defect_count', 0)
    has_audit_evidence = defect_count > 0  # Consider as evidence if we found defects

    # Calculate commercial relevance score from business signals
    ev = d.execute("SELECT id FROM mm_evidence WHERE business_id=? "
                   "ORDER BY id DESC LIMIT 1", (b['id'],)).fetchone()
    keys = b.keys() if hasattr(b, 'keys') else []
    text = ' '.join(str(v) for v in (b['name'],
                                     b['region'] if 'region' in keys else ''))
    commercial_lead = lq.qualify_lead(text, industry='')
    commercial_score = commercial_lead['qualification_score']

    # Calculate technical fitness score (invert defect score so higher = better)
    # For website optimization business: more defects = more opportunity = better prospect
    # We'll use the defect score directly as technical opportunity score
    technical_opportunity_score = min(100, audit_score)  # Cap at 100

    # Qualification logic:
    # A prospect is qualified if they have either:
    # 1. Sufficient commercial relevance (business signals indicate ability to pay/ready to buy)
    # 2. Sufficient technical opportunity (website has issues we can fix)
    # 3. Or both (ideal prospect)
    if commercial_score >= 30 or technical_opportunity_score >= 40:
        # Determine tier based on combined strength
        combined_score = (commercial_score * 0.4) + (technical_opportunity_score * 0.6)
        if combined_score >= 80:
            tier = "HOT"
        elif combined_score >= 55:
            tier = "WARM"
        else:
            tier = "QUALIFIED"

        return ('CONTACT_PENDING', f'qualified: commercial={commercial_score}, technical={technical_opportunity_score}',
                {
                    'commercial_score': commercial_score,
                    'technical_score': technical_opportunity_score,
                    'defect_count': defect_count,
                    'tier': tier,
                    'commercial_tier': commercial_lead['tier'],
                    'qualification_reasons': commercial_lead['reasons']
                })
    else:
        return ('REJECTED', f' insufficient commercial ({commercial_score}) and technical ({technical_opportunity_score}) scores',
                {
                    'commercial_score': commercial_score,
                    'technical_score': technical_opportunity_score,
                    'defect_count': defect_count
                })


def contact_handler(d, it, worker):
    """Contacts come only from Email Finder V2 evidence already recorded.

    This handler never guesses or pattern-generates addresses. If no verified
    observation exists the item routes to NO_VERIFIED_EMAIL (a valid final
    result), not to a fabricated candidate.
    """
    bid = it['business_id']
    rows = d.execute("SELECT email,result_json FROM email_verifications "
                     "WHERE prospect_id=? ORDER BY id DESC", (bid,)).fetchall()
    for row in rows:
        try:
            res = json.loads(row['result_json'])
        except (ValueError, TypeError):
            continue
        if res.get('confidence_label') == 'VERIFIED_HIGH':
            return ('REMEDIATION_PENDING', 'verified contact on record',
                    {'email': row['email'], 'confidence': 'VERIFIED_HIGH'})
    return ('NO_VERIFIED_EMAIL', 'no VERIFIED_HIGH contact; final for email lane',
            {'checked': len(rows)})


def demo_handler(d, it, worker):
    """Demo stage advances only when a real artifact exists.

    Building demos may need a model; that work is planned via the zero-cost
    router and executed under supervision. This handler never fabricates an
    artifact, so a missing demo routes to NEEDS_REVIEW, not DEMO_READY.
    """
    try:
        payload = json.loads(it['payload'] or '{}')
    except ValueError:
        payload = {}
    path = payload.get('demo_path')
    if path and Path(path).is_file() and Path(path).stat().st_size:
        return ('DEMO_READY', 'demo artifact present', {'demo_path': path})
    return ('NEEDS_REVIEW', 'no demo artifact; build is supervised/model work',
            {'expected': 'payload.demo_path'})


def qa_handler(d, it, worker):
    """QA uses the deterministic demo checker when a demo artifact exists."""
    r = d.execute("SELECT * FROM mm_demo_qa WHERE business_id=?",
                  (it['business_id'],)).fetchone()
    if not r:
        return ('NEEDS_REVIEW', 'no demo artifact to QA', None)
    if r['passed']:
        return ('OUTREACH_PENDING', 'demo QA passed', {'score': r['score']})
    return ('NEEDS_REVIEW', 'demo QA failed', {'score': r['score']})


def outreach_handler(d, it, worker):
    """Gate the item into the approval lane. This worker never sends."""
    import mm_approval as appr
    bid = it['business_id']
    ev = appr.evaluate(d, bid)
    if not ev['all_passed']:
        missing = [k for k, v in ev['gates'].items() if not v['passed']]
        return ('NEEDS_REVIEW', 'approval gates failing: ' + ','.join(missing),
                {'gates': {k: v['passed'] for k, v in ev['gates'].items()}})
    return ('APPROVAL_PENDING', 'all approval gates pass; awaiting decision',
            {'gates': 'all_passed'})


WORKERS = {
    'identity':      (('DISCOVERED', 'IDENTITY_PENDING'), identity_handler),
    'audit':         (('AUDIT_PENDING',), audit_handler),
    'understanding': (('AUDITED',), understanding_worker_handler),
    'qualification': (('QUALIFICATION_PENDING',), qualification_handler),
    'contact':       (('QUALIFIED', 'CONTACT_PENDING'), contact_handler),
    'preparation':   (('VERIFIED', 'REMEDIATION_PENDING', 'DEMO_PENDING', 'QA_PENDING'), preparation_worker_handler),
    'outreach_gate': (('OUTREACH_PENDING',), outreach_handler),
    'management':    (('RESPONDED',), management_worker_handler),
}
