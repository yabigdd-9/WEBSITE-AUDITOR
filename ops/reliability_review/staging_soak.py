"""Bounded concurrent queue acceptance on synthetic data only."""
import datetime as dt
import hashlib
import json
import multiprocessing as mp
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'money-machine'))
import mm_pipeline as p  # noqa: E402
import mm_queue_health  # noqa: E402


def connection(path):
    d = sqlite3.connect(path, timeout=10)
    d.row_factory = sqlite3.Row
    d.execute('PRAGMA busy_timeout=10000')
    return d


def process(path, worker_id):
    d = connection(path)
    def handler(db, row, worker):
        db.execute('INSERT INTO executions VALUES(?,?)', (row['business_id'], worker.worker_id))
        return 'DEMO_READY', 'synthetic concept prepared', {'synthetic': True}
    worker = p.Worker(worker_id, ('DEMO_PENDING',), handler)
    for _ in range(40):
        worker.run_once(d, limit=5)
        d.commit()
        if d.execute("SELECT count(*) FROM pipeline_items WHERE state='DEMO_PENDING'").fetchone()[0] == 0:
            break
        time.sleep(.01)
    d.close()


def abandon(path):
    d = connection(path)
    p.claim(d, ('DEMO_PENDING',), 'crashed', lease_seconds=1, limit=5)
    d.commit()
    # Only this disposable child exits
    # The live supervisor is never signalled.
    os._exit(17)


def main():
    state = Path(os.environ['MM_ROOT'])
    state.mkdir(parents=True, exist_ok=True)
    path = state / 'synthetic-queue.db'
    if path.exists():
        raise RuntimeError('Use a fresh staging directory')
    start = time.monotonic()
    source = ROOT / 'money-machine/mm_pipeline.py'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    d = connection(path)
    d.execute('PRAGMA journal_mode=WAL')
    d.executescript('CREATE TABLE businesses(id INTEGER PRIMARY KEY);'
                    'CREATE TABLE executions(business_id INTEGER PRIMARY KEY, worker TEXT);')
    p.migrate(d)
    for bid in range(1, 101):
        d.execute('INSERT INTO businesses VALUES(?)', (bid,))
        p.enqueue(d, bid, state='DEMO_PENDING')
    p.register_worker(d, 'staging-a', 'DEMO_PENDING')
    d.commit()
    before = mm_queue_health.snapshot(d)
    ctx = mp.get_context('spawn')
    crash = ctx.Process(target=abandon, args=(str(path),))
    crash.start()
    crash.join(15)
    if crash.is_alive():
        crash.terminate()
        crash.join(5)
        raise RuntimeError('Staging crash probe timed out')
    abandoned = d.execute("SELECT count(*) FROM pipeline_items WHERE lease_owner='crashed'").fetchone()[0]
    time.sleep(1.2)
    p.drain_expired_leases(d)
    d.commit()
    children = [ctx.Process(target=process, args=(str(path), name)) for name in ('staging-a', 'staging-b')]
    for child in children:
        child.start()
    for child in children:
        child.join(45)
        if child.is_alive():
            child.terminate()
            child.join(5)
            raise RuntimeError('Staging worker exceeded bound')
    # Restart an empty worker: it cannot execute successful jobs a second time.
    process(str(path), 'restarted')
    after = mm_queue_health.snapshot(d)
    completed = d.execute('SELECT count(*) FROM executions').fetchone()[0]
    dupes = d.execute('SELECT count(*)-count(distinct business_id) FROM executions').fetchone()[0]
    # Additional fault-injection jobs prove bounded retries and dead-lettering.
    for bid in (101, 102):
        d.execute('INSERT INTO businesses VALUES(?)', (bid,))
        p.enqueue(d, bid, state='DISCOVERED', max_attempts=2)
    def failure(db, row, worker):
        raise p.RetryableError('synthetic transient')
    retry = p.Worker('retry-probe', ('DISCOVERED',), failure)
    retry.run_once(d, limit=2)
    scheduled = d.execute('SELECT count(*) FROM pipeline_items WHERE next_retry_at IS NOT NULL').fetchone()[0]
    d.execute('UPDATE pipeline_items SET next_retry_at=NULL WHERE business_id>100')
    retry.run_once(d, limit=2)
    exhausted = d.execute("SELECT count(*) FROM pipeline_items WHERE state='RETRYABLE_FAILURE'").fetchone()[0]
    d.commit()
    quick = d.execute('PRAGMA quick_check').fetchone()[0]
    receipt = {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'synthetic_jobs': 100,
               'completed': completed, 'success_rate': completed/100,
               'duplicate_successful_executions': dupes, 'abandoned_leases': abandoned,
               'crash_probe_exit_code': crash.exitcode,
               'worker_exit_codes': [child.exitcode for child in children],
               'stranded_eligible': after['eligible'], 'retry_scheduled': scheduled,
               'retry_budget_exhausted': exhausted, 'quick_check': quick,
               'before': before, 'after': after, 'paid_api_calls': 0, 'messages_sent': 0,
               'elapsed_seconds': round(time.monotonic()-start, 3),
               'source_sha256': digest,
               'changed_during_run': digest != hashlib.sha256(source.read_bytes()).hexdigest(),
               'scope': 'bounded synthetic queue acceptance; not production soak'}
    receipt['soak_passed'] = (completed == 100 and dupes == 0 and after['eligible'] == 0
                              and abandoned == 5 and scheduled == exhausted == 2
                              and quick == 'ok' and all(child.exitcode == 0 for child in children)
                              and not receipt['changed_during_run'])
    out = ROOT / 'reports/reliability-review/evidence/staging-soak.json'
    out.write_text(json.dumps(receipt, indent=2) + '\n')
    d.close()
    print(json.dumps(receipt))
    return 0 if receipt['soak_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
