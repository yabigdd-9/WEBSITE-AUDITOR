"""Loop D: route responses to a human-owned outcome and learning review."""


def management_worker_handler(d, item_row, worker):
    """A response is evidence to review, never authority to convert or send."""
    return ('NEEDS_REVIEW', 'response requires human outcome and learning review', {
        'business_id': item_row['business_id'],
        'required_action': 'Record a human-reviewed outcome with supporting evidence.',
        'automatic_conversion': False,
        'automatic_send': False,
    })
