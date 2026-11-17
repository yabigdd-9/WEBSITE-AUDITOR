"""Create one deduplicated GitHub issue for a failed trusted cloud workflow.

This reads GitHub workflow-run metadata only. It never reads encrypted
checkpoints, configures a database, sends client messages, or spends money.
The workflow_run trigger executes this script from the default branch.
"""

from __future__ import annotations

import json
import os
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WORKFLOWS = frozenset({"Durable Cloud Draft Pipeline", "Durable Worker Schedule Health"})
FAILED = frozenset({"failure", "timed_out", "cancelled", "action_required", "startup_failure"})
ISSUE_TITLE = "[ops] Durable cloud worker or schedule monitor failed"
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


def trusted_failure(event: dict, repo: str) -> dict | None:
    """Ignore successful, forked, PR, or unrelated runs; fail closed on bad IDs."""
    if not REPO_PATTERN.fullmatch(repo):
        raise ValueError("Invalid repository")
    run = event.get("workflow_run", {})
    if (
        event.get("repository", {}).get("full_name") != repo
        or run.get("name") not in WORKFLOWS
        or run.get("conclusion") not in FAILED
        or run.get("head_branch") != "master"
        or run.get("head_repository", {}).get("full_name") != repo
        or run.get("event") not in {"push", "schedule", "workflow_dispatch"}
    ):
        return None
    run_id = run.get("id")
    if type(run_id) is not int or run_id < 1:
        raise ValueError("Invalid workflow run ID")
    return {
        "workflow": run["name"],
        "conclusion": run["conclusion"],
        "run_id": run_id,
        "run_url": f"https://github.com/{repo}/actions/runs/{run_id}",
    }


def alert(event: dict, repo: str, get_json, post_json) -> dict:
    """Find an open issue before creating one; never spam duplicate incidents."""
    failure = trusted_failure(event, repo)
    if failure is None:
        return {"result": "ignored"}
    root = f"repos/{repo}/issues"
    for page in range(1, 21):
        issues = get_json(root + "?" + urlencode({
            "state": "open", "per_page": 100, "page": page,
        }))
        if not isinstance(issues, list):
            raise ValueError("Unexpected issue list")
        for issue in issues:
            if issue.get("title") == ISSUE_TITLE and "pull_request" not in issue:
                return {"result": "existing", "issue": issue["number"]}
        if len(issues) < 100:
            break
    else:
        raise RuntimeError("Cannot safely deduplicate issue after 20 pages")
    body = (
        "A trusted master-branch cloud workflow did not finish successfully. "
        "This alert contains GitHub run metadata only; no private audit or "
        "checkpoint contents were read.\n\n"
        f"- Workflow: {failure['workflow']}\n"
        f"- Conclusion: {failure['conclusion']}\n"
        f"- Run: {failure['run_url']}\n\n"
        "Investigate the failed job, the latest trusted encrypted checkpoint, "
        "and the scheduled-worker health monitor. Do not silently bootstrap, "
        "discard state, enable client outreach, or enable paid calls. "
        "Close this issue after the incident and recovery are verified."
    )
    created = post_json(root, {"title": ISSUE_TITLE, "body": body})
    number = created.get("number")
    if type(number) is not int or number < 1:
        raise ValueError("GitHub did not confirm issue creation")
    return {"result": "created", "issue": number, "run_id": failure["run_id"]}


def github_json(path: str, payload: dict | None = None):
    token = os.environ["GH_TOKEN"]
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        "https://api.github.com/" + path,
        data=data,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
        method="POST" if data is not None else "GET",
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def main() -> int:
    try:
        if os.environ["GITHUB_EVENT_NAME"] != "workflow_run":
            raise ValueError("Only trusted workflow_run events may create alerts")
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as stream:
            event = json.load(stream)
        result = alert(
            event, os.environ["GITHUB_REPOSITORY"],
            lambda path: github_json(path),
            lambda path, payload: github_json(path, payload),
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        # Never print API errors or authorization headers into public logs.
        print("::error::Unable to verify or create cloud-worker failure issue.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
