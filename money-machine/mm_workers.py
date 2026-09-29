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
    import mm_opportunity_intelligence as oi

    b = _business(d, it['business_id'])
    if not b['public_website']:
        raise PermanentError('no public website; identity cannot be resolved')
    host = public_url(b['public_website'])  # raises ValueError on private/odd
    observed = {'business_name', 'canonical_host'}
    keys = b.keys() if hasattr(b, 'keys') else ()
    if 'source' in keys and b['source']:
        observed.add('source')
    try:
        payload = json.loads(it['payload'] or '{}')
    except (KeyError, TypeError, ValueError):
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    identity_evidence = {'canonical_host': host}
    for key in ('legal_name', 'trading_name', 'nzbn', 'discovery_quality'):
        value = payload.get(key)
        if value:
            identity_evidence[key] = value
    shadow = oi.shadow_assessment(
        b,
        'IDENTITY_RESOLVED',
        observed=observed,
        evidence=identity_evidence,
    )
    return (
        'AUDIT_PENDING',
        'identity resolved from declared website',
        {'canonical_host': host, 'shadow_intelligence': shadow},
    )


def _audit_evidence(report):
    """Project a canonical toolkit report into pipeline evidence."""
    defects = report.get('defects') or []
    artifacts = report.get('artifacts') or {}
    return {
        'run_id': report.get('run_id'),
        'report_path': artifacts.get('json'),
        'defect_count': len(defects),
        # Qualification treats higher values as greater technical opportunity.
        'score': report.get('defect_score') or report.get('score'),
        'health_score': report.get('health_score'),
        'profile': report.get('profile'),
        'audit_engine': 'auditor_toolkit',
        'model_calls': 0,
        'external_sends': 0,
    }


def audit_handler(d, it, worker):
    """Run/reuse the canonical deterministic auditor_toolkit report.

    Continuous operation must emit the same saved report schema consumed by
    remediation, demo, quote and proof-package builders. AI, browser rendering
    and external local tools are disabled in this always-on pass.
    """
    b = _business(d, it['business_id'])
    url = b['public_website']
    host = urlparse(url).netloc if url else None
    if not url or not host:
        raise PermanentError('public website required for audit')

    output_root = REPO / 'outputs' / 'toolkit'
    from auditor_toolkit.storage import History
    history = History(output_root)
    recent_audit = history.get_latest_valid_audit(host, max_age_days=7)
    if recent_audit:
        return (
            'AUDITED',
            'canonical toolkit audit reused (recent)',
            _audit_evidence(recent_audit),
        )

    from auditor_toolkit.pipeline import AuditOptions, run_audit
    options = AuditOptions(
        output_root=output_root,
        profile='static',
        browser=False,
        deep=False,
        external_tools=False,
        ai=False,
        timeout=min(float(AUDIT_TIMEOUT), 60.0),
    )
    try:
        report = run_audit(url, options)
    except Exception as exc:
        raise RetryableError(
            'auditor_toolkit failed: ' + str(exc)[:240]
        ) from exc

    if report.get('status') != 'complete':
        required_errors = [
            name for name, value in (report.get('checks') or {}).items()
            if value.get('required') and value.get('status') != 'ok'
        ]
        detail = ','.join(required_errors[:8]) or 'required checks incomplete'
        raise RetryableError('auditor_toolkit incomplete: ' + detail)

    return ('AUDITED', 'canonical toolkit audit captured', _audit_evidence(report))


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

    keys = b.keys() if hasattr(b, 'keys') else []
    text = ' '.join(str(v) for v in (
        b['name'], b['region'] if 'region' in keys else ''
    ))
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
    import mm_opportunity_intelligence as oi
    identity_evidence = _latest_pipeline_evidence(d, b['id'], 'IDENTITY_RESOLVED')
    observed = {'business_name'}
    if identity_evidence.get('canonical_host') or b['public_website']:
        observed.add('canonical_host')
    if 'source' in keys and b['source']:
        observed.add('source')
    if audit_evidence:
        observed.add('audit')
    # Do not claim commercial evidence merely because the legacy name+region
    # heuristic emitted a numeric score. Only substantive opportunity evidence
    # from the understanding stage satisfies this shadow completeness check.
    if commercial_opportunity:
        observed.add('commercial_evidence')
    result['shadow_intelligence'] = oi.shadow_assessment(
        b,
        'QUALIFICATION_PENDING',
        observed=observed,
        evidence=identity_evidence,
    )
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

def _email_v2_release_state(d):
    """Return whether Email Finder V2 may persist production observations.

    The email subsystem intentionally has two independent release gates:
    email_policy.mode == v2 and email_release_policy.mode == PRODUCTION for the
    exact verifier version. The contact worker must not weaken either gate just
    to keep the pipeline moving.
    """
    import mm_email as email_engine
    import mm_email_store as email_store

    if not email_store.installed(d):
        return False, {
            'installed': False,
            'email_policy': 'not_migrated',
            'release_mode': 'not_migrated',
            'verifier_version': email_engine.VERSION,
        }

    policy = d.execute(
        "SELECT mode FROM email_policy WHERE id=1"
    ).fetchone()
    release_table = d.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='email_release_policy'"
    ).fetchone()
    release = (
        d.execute(
            "SELECT mode,verifier_version FROM email_release_policy WHERE id=1"
        ).fetchone()
        if release_table else None
    )
    policy_mode = policy['mode'] if policy else 'missing'
    release_mode = release['mode'] if release else 'missing'
    verifier_version = release['verifier_version'] if release else None
    ready = (
        policy_mode == 'v2'
        and release_mode == 'PRODUCTION'
        and verifier_version == email_engine.VERSION
    )
    return ready, {
        'installed': True,
        'email_policy': policy_mode,
        'release_mode': release_mode,
        'verifier_version': verifier_version,
        'required_verifier_version': email_engine.VERSION,
    }


def _current_verified_high(d, bid):
    """Read only the authoritative Email Finder V2 current-selection view."""
    view = d.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='email_current_high'"
    ).fetchone()
    if not view:
        return None
    row = d.execute(
        "SELECT normalized_email,verification_id FROM email_current_high "
        "WHERE prospect_id=? ORDER BY verification_id DESC LIMIT 1",
        (bid,),
    ).fetchone()
    if not row:
        return None
    return {
        'email': row['normalized_email'],
        'verification_id': row['verification_id'],
        'confidence': 'VERIFIED_HIGH',
    }


def contact_handler(d, it, worker):
    """Run Email Finder V2 when released, then trust only current VERIFIED_HIGH.

    No guessed/pattern-generated address can advance this worker. An existing
    current selection from email_current_high may advance immediately.
    Otherwise the worker invokes the existing Email Finder V2 workflow only
    when its independent production-release gates are already open. A held or
    uninstalled finder routes to recoverable NEEDS_REVIEW; after a legitimate
    finder run, absence of a current VERIFIED_HIGH selection is the valid
    NO_VERIFIED_EMAIL terminal outcome.
    """
    bid = it['business_id']

    current = _current_verified_high(d, bid)
    if current:
        return (
            'REMEDIATION_PENDING',
            'current VERIFIED_HIGH Email Finder V2 contact on record',
            {**current, 'finder_run': False, 'external_sends': 0},
        )

    released, release = _email_v2_release_state(d)
    if not released:
        return (
            'NEEDS_REVIEW',
            'Email Finder V2 production release gate is not open',
            {
                'email_finder': release,
                'finder_run': False,
                'external_sends': 0,
                'next_action': (
                    'Complete the existing independent Email Finder V2 release '
                    'review; do not bypass the production gate.'
                ),
            },
        )

    import mm_email_cli

    try:
        status = mm_email_cli.find_one(d, bid)
    except ValueError as exc:
        return (
            'NEEDS_REVIEW',
            'Email Finder V2 held: ' + str(exc)[:240],
            {
                'email_finder': release,
                'finder_run': False,
                'external_sends': 0,
            },
        )

    current = _current_verified_high(d, bid)
    if current:
        return (
            'REMEDIATION_PENDING',
            'Email Finder V2 produced current VERIFIED_HIGH contact',
            {**current, 'finder_run': True, 'external_sends': 0},
        )

    candidates = status.get('candidates') if isinstance(status, dict) else []
    forms = status.get('contact_form_urls') if isinstance(status, dict) else []
    return (
        'NO_VERIFIED_EMAIL',
        'Email Finder V2 completed with no current VERIFIED_HIGH contact',
        {
            'finder_run': True,
            'candidate_count': len(candidates or []),
            'contact_form_count': len(forms or []),
            'external_sends': 0,
        },
    )


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
    'preparation':   (('VERIFIED', 'REMEDIATION_PENDING', 'DEMO_PENDING', 'DEMO_READY', 'QA_PENDING'), preparation_worker_handler),
    'outreach_gate': (('OUTREACH_PENDING',), outreach_handler),
    'management':    (('RESPONDED',), management_worker_handler),
}
