"""Deterministic stage handlers for the continuous-operation pipeline.

Each handler(d, item, worker) -> (next_state, reason, evidence). Handlers do
no paid inference: audit/qualification are pure deterministic adapters around
existing engines; anything that would need a model raises BlockedCost.

The outreach worker NEVER sends: it performs the eligibility chain and moves
items to APPROVAL_PENDING, where the evidence-gated approval engine decides.
"""
import json
import math
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from mm_core import root, public_url
from mm_management_worker import management_worker_handler
from mm_pipeline import RetryableError, PermanentError, BlockedCost
from mm_preparation_worker import preparation_worker_handler
from mm_understanding_worker import understanding_worker_handler

REPO = Path(__file__).resolve().parents[1]
AUDIT_TIMEOUT = 60
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


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
            {'defect_count': len(defects),
             'score': result.get('defect_score', result.get('score'))})


def _latest_pipeline_evidence(d, business_id, to_state):
    """Load the newest append-only stage evidence without trusting item payload."""
    row = d.execute(
        "SELECT evidence FROM pipeline_events WHERE business_id=? AND to_state=? "
        "AND evidence IS NOT NULL ORDER BY id DESC LIMIT 1",
        (business_id, to_state),
    ).fetchone()
    if not row:
        return {}
    try:
        decoded = json.loads(row['evidence'])
    except (KeyError, TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _bounded_score(value):
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score):
        return None
    return round(min(100.0, max(0.0, score)), 1)


def _technical_opportunity(audit_evidence):
    """Use the audit stage's own score; missing audit evidence stays unknown."""
    try:
        defect_count = max(0, int(audit_evidence.get('defect_count', 0)))
    except (OverflowError, TypeError, ValueError):
        defect_count = 0
    if defect_count == 0:
        return None, defect_count
    return _bounded_score(audit_evidence.get('score')), defect_count


def qualification_handler(d, it, worker):
    """Keep commercial qualification and technical need as separate evidence axes."""
    import mm_lead_qualifier as lq
    b = _business(d, it['business_id'])

    # Stage outputs live in the append-only event log. pipeline_items.payload is
    # intake data and is not rewritten by worker transitions.
    audit_evidence = _latest_pipeline_evidence(d, b['id'], 'AUDITED')
    understanding = _latest_pipeline_evidence(d, b['id'], 'QUALIFICATION_PENDING')
    technical_score, defect_count = _technical_opportunity(audit_evidence)
    raw_opportunity = understanding.get('opportunity_score')
    commercial_opportunity = (
        raw_opportunity if isinstance(raw_opportunity, dict) else None
    )
    commercial_opportunity_score = (
        _bounded_score(commercial_opportunity.get('score'))
        if commercial_opportunity else None
    )

    # Calculate commercial relevance score from business signals.
    keys = b.keys() if hasattr(b, 'keys') else []
    text = ' '.join(str(v) for v in (b['name'],
                                     b['region'] if 'region' in keys else ''))
    commercial_lead = lq.qualify_lead(text, industry='')
    commercial_score = _bounded_score(commercial_lead['qualification_score']) or 0.0
    commercial_pass = commercial_score >= 30
    technical_pass = technical_score is not None and technical_score >= 40
    qualification_basis = []
    if commercial_pass:
        qualification_basis.append('commercial')
    if technical_pass:
        qualification_basis.append('technical')

    if technical_score is not None and technical_score >= 70:
        technical_tier = 'HIGH_NEED'
    elif technical_pass:
        technical_tier = 'QUALIFIED_NEED'
    else:
        technical_tier = 'LOW_OR_UNKNOWN'
    result = {
        'commercial_score': commercial_score,
        'commercial_qualification_score': commercial_score,
        'commercial_opportunity_score': commercial_opportunity_score,
        'commercial_opportunity': commercial_opportunity,
        'commercial_tier': commercial_lead['tier'],
        'technical_score': technical_score,
        'technical_opportunity_score': technical_score,
        'technical_tier': technical_tier,
        'technical_evidence': {
            'stage': 'AUDITED' if audit_evidence else 'MISSING',
            'defect_count': defect_count,
            'audit_score': audit_evidence.get('score'),
        },
        'qualification_basis': qualification_basis,
        'qualification_reasons': commercial_lead['reasons'],
    }
    if qualification_basis:
        axes = ' and '.join(qualification_basis)
        return (
            'CONTACT_PENDING',
            f'qualified on independent {axes} evidence',
            result,
        )
    result['qualification_reasons'] = list(commercial_lead['reasons']) + [
        'No independent commercial or technical qualification threshold met'
    ]
    return (
        'REJECTED',
        f'not qualified: commercial={commercial_score}, technical={technical_score}',
        result,
    )


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
