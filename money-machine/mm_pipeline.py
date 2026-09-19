"""Continuous-operation pipeline: state machine, leased work queue, workers.

Deterministic orchestration layer for the Money Machine. No model calls and no
network access in this module; handlers that need either are injected and must
declare their external service so circuit breakers and rate limits apply.

Design rules:
  * One failed worker never stops the machine: stages are independent queues.
  * Workers are idempotent, bounded, retryable, restartable, observable,
    rate-limited and independently recoverable.
  * Every state transition is validated against the declared state machine and
    recorded in pipeline_events (append-only audit).
  * Failure handling: exponential backoff with jitter, retry counters,
    dead-letter after max attempts, circuit breakers per external service.
"""
import datetime as dt
import json
import os
import random
import socket
from pathlib import Path

from mm_core import now, root, sha, timestamp

# ---------------------------------------------------------------------------
# Canonical prospect state machine (trial-specified model)
# ---------------------------------------------------------------------------

HAPPY_PATH = (
    'DISCOVERED', 'IDENTITY_PENDING', 'IDENTITY_RESOLVED', 'AUDIT_PENDING',
    'AUDITED', 'QUALIFICATION_PENDING', 'QUALIFIED', 'CONTACT_PENDING',
    'CONTACT_RESOLVED', 'VERIFICATION_PENDING', 'VERIFIED',
    'REMEDIATION_PENDING', 'DEMO_PENDING', 'DEMO_READY', 'QA_PENDING',
    'OUTREACH_PENDING', 'APPROVAL_PENDING', 'APPROVED', 'READY_TO_SEND',
    'SENT', 'RESPONDED', 'CONVERTED',
)
ALTERNATE = (
    'REJECTED', 'NO_VERIFIED_EMAIL', 'NEEDS_REVIEW', 'RETRYABLE_FAILURE',
    'PERMANENT_FAILURE', 'SUPPRESSED', 'DUPLICATE', 'DEPLOYMENT_FAILED',
)
STATES = HAPPY_PATH + ALTERNATE
TERMINAL = ('CONVERTED', 'REJECTED', 'NO_VERIFIED_EMAIL', 'PERMANENT_FAILURE',
            'SUPPRESSED', 'DUPLICATE')

_FORWARD = {HAPPY_PATH[i]: HAPPY_PATH[i + 1] for i in range(len(HAPPY_PATH) - 1)}
TRANSITIONS = {s: set() for s in STATES}
for _a, _b in _FORWARD.items():
    TRANSITIONS[_a].add(_b)
for _s in HAPPY_PATH:
    if _s not in TERMINAL:
        TRANSITIONS[_s].update(('REJECTED', 'NO_VERIFIED_EMAIL', 'NEEDS_REVIEW',
                                'RETRYABLE_FAILURE', 'PERMANENT_FAILURE',
                                'SUPPRESSED', 'DUPLICATE'))
# Recovery edges: review can requeue work deterministically.
TRANSITIONS['NEEDS_REVIEW'] = {'IDENTITY_PENDING', 'AUDIT_PENDING',
                               'QUALIFICATION_PENDING', 'CONTACT_PENDING',
                               'VERIFICATION_PENDING', 'SUPPRESSED', 'REJECTED'}
TRANSITIONS['RETRYABLE_FAILURE'] = set(s for s in HAPPY_PATH if s.endswith('_PENDING'))

DDL = """
CREATE TABLE IF NOT EXISTS pipeline_items(
  business_id INTEGER PRIMARY KEY REFERENCES businesses(id),
  state TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_retry_at TEXT,
  lease_owner TEXT,
  lease_until TEXT,
  heartbeat_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pipeline_events(
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  actor TEXT NOT NULL,
  reason TEXT NOT NULL,
  evidence TEXT,
  event_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS worker_registry(
  worker_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  hostname TEXT NOT NULL,
  pid INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  lease_seconds INTEGER NOT NULL DEFAULT 300);
CREATE TABLE IF NOT EXISTS circuit_breakers(
  service TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK(state IN ('closed','open','half_open')),
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  opened_at TEXT,
  cooldown_until TEXT,
  failure_threshold INTEGER NOT NULL DEFAULT 5,
  cooldown_seconds INTEGER NOT NULL DEFAULT 300);
CREATE TABLE IF NOT EXISTS rate_buckets(
  bucket TEXT PRIMARY KEY,
  window_start TEXT NOT NULL,
  window_seconds INTEGER NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  cap INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mm_metrics(
  name TEXT PRIMARY KEY,
  value INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_pipeline_items_state ON pipeline_items(state);
CREATE INDEX IF NOT EXISTS idx_pipeline_events_business ON pipeline_events(business_id);
"""


EVENTS_DDL = """CREATE TABLE IF NOT EXISTS pipeline_events(
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  actor TEXT NOT NULL,
  reason TEXT NOT NULL,
  evidence TEXT,
  event_at TEXT NOT NULL);
"""


def migrate(d):
    """Idempotent DDL apply; safe to call on every worker start.

    Also repairs schema drift: a legacy pipeline_events shape (business_id,
    stage, event_at, detail) is rebuilt into the current shape with every row
    preserved, because the event trail is append-only history.
    """
    d.executescript(DDL)
    cols = {r[1] for r in d.execute('PRAGMA table_info(pipeline_events)')}
    if cols and 'to_state' not in cols:  # legacy shape from an earlier build
        d.execute('ALTER TABLE pipeline_events RENAME TO pipeline_events_legacy')
        d.executescript(EVENTS_DDL)
        d.execute("INSERT INTO pipeline_events(business_id,from_state,to_state,"
                  "actor,reason,evidence,event_at) SELECT business_id,NULL,"
                  "stage,'legacy',coalesce(detail,'legacy row'),NULL,event_at "
                  "FROM pipeline_events_legacy")
        kept = d.execute('SELECT changes()').fetchone()[0]
        d.execute('DROP TABLE pipeline_events_legacy')
        d.commit()
        log({'kind': 'schema_drift_repaired', 'table': 'pipeline_events',
             'rows_preserved': kept})


class RetryableError(Exception):
    """Transient failure: item is rescheduled with exponential backoff."""

class PermanentError(Exception):
    """Unrecoverable failure for this item: dead-letter immediately."""

class BlockedCost(Exception):
    """No free model/provider route: defer, never fall back to paid."""


# ---------------------------------------------------------------------------
# Structured logging + metrics
# ---------------------------------------------------------------------------

def _log_path():
    d = root() / 'state' / 'worker-logs'
    d.mkdir(parents=True, exist_ok=True)
    return d / (dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d') + '.jsonl')


def log(record):
    """Append one structured JSON log record. Never raises."""
    try:
        record = dict(record)
        record.setdefault('at', now())
        with open(_log_path(), 'a') as fh:
            fh.write(json.dumps(record, sort_keys=True) + '\n')
    except OSError:
        pass


def metric(d, name, delta=1):
    d.execute("INSERT INTO mm_metrics(name,value,updated_at) VALUES(?,?,?) "
              "ON CONFLICT(name) DO UPDATE SET value=value+excluded.value,"
              "updated_at=excluded.updated_at", (name, delta, now()))


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

def enqueue(d, business_id, state='DISCOVERED', payload=None, max_attempts=5):
    """Register a business in the pipeline exactly once (idempotent)."""
    if state not in STATES:
        raise ValueError('Unknown pipeline state: ' + state)
    d.execute("INSERT INTO pipeline_items(business_id,state,payload,max_attempts,"
              "next_retry_at,created_at,updated_at) VALUES(?,?,?,?,NULL,?,?) "
              "ON CONFLICT(business_id) DO NOTHING",
              (business_id, state, json.dumps(payload or {}), max_attempts,
               now(), now()))
    if d.execute("SELECT changes()").fetchone()[0]:
        _record(d, business_id, None, state, 'enqueue', 'enqueued', None)
    return item(d, business_id)


# ---------------------------------------------------------------------------
# Leases + heartbeats
# ---------------------------------------------------------------------------

def register_worker(d, worker_id, kind, lease_seconds=300):
    d.execute("INSERT INTO worker_registry(worker_id,kind,hostname,pid,"
              "started_at,heartbeat_at,lease_seconds) VALUES(?,?,?,?,?,?,?) "
              "ON CONFLICT(worker_id) DO UPDATE SET heartbeat_at=excluded."
              "heartbeat_at,pid=excluded.pid,lease_seconds=excluded.lease_seconds",
              (worker_id, kind, socket.gethostname(), os.getpid(), now(),
               now(), lease_seconds))
    return worker_id


def heartbeat(d, worker_id, business_id=None):
    d.execute("UPDATE worker_registry SET heartbeat_at=? WHERE worker_id=?",
              (now(), worker_id))
    if business_id is not None:
        d.execute("UPDATE pipeline_items SET heartbeat_at=? WHERE business_id=?"
                  " AND lease_owner=?", (now(), business_id, worker_id))


def claim(d, states, worker_id, lease_seconds=300, limit=1):
    """Claim up to `limit` items in `states`. Expired leases are recoverable."""
    at = dt.datetime.now(dt.timezone.utc)
    until = (at + dt.timedelta(seconds=lease_seconds)).isoformat()
    marks = ','.join('?' * len(states))
    rows = d.execute(
        "SELECT * FROM pipeline_items WHERE state IN (%s) "
        "AND (next_retry_at IS NULL OR next_retry_at<=?) "
        "ORDER BY updated_at LIMIT ?" % marks,
        tuple(states) + (at.isoformat(), limit)).fetchall()
    got = []
    for r in rows:
        if r['lease_until'] and timestamp(r['lease_until']) > at:
            continue  # actively leased by another worker
        cur = d.execute(
            "UPDATE pipeline_items SET lease_owner=?,lease_until=?,"
            "heartbeat_at=?,updated_at=? WHERE business_id=? AND "
            "(lease_until IS NULL OR lease_until<=?)",
            (worker_id, until, now(), now(), r['business_id'], at.isoformat()))
        if cur.rowcount:
            got.append(item(d, r['business_id']))
    return got


def release(d, business_id, worker_id):
    d.execute("UPDATE pipeline_items SET lease_owner=NULL,lease_until=NULL "
              "WHERE business_id=? AND lease_owner=?", (business_id, worker_id))


# ---------------------------------------------------------------------------
# Retry / backoff / dead-letter
# ---------------------------------------------------------------------------

def backoff_seconds(attempts, base=30, cap=3600, jitter=0.2):
    delay = min(cap, base * (2 ** max(0, attempts - 1)))
    return delay * (1 + random.uniform(-jitter, jitter))


def fail(d, business_id, worker_id, error, retryable=True):
    """Record a failure; schedule retry or dead-letter."""
    r = item(d, business_id)
    attempts = r['attempts'] + 1
    msg = str(error)[:500]
    if retryable and attempts < r['max_attempts']:
        nxt = (dt.datetime.now(dt.timezone.utc)
               + dt.timedelta(seconds=backoff_seconds(attempts))).isoformat()
        d.execute("UPDATE pipeline_items SET attempts=?,next_retry_at=?,"
                  "last_error=?,lease_owner=NULL,lease_until=NULL,updated_at=? "
                  "WHERE business_id=?", (attempts, nxt, msg, now(), business_id))
        _record(d, business_id, r['state'], r['state'], worker_id,
                'retryable_failure: ' + msg, {'attempts': attempts})
        outcome = 'retry_scheduled'
    else:
        to = 'RETRYABLE_FAILURE' if retryable else 'PERMANENT_FAILURE'
        d.execute("UPDATE pipeline_items SET attempts=?,last_error=?,"
                  "lease_owner=NULL,lease_until=NULL,updated_at=? "
                  "WHERE business_id=?", (attempts, msg, now(), business_id))
        if r['state'] not in TERMINAL:
            transition(d, business_id, to, worker_id,
                       'dead-lettered after %d attempts: %s' % (attempts, msg),
                       {'attempts': attempts})
        outcome = 'dead_lettered'
    metric(d, 'pipeline.items.' + outcome)
    log({'kind': 'failure', 'business_id': business_id, 'worker': worker_id,
         'error': msg, 'outcome': outcome, 'attempts': attempts})
    return outcome


# States beyond this boundary are owned by the approval/send engines, never
# by a stage handler: a worker must not be able to walk an item into APPROVED
# or SENT on its own. (Trial rule: fail closed when mandatory evidence is absent.)
POST_APPROVAL = ('APPROVED', 'READY_TO_SEND', 'SENT', 'RESPONDED', 'CONVERTED')
MAX_AUTO_ADVANCE = 8


def advance(d, business_id, to_state, actor, reason, evidence=None):
    """Move an item to `to_state`, walking declared gate states if needed.

    A stage handler reports the state whose evidence it just produced (for
    example AUDIT_PENDING after capturing an audit). Intermediate gate states
    on the declared chain are recorded individually, so every edge stays
    auditable. Handlers cannot cross POST_APPROVAL and cannot move backward.
    """
    if to_state in POST_APPROVAL:
        raise ValueError('Handler may not cross the approval boundary (%s); '
                         'use the approval/send engine' % to_state)
    cur = item(d, business_id)
    if to_state in ALTERNATE or to_state == cur['state']:
        return transition(d, business_id, to_state, actor, reason, evidence)
    chain = list(HAPPY_PATH)
    try:
        start = chain.index(cur['state'])
        end = chain.index(to_state)
    except ValueError:
        return transition(d, business_id, to_state, actor, reason, evidence)
    if end < start:
        raise ValueError('Illegal backward transition %s -> %s'
                         % (cur['state'], to_state))
    if end - start > MAX_AUTO_ADVANCE:
        raise ValueError('Refusing to auto-advance %d steps (%s -> %s)'
                         % (end - start, cur['state'], to_state))
    last = cur
    for i in range(start + 1, end + 1):
        step = chain[i]
        last = transition(d, business_id, step, actor,
                          reason if i == end else 'auto-advance to ' + to_state,
                          evidence if i == end else None)
    return last


def mark_sent(d, business_id, actor, provider_message_id):
    """Record a verified send. Requires a 'sent' ledger row from the transport.

    This is the only path into SENT: it demands provider evidence, so an
    unverified claim of delivery cannot advance the pipeline.
    """
    import mm_approval as appr
    appr.migrate(d)
    row = d.execute("SELECT * FROM outreach_send_ledger WHERE business_id=? "
                    "AND status='sent' AND provider_message_id IS NOT NULL "
                    "ORDER BY rowid DESC LIMIT 1", (business_id,)).fetchone()
    if not row or row['provider_message_id'] != provider_message_id:
        raise ValueError('Provider-verified sent ledger row required before SENT')
    cur = item(d, business_id)['state']
    if cur != 'READY_TO_SEND':
        raise ValueError('READY_TO_SEND required before SENT (at %s)' % cur)
    metric(d, 'pipeline.items.sent')
    return transition(d, business_id, 'SENT', actor,
                      'provider-verified send: ' + str(provider_message_id),
                      {'provider_message_id': provider_message_id,
                       'idempotency_key': row['idempotency_key']})


def complete(d, business_id, worker_id, to_state, reason='ok', evidence=None):
    release(d, business_id, worker_id)
    d.execute("UPDATE pipeline_items SET attempts=0,next_retry_at=NULL "
              "WHERE business_id=?", (business_id,))
    metric(d, 'pipeline.items.completed')
    return advance(d, business_id, to_state, worker_id, reason, evidence)




# ---------------------------------------------------------------------------
# Circuit breakers (persisted, shared across workers)
# ---------------------------------------------------------------------------

def breaker(d, service, threshold=5, cooldown_seconds=300):
    d.execute("INSERT INTO circuit_breakers(service,state,failure_threshold,"
              "cooldown_seconds) VALUES(?,?,?,?) ON CONFLICT(service) DO NOTHING",
              (service, 'closed', threshold, cooldown_seconds))
    return d.execute("SELECT * FROM circuit_breakers WHERE service=?",
                     (service,)).fetchone()


def breaker_allow(d, service):
    b = breaker(d, service)
    if b['state'] == 'closed':
        return True
    if b['state'] == 'open':
        if b['cooldown_until'] and timestamp(b['cooldown_until']) <= dt.datetime.now(dt.timezone.utc):
            d.execute("UPDATE circuit_breakers SET state='half_open' WHERE service=?", (service,))
            return True
        return False
    return True  # half_open: a single probe is permitted


def breaker_success(d, service):
    breaker(d, service)
    d.execute("UPDATE circuit_breakers SET state='closed',consecutive_failures=0,"
              "opened_at=NULL,cooldown_until=NULL WHERE service=?", (service,))


def breaker_failure(d, service):
    b = breaker(d, service)
    fails = b['consecutive_failures'] + 1
    if fails >= b['failure_threshold']:
        until = (dt.datetime.now(dt.timezone.utc)
                 + dt.timedelta(seconds=b['cooldown_seconds'])).isoformat()
        d.execute("UPDATE circuit_breakers SET state='open',consecutive_failures=?,"
                  "opened_at=?,cooldown_until=? WHERE service=?",
                  (fails, now(), until, service))
        log({'kind': 'circuit_open', 'service': service, 'failures': fails})
    else:
        d.execute("UPDATE circuit_breakers SET consecutive_failures=? WHERE service=?",
                  (fails, service))


# ---------------------------------------------------------------------------
# Rate limits (persisted fixed window, e.g. 20 outreach sends/day)
# ---------------------------------------------------------------------------

def rate_ok(d, bucket, cap, window_seconds):
    at = dt.datetime.now(dt.timezone.utc)
    d.execute("INSERT INTO rate_buckets(bucket,window_start,window_seconds,count,cap)"
              " VALUES(?,?,?,0,?) ON CONFLICT(bucket) DO NOTHING",
              (bucket, at.isoformat(), window_seconds, cap))
    b = d.execute("SELECT * FROM rate_buckets WHERE bucket=?", (bucket,)).fetchone()
    if timestamp(b['window_start']) + dt.timedelta(seconds=b['window_seconds']) <= at:
        d.execute("UPDATE rate_buckets SET window_start=?,count=0,window_seconds=?,cap=? "
                  "WHERE bucket=?", (at.isoformat(), window_seconds, cap, bucket))
        b = d.execute("SELECT * FROM rate_buckets WHERE bucket=?", (bucket,)).fetchone()
    if b['count'] >= b['cap']:
        return False
    d.execute("UPDATE rate_buckets SET count=count+1 WHERE bucket=?", (bucket,))
    return True


# ---------------------------------------------------------------------------
# Health snapshot (observability surface)
# ---------------------------------------------------------------------------

def health(d):
    migrate(d)
    states = {r['state']: r['n'] for r in d.execute(
        "SELECT state,count(*) n FROM pipeline_items GROUP BY state")}
    workers = [dict(r) for r in d.execute("SELECT * FROM worker_registry")]
    at = dt.datetime.now(dt.timezone.utc)
    for w in workers:
        w['alive'] = (at - timestamp(w['heartbeat_at'])) < dt.timedelta(seconds=2 * w['lease_seconds'])
    breakers = {r['service']: r['state'] for r in d.execute("SELECT * FROM circuit_breakers")}
    buckets = {r['bucket']: {'count': r['count'], 'cap': r['cap']}
               for r in d.execute("SELECT * FROM rate_buckets")}
    metrics = {r['name']: r['value'] for r in d.execute("SELECT * FROM mm_metrics")}
    leased = d.execute("SELECT count(*) FROM pipeline_items WHERE lease_until IS NOT NULL "
                       "AND lease_until>?", (at.isoformat(),)).fetchone()[0]
    return {'at': now(), 'states': states, 'workers': workers,
            'circuit_breakers': breakers, 'rate_buckets': buckets,
            'metrics': metrics, 'active_leases': leased}

def item(d, business_id):
    r = d.execute("SELECT * FROM pipeline_items WHERE business_id=?",
                  (business_id,)).fetchone()
    if not r:
        raise ValueError('No pipeline item for business ' + str(business_id))
    return r


def _record(d, bid, frm, to, actor, reason, evidence):
    d.execute("INSERT INTO pipeline_events(business_id,from_state,to_state,"
              "actor,reason,evidence,event_at) VALUES(?,?,?,?,?,?,?)",
              (bid, frm, to, actor, reason,
               json.dumps(evidence) if evidence else None, now()))


def transition(d, business_id, to_state, actor, reason, evidence=None):
    """Validated state transition with append-only audit record."""
    if to_state not in STATES:
        raise ValueError('Unknown pipeline state: ' + to_state)
    r = item(d, business_id)
    frm = r['state']
    if frm == to_state:
        return r
    if frm in TERMINAL:
        raise ValueError('Terminal state %s has no outgoing transitions' % frm)
    if to_state not in TRANSITIONS.get(frm, ()):  # fail closed on illegal edge
        raise ValueError('Illegal transition %s -> %s' % (frm, to_state))
    d.execute("UPDATE pipeline_items SET state=?,last_error=NULL,updated_at=? "
              "WHERE business_id=?", (to_state, now(), business_id))
    _record(d, business_id, frm, to_state, actor, reason, evidence)
    return item(d, business_id)


# ---------------------------------------------------------------------------
# Worker: bounded, restartable processing loop
# ---------------------------------------------------------------------------

class Worker:
    """One bounded worker for a set of input states.

    handler(d, item_row, worker) must return (next_state, reason, evidence)
    or raise RetryableError / PermanentError / BlockedCost. Handlers declare
    external `services` so the worker applies circuit breakers around them.
    """

    def __init__(self, worker_id, states, handler, services=(),
                 lease_seconds=300, rate_bucket=None, rate_cap=None,
                 rate_window=86400):
        self.worker_id = worker_id
        self.states = tuple(states)
        self.kind = ','.join(self.states)
        self.handler = handler
        self.services = tuple(services)
        self.lease_seconds = lease_seconds
        self.rate_bucket = rate_bucket
        self.rate_cap = rate_cap
        self.rate_window = rate_window

    def run_once(self, d, limit=1):
        """Claim and process up to `limit` items. Bounded: always returns."""
        migrate(d)
        register_worker(d, self.worker_id, kind=','.join(self.states),
                        lease_seconds=self.lease_seconds)
        processed = 0
        for it in claim(d, self.states, self.worker_id,
                        lease_seconds=self.lease_seconds, limit=limit):
            bid = it['business_id']
            try:
                if self.rate_bucket and not rate_ok(d, self.rate_bucket,
                                                    self.rate_cap or 0,
                                                    self.rate_window):
                    raise RetryableError('rate limit reached for ' + self.rate_bucket)
                for svc in self.services:
                    if not breaker_allow(d, svc):
                        raise RetryableError('circuit open for ' + svc)
                try:
                    nxt, reason, evidence = self.handler(d, it, self)
                except (RetryableError, PermanentError, BlockedCost):
                    raise
                except Exception as ex:  # unknown faults are retryable, bounded
                    raise RetryableError('%s: %s' % (type(ex).__name__, ex))
                for svc in self.services:
                    breaker_success(d, svc)
                try:
                    complete(d, bid, self.worker_id, nxt, reason, evidence)
                except Exception as ex:
                    # A bad handler target must never crash the worker loop:
                    # record it as a bounded retryable failure instead.
                    raise RetryableError('completion rejected: %s: %s'
                                         % (type(ex).__name__, ex))
                processed += 1
            except BlockedCost as ex:
                for svc in self.services:
                    breaker_failure(d, svc)
                fail(d, bid, self.worker_id, 'BLOCKED_COST: %s' % ex)
            except RetryableError as ex:
                for svc in self.services:
                    breaker_failure(d, svc)
                fail(d, bid, self.worker_id, ex)
            except PermanentError as ex:
                fail(d, bid, self.worker_id, ex, retryable=False)
            heartbeat(d, self.worker_id)
        return processed


def run_pipelineloop(d, workers, sleep_seconds=60, max_cycles=None,
                     report_every=10, log_destination=None):
    """Bounded, restartable, deterministic continuous pipeline loop.

    Each cycle: migrate(state), claim a few items per worker set, process each
    once, heartbeat, report a compact metrics snapshot. The loop is entirely
    opt-in and must be started by an authorized operator/controller; it emits
    metrics but never takes external actions by itself (sends/approvals are
    still gated by the approval engine).
    """
    metrics_sink = log_destination or (root() / 'state' / 'worker-logs')
    migrate(d)
    for idx, w in enumerate(workers):
        register_worker(d, w.worker_id, w.kind, lease_seconds=w.lease_seconds)
    cycles = 0
    try:
        while max_cycles is None or cycles < max_cycles:
            snapshot = []
            for w in workers:
                snapshot.append({'worker': w.worker_id,
                                 'processed': w.run_once(d)})
            drain_expired_leases(d)
            report(d, snapshot)
            cycles += 1
            log({'kind': 'loop_cycle', 'cycle': cycles,
                 'snapshot': snapshot, 'sleep_before_next': sleep_seconds})
            if cycles % report_every == 0:
                log({'kind': 'loop_checkpoint', 'cycle': cycles,
                     'elapsed_hint': 'agent-local'})
    except Exception as ex:
        log({'kind': 'loop_stopped', 'reason': '%s: %s' % (type(ex).__name__, ex),
             'cycles_completed': cycles})
        raise
    log({'kind': 'loop_ended', 'cycles_completed': cycles,
         'report_every': report_every})
    return cycles


def run_pipelineloop_cli(argv=None):
    """CLI handler for mm_protocol run-pipeline (long-lived punctuator loop)."""
    import argparse
    p = argparse.ArgumentParser(prog='run-pipeline')
    p.add_argument('--workers', action='append', default=None)
    p.add_argument('--sleep', type=float, default=60)
    p.add_argument('--cycles', type=int, default=None)
    p.add_argument('--report-every', type=int, default=10)
    args = p.parse_known_args(argv)[0]
    from mm_workers import WORKERS
    names = set(args.workers) if args.workers else set(WORKERS)
    workers = [p.Worker('w-' + n, *WORKERS[n]) for n in sorted(names)]
    return run_pipelineloop(d, workers, sleep_seconds=args.sleep,
                            max_cycles=args.cycles, report_every=args.report_every)


def drain_expired_leases(d):
    at = dt.datetime.now(dt.timezone.utc)
    d.execute("UPDATE pipeline_items SET lease_owner=NULL,lease_until=NULL,"
              "updated_at=? WHERE lease_until IS NOT NULL "
              "AND lease_until<=?", (now(), at.isoformat()))


def report(d, snapshot):
    states = {r['state']: r['n'] for r in d.execute(
        "SELECT state,count(*) n FROM pipeline_items GROUP BY state")}
    workers = {r['worker_id']: dict(r) for r in d.execute(
        "SELECT * FROM worker_registry")}
    for w in workers.values():
        w['alive'] = (dt.datetime.now(dt.timezone.utc) - timestamp(w['heartbeat_at'])) < dt.timedelta(seconds=2 * w['lease_seconds'])
    log({'kind': 'loop_snapshot', 'states': states, 'workers': workers,
         'snapshot': snapshot})


def health_full(d):
    migrate(d)
    return health(d), report(d, [])


def driftfirst_apply(d):
    """Apply the current schema, repairing any older shape in place if needed.

    Safe to call at startup on any node; preserves append-only event history.
    """
    return migrate(d)


class RunPipeline:
    """Marker protocol so a long-running loop can be modeled as a command."""

    @staticmethod
    def run_pipelineloop(d, workers, sleep_seconds=60, max_cycles=None,
                         report_every=10):
        return run_pipelineloop(d, workers, sleep_seconds=sleep_seconds,
                                max_cycles=max_cycles, report_every=report_every)
