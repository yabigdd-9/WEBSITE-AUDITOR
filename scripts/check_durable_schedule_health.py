"""Verify that GitHub actually ran the scheduled durable worker and saved state.

Read-only metadata probe: never reads ciphertext, decrypts it, runs audits, or
dispatches a worker. A skipped GitHub cron must not look like a healthy queue.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, time, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WORKFLOW = "cloud-prospect-pipeline.yml"
CRON_WEEKDAYS = frozenset({1, 4})  # Tuesday and Friday, UTC (Python weekday)
CRON_TIME_UTC = time(4, 50)
GRACE = timedelta(hours=6)
REPO_PATTERN = re.compile(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+\Z")


def latest_expected_slot(now: datetime) -> datetime:
    """Most recent schedule slot at least six hours in the past."""
    if now.tzinfo is None:
        raise ValueError("UTC-aware clock required")
    now = now.astimezone(timezone.utc)
    eligible = []
    for days_ago in range(8):
        date = (now - timedelta(days=days_ago)).date()
        if date.weekday() not in CRON_WEEKDAYS:
            continue
        candidate = datetime.combine(date, CRON_TIME_UTC, tzinfo=timezone.utc)
        if candidate + GRACE <= now:
            eligible.append(candidate)
    if not eligible:
        raise ValueError("No prior scheduled slot found")
    return max(eligible)


def utc_timestamp(value: str | None) -> datetime:
    if not isinstance(value, str):
        raise ValueError("GitHub metadata timestamp missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("GitHub metadata timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def created_utc(run: dict) -> datetime:
    return utc_timestamp(run.get("created_at"))


def verify_health(now: datetime, fetch_json, repo: str) -> dict:
    """Check worker success and checkpoint retention through the next slot."""
    if not REPO_PATTERN.fullmatch(repo):
        raise ValueError("Invalid repository identifier")
    due = latest_expected_slot(now)
    root = f"repos/{repo}"
    data = fetch_json(
        f"{root}/actions/workflows/{WORKFLOW}/runs?"
        + urlencode({"event": "schedule", "branch": "master", "per_page": 100})
    )
    runs = [
        run for run in data.get("workflow_runs", [])
        if run.get("event") == "schedule"
        and run.get("head_branch") == "master"
        and due <= created_utc(run) <= now.astimezone(timezone.utc)
    ]
    if not runs:
        raise RuntimeError(f"No scheduled worker run after {due.isoformat()}")
    newest = max(runs, key=lambda run: (created_utc(run), int(run.get("id", 0))))
    if newest.get("status") != "completed" or newest.get("conclusion") != "success":
        raise RuntimeError("Latest scheduled workflow did not complete successfully")
    run_id = int(newest["id"])
    jobs = fetch_json(f"{root}/actions/runs/{run_id}/jobs?per_page=100").get("jobs", [])
    worker = [job for job in jobs if job.get("name") == "draft-pipeline"]
    if len(worker) != 1 or worker[0].get("conclusion") != "success":
        raise RuntimeError("Scheduled draft-pipeline job was missing, skipped or unsuccessful")
    artifacts = fetch_json(f"{root}/actions/runs/{run_id}/artifacts?per_page=100").get(
        "artifacts", []
    )
    checkpoint = [
        item for item in artifacts
        if item.get("name") == "pipeline-state"
        and item.get("expired") is False
        and type(item.get("size_in_bytes")) is int
        and item["size_in_bytes"] > 0
    ]
    if len(checkpoint) != 1:
        raise RuntimeError("Scheduled worker did not retain one nonempty encrypted checkpoint")
    next_slot = min(
        due + timedelta(days=offset)
        for offset in range(1, 8)
        if (due.weekday() + offset) % 7 in CRON_WEEKDAYS
    )
    required_until = next_slot + GRACE
    expires = utc_timestamp(checkpoint[0].get("expires_at"))
    if expires <= required_until:
        raise RuntimeError("Encrypted checkpoint expires before the next schedule grace window closes")
    return {
        "due_utc": due.isoformat(),
        "run_id": run_id,
        "run_url": f"https://github.com/{repo}/actions/runs/{run_id}",
        "run_created_utc": created_utc(newest).isoformat(),
        "schedule_delay_seconds": int((created_utc(newest) - due).total_seconds()),
        "next_slot_utc": next_slot.isoformat(),
        "checkpoint_present": True,
        "checkpoint_expires_utc": expires.isoformat(),
        "retention_required_until_utc": required_until.isoformat(),
    }


def github_json(path: str) -> dict:
    token = os.environ["GH_TOKEN"]
    request = Request(
        "https://api.github.com/" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def main() -> int:
    try:
        result = verify_health(
            datetime.now(timezone.utc),
            github_json,
            os.environ["GITHUB_REPOSITORY"],
        )
        print("Scheduled durable worker healthy: " + json.dumps(result, sort_keys=True))
        return 0
    except (KeyError, ValueError, RuntimeError, HTTPError, URLError, TimeoutError):
        # Don't print HTTP response bodies, tokens, artifacts or internal customer data.
        print("::error::Scheduled durable worker health unverified: inspect Actions runs, "
              "worker job, and encrypted checkpoint retention.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
