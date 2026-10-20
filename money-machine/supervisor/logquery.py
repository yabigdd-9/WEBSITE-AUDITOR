"""Structured supervisor log queries, with UTC windows and newest-first results."""

import argparse
import heapq
import json
import re
from datetime import datetime, timedelta, timezone

from mm_pipeline import root


def _since_delta(value):
    match = re.fullmatch(r"([0-9]+)([hdwm])", value.lower()) if isinstance(value, str) else None
    if match is None:
        raise ValueError("since must be a whole number followed by h, d, w or m")
    try:
        count = int(match.group(1))
        return timedelta(seconds=count * {"h": 3600, "d": 86400,
                                          "w": 604800, "m": 2592000}[match.group(2)])
    except (OverflowError, ValueError) as exc:
        raise ValueError("since duration is out of range") from exc


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Legacy timestamps without an offset are interpreted as UTC.
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def query_logs(kind=None, worker=None, since=None, level=None, limit=100):
    """Read all files, retaining at most ``limit`` matching rows, newest first.

    Unknown timestamps sort last without a filter and never establish freshness.
    A month means 30 days.
    """
    if type(limit) is not int or limit < 0:
        raise ValueError("limit must be a nonnegative integer")

    since_dt = None
    if since is not None:
        try:
            since_dt = datetime.now(timezone.utc) - _since_delta(since)
        except OverflowError as exc:
            raise ValueError("since duration is out of range") from exc
    if limit == 0:
        return []
    log_dir = root() / "state" / "worker-logs"
    unknown_time = datetime.min.replace(tzinfo=timezone.utc)
    results = []
    sequence = 0
    for log_file in sorted(log_dir.glob("*.jsonl")):
        try:
            with log_file.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(record, dict):
                        continue
                    if kind and record.get('kind') != kind:
                        continue
                    if worker and record.get('worker_id') != worker:
                        continue
                    if level and record.get('level') != level:
                        continue

                    stamp = _timestamp(record.get("at"))
                    if since_dt is not None and (stamp is None or stamp < since_dt):
                        continue
                    sequence += 1
                    entry = (stamp or unknown_time, sequence, record)
                    if len(results) < limit:
                        heapq.heappush(results, entry)
                    elif entry[:2] > results[0][:2]:
                        heapq.heapreplace(results, entry)
        except OSError:
            continue
    return [entry[2] for entry in sorted(results, reverse=True)]

def query_logs_cli(argv):
    p = argparse.ArgumentParser()
    p.add_argument('--kind')
    p.add_argument('--worker')
    p.add_argument('--since')
    p.add_argument('--level')
    p.add_argument('--limit', type=int, default=100)
    p.add_argument('--json', action='store_true')
    args = p.parse_args(argv)

    try:
        results = query_logs(kind=args.kind, worker=args.worker, since=args.since,
                             level=args.level, limit=args.limit)
    except ValueError as exc:
        p.error(str(exc))
    return {'logs': results, 'count': len(results)}
