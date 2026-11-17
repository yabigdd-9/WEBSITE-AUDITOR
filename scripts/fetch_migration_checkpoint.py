"""Fetch the latest successful trusted worker checkpoint for one-time cutover."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from scripts.cloud_pipeline_checkpoint import WORKFLOW, WORKFLOW_PATH, gh_json
from scripts.cloud_prospect_pipeline import private_state_path


def fetch_latest(*, repo, source_run, current_run, destination, query=gh_json, download=None):
    if not 0 < source_run < current_run:
        raise ValueError("An older verified source is required")
    destination = private_state_path(destination)
    runs = query(["run", "list", "--workflow", WORKFLOW, "--branch", "master",
                  "--limit", "100", "--json", "databaseId"])
    ids = sorted({int(run["databaseId"]) for run in runs
                  if int(run["databaseId"]) < current_run}, reverse=True)
    selected = None
    for identity in ids:
        info = query(["api", f"repos/{repo}/actions/runs/{identity}"])
        if (info.get("head_branch") != "master" or info.get("event") not in {"push", "schedule", "workflow_dispatch"}
                or info.get("path", "").split("@")[0] != WORKFLOW_PATH):
            continue
        jobs = query(["api", f"repos/{repo}/actions/runs/{identity}/jobs"])["jobs"]
        workers = [job for job in jobs if job["name"] == "draft-pipeline"]
        if len(workers) != 1:
            raise ValueError("Ambiguous worker history")
        if workers[0].get("conclusion") == "skipped":
            continue
        if (info.get("status") != "completed" or info.get("conclusion") != "success"
                or workers[0].get("conclusion") != "success"):
            raise ValueError("Latest worker is not successful; no stale fallback is permitted")
        selected = identity
        break
    if selected != source_run:
        raise ValueError("Review the latest worker before migration")
    artifacts = query(["api", f"repos/{repo}/actions/runs/{selected}/artifacts"])["artifacts"]
    matches = [item for item in artifacts if item.get("name") == "pipeline-state" and not item.get("expired")]
    if len(matches) != 1 or not 0 < matches[0].get("size_in_bytes", 0) <= 10_000_000:
        raise ValueError("One intact bounded encrypted checkpoint is required")
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix="wa-pg-import-") as directory:
        if download is None:
            subprocess.run(["gh", "run", "download", str(selected), "--name", "pipeline-state",
                            "--dir", directory], check=True, capture_output=True, timeout=60)
        else:
            download(selected, Path(directory))
        source = Path(directory) / "pipeline-state.enc"
        if (source.is_symlink() or not source.is_file() or source.stat().st_size > 10_000_000
                or list(Path(directory).iterdir()) != [source]):
            raise ValueError("Unexpected checkpoint contents")
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
    return {"source_run": selected, "artifact_id": matches[0]["id"]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        result = fetch_latest(
            repo=os.environ["GITHUB_REPOSITORY"], source_run=args.source_run,
            current_run=int(os.environ["GITHUB_RUN_ID"]),
            destination=Path(os.environ["RUNNER_TEMP"]) / "pipeline-state.enc",
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print("Migration source blocked; inspect worker/artifact history privately.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
