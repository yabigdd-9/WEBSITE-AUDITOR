"""Loop B: prepare deterministic, evidence-first qualification context."""

from mm_core import opportunity_score_6_component
from mm_pipeline import PermanentError


def understanding_worker_handler(d, item_row, worker):
    """Score available evidence and hand off to the existing qualifier."""
    business = d.execute('SELECT * FROM businesses WHERE id=?', (item_row['business_id'],)).fetchone()
    if not business:
        raise PermanentError('business row missing')
    evidence = d.execute(
        'SELECT m.status,m.confidence FROM mm_evidence e '
        'LEFT JOIN mm_evidence_meta m ON m.evidence_id=e.id '
        'WHERE e.business_id=?', (item_row['business_id'],)
    ).fetchall()
    count = len(evidence)
    verified = [row for row in evidence if row['status'] == 'verified']
    confidence = (sum((row['confidence'] or 0) for row in verified) / len(verified)
                  if verified else 0)
    score = opportunity_score_6_component(
        min(1, count / 3), min(1, count / 3), 0.5 if business['region'] else 0.3,
        0.5, confidence, 0,
    )
    return ('QUALIFICATION_PENDING', 'understanding prepared for deterministic qualification', {
        'evidence_count': count,
        'verified_evidence_count': len(verified),
        'opportunity_score': score,
    })
