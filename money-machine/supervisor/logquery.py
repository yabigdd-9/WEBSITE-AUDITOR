"""Structured log query CLI for the supervisor."""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

from mm_pipeline import root

def query_logs(
    kind=None,
    worker=None,
    since=None,
    level=None,
    limit=100,
):
    """Query structured logs with filters."""
    log_dir = root() / 'state' / 'worker-logs'
    if not log_dir.exists():
        return []

    since_dt = None
    if since:
        match = re.match(r'(\d+)([hdwm])', since.lower())
        if match:
            val, unit = int(match.group(1)), match.group(2)
            delta = {'h': timedelta(hours=val), 'd': timedelta(days=val),
                       'w': timedelta(weeks=val), 'm': timedelta(days=30*val)}[unit]
            since_dt = datetime.now() - timedelta(days=0)  # placeholder

    results = []
    log_dir = root() / 'state' / 'worker-logs'
    for log_file in sorted(root().glob('state/worker-logs/*.jsonl')):
        try:
            with open(log_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if kind and record.get('kind') != kind:
                        continue
                    if worker and record.get('worker_id') != worker:
                        continue
                    if level and record.get('level') != level:
                        continue

                    at = record.get('at')
                    if since_dt and at:
                        try:
                            dt = datetime.fromisoformat(at.replace('Z', '+00:00'))
                            if dt < since_dt:
                                continue
                        except ValueError:
                            pass

                    results.append(record)
                    if len(results) >= limit:
                        return results
        except (OSError, json.JSONDecodeError):
            continue

    results.sort(key=lambda r: r.get('at', ''), reverse=True)
    return results[:limit]

def query_logs_cli(argv):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--kind')
    p.add_argument('--worker')
    p.add_argument('--since')
    p.add_argument('--level')
    p.add_argument('--limit', type=int, default=100)
    p.add_argument('--json', action='store_true')
    args = p.parse_args(argv)

    results = query_logs(
        kind=args.kind,
        worker=args.worker,
        since=args.since,
        level=args.level,
        limit=args.limit,
    )
    return {'logs': results, 'count': len(results)}
