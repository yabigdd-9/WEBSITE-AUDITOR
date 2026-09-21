"""Loop A: deterministic discovery hand-off for the canonical pipeline."""

from mm_pipeline import PermanentError

DISCOVERY_ANGLES = ('problem_led', 'strength_led', 'change_led')


def discovery_worker_handler(d, item_row, worker):
    """Move a discovered, real business into identity review without I/O."""
    business = d.execute('SELECT * FROM businesses WHERE id=?', (item_row['business_id'],)).fetchone()
    if not business:
        raise PermanentError('business row missing')
    if not business['public_website']:
        return ('NEEDS_REVIEW', 'discovery record has no declared public website',
                {'discovery_angles': DISCOVERY_ANGLES})
    return ('IDENTITY_PENDING', 'discovery ready for identity resolution', {
        'discovery_angles': DISCOVERY_ANGLES,
        'source': business['source'],
        'declared_website': business['public_website'],
    })
