#!/usr/bin/env python3
"""
Resume + checkpoint controller for the Hermes Money Engine.

  python3 run.py status                 → read state, show what to do next (mutates nothing)
  python3 run.py checkpoint "<task>"    → append a completed task, bump timestamp
  python3 run.py fail "<task>" "<why>"  → log failure + queue retry (never restarts project)
  python3 run.py report                 → regenerate today's operator report
  python3 run.py rebuild                → re-run extract+score+deliverables (only if sources changed)
  python3 run.py concurrency up|down    → step concurrency per rate-limit policy

Design rule: `status` and `report` are READ-ONLY on state except report regeneration.
Nothing here sends, publishes, purchases or commits anything.
"""
import sys, yaml, json, datetime, subprocess, hashlib, signal
from pathlib import Path

# allow `run.py status | head` without a BrokenPipeError traceback
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state/HERMES_EXECUTION_STATE.yaml"
NOW = lambda: datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def load():
    return yaml.safe_load(open(STATE))


def save(s):
    s["updated_at"] = NOW()
    yaml.safe_dump(s, open(STATE, "w"), sort_keys=False, width=100, allow_unicode=True)


def status():
    s = load()
    db = json.load(open(ROOT / "db/master_opportunity_database.json"))
    print(f"phase            : {s['current_phase']}")
    print(f"updated          : {s['updated_at']}")
    print(f"engines in db    : {len(db)}")
    print(f"active engine    : {s['active_engine']}")
    print(f"concurrency      : {s['concurrency']['current_max_concurrent_children']} "
          f"({s['concurrency']['mode']})")
    print(f"completed tasks  : {len(s['completed_tasks'])}")
    print(f"failed tasks     : {len(s['failed_tasks'])}   retry queue: {len(s['retry_queue'])}")
    print(f"revenue          : NZ${s['revenue']['total_nzd']}")
    print("\nactive tasks:")
    for t in s["active_tasks"]:
        print(f"  [{t['status']:11s}] {t['id']} {t['agent']:10s} {t['task'][:70]}")
    todo = [t for t in s["active_tasks"] if t["status"] in ("QUEUED", "IN_PROGRESS")]
    print(f"\nNEXT ACTION      : {s['next_action']}")
    print(f"unfinished tasks : {len(todo)}  (resume these, do NOT redo completed work)")
    # readiness, not mutation
    missing = [p for p in ("outputs/RESEARCH_website_rescue_methodology.md",
                           "outputs/RESEARCH_reputation_engine_methodology.md")
               if not (ROOT / p).exists()]
    print(f"needs_reload     : {bool(missing)}")
    if missing:
        print("  reasons: awaiting " + ", ".join(missing))


def checkpoint(task):
    s = load()
    cid = f"C-{len(s['completed_tasks'])+1:03d}"
    s["completed_tasks"].append({"id": cid, "task": task, "at": NOW()})
    for t in s["active_tasks"]:
        if t["task"][:40] in task or task[:40] in t["task"]:
            t["status"] = "COMPLETE"
    save(s)
    print(f"checkpointed {cid}: {task}")


def fail(task, why):
    s = load()
    fid = f"F-{len(s['failed_tasks'])+1:03d}"
    s["failed_tasks"].append({"id": fid, "task": task, "reason": why, "at": NOW()})
    s["retry_queue"].append({"id": fid, "task": task, "strategy": "reroute_to_fallback_model",
                             "queued_at": NOW()})
    save(s)
    print(f"logged failure {fid} and queued retry — project NOT restarted")


def concurrency(direction):
    s = load()
    c = s["concurrency"]
    cur = c["current_max_concurrent_children"]
    if direction == "up":
        new = min(4, cur + 1)
        c["mode"] = {2: "initial_conservative", 3: "stable", 4: "experimental_max"}[new]
    else:
        new = max(1, cur - 1)
        c["mode"] = "throttled_after_429"
    c["current_max_concurrent_children"] = new
    save(s)
    print(f"concurrency {cur} -> {new} ({c['mode']})")


def run(script):
    r = subprocess.run([sys.executable, str(ROOT / script)], capture_output=True, text=True)
    print(r.stdout or "", end="")
    if r.returncode != 0:
        print(r.stderr[-1500:]); sys.exit(r.returncode)


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "status": status()
    elif cmd == "checkpoint": checkpoint(sys.argv[2])
    elif cmd == "fail": fail(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "unspecified")
    elif cmd == "report": run("extract/daily_report.py")
    elif cmd == "concurrency": concurrency(sys.argv[2])
    elif cmd == "rebuild":
        for s_ in ("extract/extract_engines.py", "extract/dedupe_score.py",
                   "extract/build_deliverables.py", "extract/build_cartridges.py",
                   "extract/daily_report.py"):
            print(f"--- {s_}"); run(s_)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
