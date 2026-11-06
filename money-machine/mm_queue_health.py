"""Read-only queue diagnostics; no migration, probes, providers or recovery."""
import datetime as dt

from mm_core import timestamp


def snapshot(d, at=None):
    at = at or dt.datetime.now(dt.timezone.utc)
    tables = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'pipeline_items' not in tables:
        return {'initialised': False}
    workers = []
    supported = set()
    if 'worker_registry' in tables:
        for row in d.execute('SELECT * FROM worker_registry'):
            w = dict(row)
            supported.update(w['kind'].split(','))
            age = (at - timestamp(w['heartbeat_at'])).total_seconds()
            workers.append({k: w[k] for k in ('worker_id', 'kind', 'started_at', 'heartbeat_at')}
                           | {'heartbeat_age_seconds': max(0, age),
                              'stale': age > 2 * w['lease_seconds']})
    counts = dict(eligible=0, active_leases=0, expired_leases=0, waiting_retry=0,
                  dead_lettered=0, held_or_terminal=0)
    states = {}
    for row in d.execute('SELECT state,lease_until,next_retry_at FROM pipeline_items'):
        state, lease, retry = row
        states[state] = states.get(state, 0) + 1
        if state in ('RETRYABLE_FAILURE', 'PERMANENT_FAILURE'):
            counts['dead_lettered'] += 1
        if lease:
            counts['active_leases' if timestamp(lease) > at else 'expired_leases'] += 1
        if state not in supported:
            counts['held_or_terminal'] += 1
        elif lease and timestamp(lease) > at:
            continue
        elif retry and timestamp(retry) > at:
            counts['waiting_retry'] += 1
        else:
            counts['eligible'] += 1
    if counts['eligible']:
        activity = 'eligible_work_available'
    elif counts['active_leases']:
        activity = 'work_in_flight'
    elif counts['waiting_retry']:
        activity = 'waiting_for_retry'
    else:
        activity = 'idle_no_eligible_work'
    metrics = {r[0]: r[1] for r in d.execute('SELECT name,value FROM mm_metrics')} if 'mm_metrics' in tables else {}
    return {'initialised': True, 'at': at.isoformat(), 'states': states, **counts,
            'activity': activity, 'workers': workers, 'metrics': metrics,
            'eligibility_basis': 'registered worker input states',
            'note': 'Queue activity does not attest supervisor liveness or external safety.'}
