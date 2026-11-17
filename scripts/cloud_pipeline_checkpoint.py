"""Restore only trusted workflow checkpoints, with explicit recorded recovery."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

WORKFLOW = "cloud-prospect-pipeline.yml"
WORKFLOW_PATH = ".github/workflows/" + WORKFLOW
TRUSTED_EVENTS = ("schedule", "workflow_dispatch", "push")


def gh_json(args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True, timeout=60)
    return json.loads(result.stdout)


def eligible_run(run):
    return (
        run.get("head_branch") == "master"
        and run.get("event") in TRUSTED_EVENTS
        and run.get("path", "").split("@")[0] == WORKFLOW_PATH
    )


def restore(
    *, repo, current_id, state_path, bootstrap=False, recovery_id=None, query=gh_json, download=None
):
    from scripts.cloud_prospect_pipeline import private_state_path

    state_path = private_state_path(state_path)
    candidates = []
    for kind in TRUSTED_EVENTS:
        candidates.extend(
            query(
                [
                    "run",
                    "list",
                    "--workflow",
                    WORKFLOW,
                    "--branch",
                    "master",
                    "--event",
                    kind,
                    "--limit",
                    "100",
                    "--json",
                    "databaseId",
                ]
            )
        )
    ids = sorted(
        {int(x["databaseId"]) for x in candidates if int(x["databaseId"]) < current_id},
        reverse=True,
    )
    selected = None
    if recovery_id:
        if bootstrap or not 0 < recovery_id < current_id:
            raise ValueError("Recovery must select an older run, never bootstrap")
        selected = recovery_id
    else:
        for candidate in ids:
            jobs = query(["api", f"repos/{repo}/actions/runs/{candidate}/jobs"])["jobs"]
            worker = [x for x in jobs if x["name"] == "draft-pipeline"]
            if len(worker) != 1:
                raise ValueError("Ambiguous prior run; owner recovery required")
            if worker[0].get("conclusion") != "skipped":
                selected = candidate
                break
    if selected is None:
        if not bootstrap:
            raise ValueError("No checkpoint exists; first run requires explicit bootstrap")
        return {"source_run": None, "recovery": False, "bootstrap": True}
    if bootstrap:
        raise ValueError("Cannot bootstrap over prior worker history")
    info = query(["api", f"repos/{repo}/actions/runs/{selected}"])
    if not eligible_run(info):
        raise ValueError("Untrusted checkpoint workflow, branch or event")
    with tempfile.TemporaryDirectory(dir=state_path.parent, prefix="wa-restore-") as directory:
        if download:
            download(selected, Path(directory))
        else:
            subprocess.run(
                [
                    "gh",
                    "run",
                    "download",
                    str(selected),
                    "--name",
                    "pipeline-state",
                    "--dir",
                    directory,
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
        source = Path(directory) / "pipeline-state.enc"
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 10_000_000:
            raise ValueError("Missing or oversized checkpoint; no fallback permitted")
        with tempfile.NamedTemporaryFile(dir=state_path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        try:
            temporary.replace(state_path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"source_run": selected, "recovery": bool(recovery_id), "bootstrap": False}


def main():
    try:
        raw_recovery = os.environ.get("WA_RECOVERY_RUN", "").strip()
        recovery = int(raw_recovery) if raw_recovery else None
        result = restore(
            repo=os.environ["GITHUB_REPOSITORY"],
            current_id=int(os.environ["GITHUB_RUN_ID"]),
            state_path=Path(os.environ["RUNNER_TEMP"]) / "pipeline-state.enc",
            bootstrap=os.environ.get("BOOTSTRAP") == "true",
            recovery_id=recovery,
        )
        if not os.environ.get("WA_PIPELINE_STATE_KEY"):
            raise ValueError("State key required")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print(
            "Checkpoint restore blocked. Inspect prior artifacts; use explicit recovery if needed."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
