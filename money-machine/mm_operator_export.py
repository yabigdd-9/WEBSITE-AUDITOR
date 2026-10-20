"""One local presentation export; called by the supervisor, never a daemon.

Database access is read-only. No search/provider/model requests, migrations,
queue transitions, approvals, sends or pricing decisions are performed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def publish_once() -> dict:
    import mm_core as core
    import mm_observability
    import mm_obsidian
    from supervisor.logrotate import directory_lock, maintain_logs

    from auditor_toolkit.common import atomic_write_json

    state = core.root() / "state"
    result = {"generated_at": core.now(), "authoritative": False,
              "stages": {}, "database_mutations": 0, "external_sends": 0,
              "provider_requests": 0, "paid_cost_usd": 0}
    with directory_lock(state, ".operator-export.lock"):
        # Rotate only named telemetry at the state root. Soak/controller
        # journals and unrelated runtime/history files are never selected.
        stages = [
            ("telemetry_retention", lambda: maintain_logs(state, names={"metrics.jsonl", "errors.jsonl"})),
            ("worker_log_retention", lambda: maintain_logs(state / "worker-logs")),
            ("snapshots", lambda: mm_observability.write_snapshots(probe_discovery=False)),
            ("obsidian", mm_obsidian.sync),
        ]
        for name, operation in stages:
            try:
                detail = operation()
                result["stages"][name] = {"status": "COMPLETE", "result": detail}
            except Exception as error:
                # Stage isolation allows fresh snapshots even if retention or
                # the vault is unavailable. Exception values are not copied.
                result["stages"][name] = {"status": "FAILED", "error_type": type(error).__name__}
        result["complete"] = all(s["status"] == "COMPLETE" for s in result["stages"].values())
        atomic_write_json(state / "operator-export-status.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--parent-pid", type=int, help="Supervisor ownership; bounded child exits if parent is lost")
    args = parser.parse_args(argv)
    if args.parent_pid is not None:
        if args.parent_pid <= 1 or args.parent_pid != os.getppid():
            parser.error("Expected live parent must match the invoking supervisor")
        deadline = time.monotonic() + 20

        def guard():
            while True:
                if os.getppid() != args.parent_pid or time.monotonic() >= deadline:
                    os._exit(3)
                time.sleep(0.25)

        threading.Thread(target=guard, daemon=True).start()
    try:
        result = publish_once()
    except Exception as error:
        result = {"complete": False, "error_type": type(error).__name__,
                  "authoritative": False, "external_sends": 0, "provider_requests": 0}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
