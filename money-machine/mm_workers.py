"""Deterministic stage handlers for the continuous-operation pipeline.

Each handler(d, item, worker) -> (next_state, reason, evidence). Handlers do
no paid inference: audit/qualification are pure deterministic adapters around
existing engines; anything that would need a model raises BlockedCost.

The outreach worker NEVER sends: it performs the eligibility chain and moves
items to APPROVAL_PENDING, where the evidence-gated approval engine decides.
"""
import hashlib
import json
import math
import sys
from pathlib import Path
from urllib.parse import urlparse

from mm_core import public_url
from mm_management_worker import management_worker_handler
from mm_pipeline import PermanentError, RetryableError
from mm_preparation_worker import preparation_worker_handler
from mm_understanding_worker import understanding_worker_handler

REPO = Path(__file__).resolve().parents[1]
AUDIT_TIMEOUT = 15
DETECTOR_SEVERITY_WEIGHTS = {
    'critical': 30,
    'high': 18,
    'medium': 9,
    'low': 4,
}
MAX_AUDIT_FINDINGS = 100
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _business(d, bid):
    r = d.execute("SELECT * FROM businesses WHERE id=?", (bid,)).fetchone()
    if not r:
        raise PermanentError('business row missing')
    return r


def _commercial_signal_context(d, business):
    """Build qualifier input only from fresh, verified evidence artifacts."""
    keys = set(business.keys()) if hasattr(business, 'keys') else set()
    industry = ''
    if 'industry_id' in keys and business['industry_id']:
        tables = {
            row[0] for row in d.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if 'industries' in tables:
            row = d.execute(
                'SELECT name FROM industries WHERE id=?',
                (business['industry_id'],),
            ).fetchone()
            if row:
                industry = str(row['name'] if hasattr(row, 'keys') else row[0])[:200]

    tables = {
        row[0] for row in d.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if not {'mm_evidence', 'mm_evidence_meta'}.issubset(tables):
        return {'text': '', 'industry': industry, 'evidence_ids': []}

    from mm_core import artifact_valid, fresh

    rows = d.execute(
        'SELECT e.id,e.observation,e.checked_at,m.status,m.confidence,'
        'm.expires_at,m.capture_path,m.capture_hash,m.commercial_relevance '
        'FROM mm_evidence e JOIN mm_evidence_meta m ON m.evidence_id=e.id '
        'WHERE e.business_id=? AND m.status=? AND m.confidence>=0.7 '
        "AND julianday(m.expires_at)>=julianday('now') "
        'ORDER BY julianday(e.checked_at) DESC,e.id DESC LIMIT 10',
        (business['id'], 'verified'),
    ).fetchall()
    observations = []
    evidence_ids = []
    for row in rows:
        if (
            not fresh(row['checked_at'])
            or not artifact_valid(row['capture_path'], row['capture_hash'])
        ):
            continue
        evidence_ids.append(int(row['id']))
        observation = str(row['observation'] or '').strip()[:2000]
        relevance = str(row['commercial_relevance'] or '').strip()[:500]
        if observation:
            observations.append(observation)
        if relevance:
            observations.append(relevance)
    return {
        'text': '\n'.join(observations)[:20000],
        'industry': industry,
        'evidence_ids': evidence_ids,
    }


def _latest_audit_evidence(d, it):
    """Read the persisted audit-stage evidence, with legacy payload fallback."""
    row = d.execute(
        "SELECT evidence FROM pipeline_events WHERE business_id=? "
        "AND to_state='AUDITED' ORDER BY id DESC LIMIT 1",
        (it['business_id'],),
    ).fetchone()
    if row is not None:
        try:
            evidence = json.loads(row['evidence'] or '{}')
        except (KeyError, TypeError, ValueError):
            return {}
        return evidence if isinstance(evidence, dict) else {}
    try:
        payload = json.loads(it['payload'] or '{}')
    except (KeyError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_detector_findings(raw_findings):
    """Bound detector output and retain the evidence used by its score."""
    if not isinstance(raw_findings, list) or len(raw_findings) > MAX_AUDIT_FINDINGS:
        return [], False
    findings = []
    complete = True
    for raw in raw_findings:
        if not isinstance(raw, dict):
            complete = False
            continue
        key = str(raw.get('code') or raw.get('defect_key') or '').strip()[:160]
        severity = str(raw.get('severity') or '').strip().lower()
        title = str(raw.get('finding') or raw.get('defect') or '').strip()[:500]
        observed = str(raw.get('evidence') or raw.get('observed') or '').strip()[:2000]
        if not key or severity not in DETECTOR_SEVERITY_WEIGHTS or not title:
            complete = False
            continue
        if severity != 'low' and not observed:
            complete = False
        identity = raw.get('finding_id')
        if not isinstance(identity, str) or not identity.strip():
            identity = hashlib.sha256(json.dumps(
                [key, severity, title, observed], ensure_ascii=False,
                separators=(',', ':'),
            ).encode()).hexdigest()[:24]
        findings.append({
            'finding_id': identity[:128],
            'defect_key': key,
            'severity': severity,
            'defect': title,
            'observed': observed,
            'evidence_summary': observed,
            'confidence': 'observed' if observed else 'heuristic',
        })
    return findings, complete


def _normalize_toolkit_findings(raw_findings):
    """Keep the P5 evidence fields needed to independently replay a score."""
    if not isinstance(raw_findings, list) or len(raw_findings) > MAX_AUDIT_FINDINGS:
        return [], False
    findings = []
    complete = True
    for raw in raw_findings:
        if not isinstance(raw, dict):
            complete = False
            continue
        key = str(raw.get('defect_key') or '').strip()[:160]
        severity = str(raw.get('severity') or '').strip().lower()
        summary = str(
            raw.get('evidence_summary') or raw.get('observed')
            or raw.get('evidence_source') or raw.get('selector') or ''
        ).strip()[:2000]
        identity = str(raw.get('finding_id') or '').strip()[:128]
        if not key or severity not in DETECTOR_SEVERITY_WEIGHTS or not identity:
            complete = False
            continue
        if severity != 'low' and not summary:
            complete = False
        findings.append({
            'finding_id': identity,
            'defect_key': key,
            'severity': severity,
            'defect': str(raw.get('defect') or raw.get('title') or key)[:500],
            'observed': str(raw.get('observed') or '')[:2000],
            'evidence_summary': summary,
            'evidence_ref': str(raw.get('evidence_ref') or '')[:160],
            'confidence': raw.get('confidence', 'heuristic'),
        })
    return findings, complete


def _score_audit_findings(findings, method):
    """Replay the bounded technical opportunity score from stored findings."""
    if method == 'detector-severity-v1':
        return min(100, sum(
            DETECTOR_SEVERITY_WEIGHTS[finding['severity']]
            for finding in findings
        ))
    if method == 'toolkit-p5-v1':
        from auditor_toolkit.scoring import score_from_findings

        return score_from_findings(findings, complete=True).severity_total
    return 0


def _bounded_defect_score(value):
    """Return a finite 0..100 defect score; malformed scores are unscored."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if not math.isfinite(float(value)):
        return 0
    return max(0, min(100, value))


def _defect_count(value):
    return len(value) if isinstance(value, (list, tuple)) else 0


def identity_handler(d, it, worker):
    """Resolve canonical identity from the declared public website."""
    b = _business(d, it['business_id'])
    if not b['public_website']:
        raise PermanentError('no public website; identity cannot be resolved')
    host = public_url(b['public_website'])  # raises ValueError on private/odd
    return ('AUDIT_PENDING', 'identity resolved from declared website',
            {'canonical_host': host})


def _recent_audit_result(host):
    if not host:
        return None
    from auditor_toolkit.storage import History

    history = History(str(REPO / 'outputs' / 'toolkit'))
    recent_audit = history.get_latest_valid_audit(host, max_age_days=7)
    if not recent_audit:
        return None
    findings, valid = _normalize_toolkit_findings(recent_audit.get('defects'))
    method = 'toolkit-p5-v1'
    score = _score_audit_findings(findings, method) if valid else 0
    reported_breakdown = recent_audit.get('breakdown') or {}
    if (
        not isinstance(reported_breakdown, dict)
        or reported_breakdown.get('severity_total') != score
    ):
        valid = False
        score = 0
    return (
        'AUDITED',
        'audit reused (recent)',
        {
            'audit_run_id': str(recent_audit.get('run_id') or '')[:128],
            'audit_source': 'auditor_toolkit_history',
            'score_method': method,
            'finding_evidence_complete': valid,
            'findings': findings,
            'defect_count': len(findings),
            'score': _bounded_defect_score(score),
        },
    )


def _run_audit(url):
    """Run the canonical DNS-pinned audit engine with a bounded static profile."""
    from auditor_toolkit.pipeline import AuditOptions, run_audit

    try:
        report = run_audit(
            url,
            AuditOptions(
                output_root=REPO / 'outputs' / 'toolkit',
                allow_private=False,
                browser=False,
                tls=False,
                timeout=AUDIT_TIMEOUT,
                profile='static',
                deep=False,
                max_pages=1,
                max_links=20,
                cache=False,
                ai=False,
                external_tools=False,
            ),
        )
    except TimeoutError as exc:
        raise RetryableError('audit timed out') from exc
    except ValueError as exc:
        raise PermanentError('audit URL rejected: ' + str(exc)[:200]) from exc

    findings, valid = _normalize_toolkit_findings(report.get('defects'))
    method = 'toolkit-p5-v1'
    replayed_score = _score_audit_findings(findings, method) if valid else 0
    breakdown = report.get('breakdown') or {}
    complete = report.get('status') == 'complete'
    score_matches = (
        isinstance(breakdown, dict)
        and breakdown.get('severity_total') == replayed_score
    )
    evidence_complete = valid and complete and score_matches
    score = replayed_score if evidence_complete else 0
    return ('AUDITED', 'canonical audit ' + ('complete' if complete else 'partial'),
            {
                'audit_run_id': str(report.get('run_id') or '')[:128],
                'audit_source': 'auditor_toolkit',
                'audit_status': str(report.get('status') or 'unknown')[:32],
                'score_method': method,
                'finding_evidence_complete': evidence_complete,
                'reported_score_matches_findings': score_matches,
                'findings': findings,
                'defect_count': len(findings),
                'score': _bounded_defect_score(score),
                'audit_coverage': report.get('coverage') or {},
            })


def audit_handler(d, it, worker):
    """Run the deterministic Website Rescue detector for the business site."""
    b = _business(d, it['business_id'])
    url = b['public_website']
    host = urlparse(url).netloc if url else None
    recent_result = _recent_audit_result(host)
    if recent_result is not None:
        return recent_result
    return _run_audit(url)


def _technical_tier(score):
    if score >= 80:
        return 'HIGH_OPPORTUNITY'
    if score >= 60:
        return 'MEDIUM_OPPORTUNITY'
    if score >= 40:
        return 'OPPORTUNITY'
    return 'LOW'


def _qualification_result(commercial_lead, commercial_score, technical_score, defect_count):
    commercial_qualified = commercial_score >= 30
    technical_qualified = technical_score >= 40
    technical_tier = _technical_tier(technical_score)
    if not commercial_qualified and not technical_qualified:
        return (
            'REJECTED',
            f' insufficient commercial ({commercial_score}) and technical ({technical_score}) scores',
            {
                'commercial_score': commercial_score,
                'technical_score': technical_score,
                'defect_count': defect_count,
                'qualification_basis': 'none',
                'technical_tier': technical_tier,
            },
        )

    if commercial_qualified and technical_qualified:
        qualification_basis = 'both'
    elif commercial_qualified:
        qualification_basis = 'commercial'
    else:
        qualification_basis = 'technical'
    tier = commercial_lead['tier'] if commercial_qualified else 'TECHNICAL_OPPORTUNITY'
    return (
        'CONTACT_PENDING',
        f'qualified: commercial={commercial_score}, technical={technical_score}',
        {
            'commercial_score': commercial_score,
            'technical_score': technical_score,
            'defect_count': defect_count,
            'tier': tier,
            'qualification_basis': qualification_basis,
            'commercial_tier': commercial_lead['tier'],
            'technical_tier': technical_tier,
            'qualification_reasons': commercial_lead['reasons'],
        },
    )


def qualification_handler(d, it, worker):
    """Deterministic qualification: separate commercial relevance from technical fitness."""
    import mm_lead_qualifier as lq
    b = _business(d, it['business_id'])

    # Pipeline items are sqlite3.Row values; decode their JSON payload before
    # reading fields. sqlite3.Row supports indexing but not dict.get().
    audit_payload = _latest_audit_evidence(d, it)
    # Malformed historical evidence cannot create technical qualification.
    score_method = audit_payload.get('score_method')
    raw_findings = audit_payload.get('findings')
    findings_valid = bool(audit_payload.get('finding_evidence_complete'))
    if not isinstance(raw_findings, list) or len(raw_findings) > MAX_AUDIT_FINDINGS:
        findings_valid = False
        findings = []
    elif score_method == 'detector-severity-v1':
        findings, normalized = _normalize_detector_findings(raw_findings)
        findings_valid = findings_valid and normalized and len(findings) == len(raw_findings)
    elif score_method == 'toolkit-p5-v1':
        findings, normalized = _normalize_toolkit_findings(raw_findings)
        findings_valid = findings_valid and normalized and len(findings) == len(raw_findings)
    else:
        findings_valid = False
        findings = []
    replayed_score = _score_audit_findings(findings, score_method) if findings_valid else 0
    audit_score = (
        replayed_score
        if _bounded_defect_score(audit_payload.get('score', 0)) == replayed_score
        else 0
    )
    raw_defect_count = audit_payload.get('defect_count')
    if (
        not isinstance(raw_defect_count, int)
        or isinstance(raw_defect_count, bool)
        or raw_defect_count != len(findings)
    ):
        findings_valid = False
        audit_score = 0
    defect_count = len(findings) if findings_valid else 0

    # Commercial value comes from fresh verified captures, not name/region alone.
    commercial_context = _commercial_signal_context(d, b)
    commercial_lead = lq.qualify_lead(
        commercial_context['text'], industry=commercial_context['industry']
    )
    commercial_score = commercial_lead['qualification_score']

    state, reason, result = _qualification_result(
        commercial_lead, commercial_score, audit_score, defect_count
    )
    result.update({
        'audit_run_id': str(audit_payload.get('audit_run_id') or '')[:128],
        'technical_score_method': score_method or 'unverified_legacy',
        'technical_score_finding_ids': [
            str(finding.get('finding_id', ''))[:128] for finding in findings
        ],
        'technical_score_evidence_complete': findings_valid,
        'commercial_score_evidence_ids': commercial_context['evidence_ids'],
        'commercial_score_industry': commercial_context['industry'],
        'commercial_score_basis': commercial_lead.get('basis', 'unspecified'),
    })
    return state, reason, result


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
