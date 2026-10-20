"""Bounded read-only queue sampling; never restarts workers or probes networks."""
import argparse
import datetime as dt
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'money-machine'))
from mm_queue_health import snapshot  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=6)
    parser.add_argument('--interval', type=float, default=5)
    args = parser.parse_args()
    if not 2 <= args.samples <= 60 or not 1 <= args.interval <= 30:
        parser.error('Use 2-60 samples and a 1-30 second interval')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'reports/reliability-review'):
        parser.error('Output must remain within candidate review reports')
    samples = []
    start = time.monotonic()
    for i in range(args.samples):
        with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as d:
            d.row_factory = sqlite3.Row
            row = snapshot(d)
            row['quick_check'] = d.execute('PRAGMA quick_check').fetchone()[0]
            row['foreign_key_violations'] = len(d.execute('PRAGMA foreign_key_check').fetchall())
        row['disk_free_bytes'] = shutil.disk_usage(args.database.parent).free
        row['sample_monotonic_seconds'] = round(time.monotonic()-start, 3)
        samples.append(row)
        if i < args.samples-1:
            time.sleep(args.interval)
    elapsed = samples[-1]['sample_monotonic_seconds'] - samples[0]['sample_monotonic_seconds']
    first, last = samples[0]['metrics'], samples[-1]['metrics']
    delta = {name: last.get(name, 0)-first.get(name, 0) for name in set(first) | set(last)}
    done = delta.get('pipeline.items.completed', 0)
    retries = delta.get('pipeline.items.retry_scheduled', 0)
    dead = delta.get('pipeline.items.dead_lettered', 0)
    receipt = {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'mode': 'read_only_no_recovery',
               'samples': samples, 'elapsed_seconds': elapsed, 'counter_deltas': delta,
               'jobs_processed_per_hour': done*3600/elapsed if elapsed else None,
               'completion_rate': done/(done+retries+dead) if done+retries+dead else None,
               'retry_rate': retries/(done+retries+dead) if done+retries+dead else None,
               'failure_rate': dead/(done+retries+dead) if done+retries+dead else None,
               'recovery_attempts_by_observer': 0,
               'note': 'Idle rates are null when no outcomes occur; zero work is not a worker failure.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'samples'}))


if __name__ == '__main__':
    main()
