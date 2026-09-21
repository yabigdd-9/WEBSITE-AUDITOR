"""Loop C: use canonical demo and QA gates to prepare reviewable proof."""

from mm_pipeline import PermanentError


def preparation_worker_handler(d, item_row, worker):
    """Delegate only to existing deterministic artifact and QA gates."""
    from mm_workers import demo_handler, qa_handler

    state = item_row['state']
    if state in ('REMEDIATION_PENDING', 'DEMO_PENDING'):
        return demo_handler(d, item_row, worker)
    if state == 'QA_PENDING':
        return qa_handler(d, item_row, worker)
    raise PermanentError('unsupported preparation state: ' + state)
