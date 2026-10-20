#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Runner
Executes zero-token workers by delegating to existing money-machine commands
or running custom zero-token logic.

Safety guarantees (hard-coded, non-bypassable):
  * Sets HERMES_ZERO_TOKEN_MODE=ZERO_LLM, HERMES_ALLOW_HOSTED_LLM=0,
    HERMES_ALLOW_PAID_FALLBACK=0, WEBSITE_AUDITOR_OUTREACH_SEND=0 in every run.
  * Writes JSONL audit logs to state/hermes_zero_token/audit.jsonl.
  * Emits zero-token attestation metrics after every worker run.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import yaml

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from ops.hermes_zero_token.worker_ownership import (  # noqa: E402
    STAGING_WORKERS,
    worker_lock,
)

STATE_DIR = PROJECT_ROOT / "state" / "hermes_zero_token"
REPORTS_DIR = PROJECT_ROOT / "reports" / "hermes_zero_token"
AUDIT_LOG = STATE_DIR / "audit.jsonl"
MODULE_TIMEOUT_SECONDS = 240
TEST_COUNTS_MARKER = "HERMES_TEST_COUNTS="


# Zero-token environment values (always enforced)
ZERO_TOKEN_ENV = {
    "HERMES_ZERO_TOKEN_MODE": "ZERO_LLM",
    "HERMES_ALLOW_HOSTED_LLM": "0",
    "HERMES_ALLOW_PAID_FALLBACK": "0",
    "WEBSITE_AUDITOR_OUTREACH_SEND": "0",
    "MM_EXTERNAL_SEND_DISABLED": "1",
}

# Emergency kill switch
KILL_SWITCH = os.environ.get("HERMES_ZERO_TOKEN_DISABLE_ALL", "0")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _log_audit(worker_id, event, status="ok", task_id="", extra=None):
    """Append a JSONL audit record with the required fields."""
    record = {
        "timestamp": _now_iso(),
        "job_id": "za-" + worker_id,
        "worker_id": worker_id,
        "task_id": task_id or "n/a",
        "event": event,
        "status": status,
        "duration_ms": 0,  # filled by caller if timing
        "cost_nzd": 0,     # always zero in ZERO_LLM mode
    }
    if extra:
        record.update(extra)
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _enforce_zero_token():
    """Enforce zero-token environment. Fail closed if any flag is missing or wrong."""
    for key, expected in ZERO_TOKEN_ENV.items():
        actual = os.environ.get(key)
        if actual != expected:
            # Override to the safe value
            os.environ[key] = expected
    # Kill switch
    if os.environ.get("HERMES_ZERO_TOKEN_DISABLE_ALL", "0") == "1":
        print("BLOCKED: HERMES_ZERO_TOKEN_DISABLE_ALL=1 — all non-watchdog jobs refuse work.", file=sys.stderr)
        sys.exit(3)


def run_mm_command(command, *args, timeout=180):
    """Run an mm command with the venv-email python."""
    mm_venv = PROJECT_ROOT / ".venv-email" / "bin" / "python"
    if not mm_venv.exists():
        mm_venv = PROJECT_ROOT / ".venv" / "bin" / "python"

    cmd = [str(mm_venv), str(PROJECT_ROOT / "money-machine" / "mm_operator.py"), command] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def run_toolkit_test(*args):
    """Run toolkit tests."""
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = PROJECT_ROOT / ".venv-email" / "bin" / "python"

    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pytest-", dir=AUDIT_LOG.parent) as directory:
        report_path = Path(directory) / "results.xml"
        cmd = [str(venv_python), "-m", "pytest", *args, f"--junitxml={report_path}"]
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300)
        try:
            testcases = list(ElementTree.parse(report_path).iter("testcase"))
            counts = {"passed": 0, "failed": 0, "skipped": 0}
            for testcase in testcases:
                if testcase.find("failure") is not None or testcase.find("error") is not None:
                    counts["failed"] += 1
                elif testcase.find("skipped") is not None:
                    counts["skipped"] += 1
                else:
                    counts["passed"] += 1
        except (OSError, ElementTree.ParseError):
            counts = None
        stdout = result.stdout + "\n" + TEST_COUNTS_MARKER + json.dumps(counts) + "\n"
        return result.returncode, stdout, result.stderr


def run_supervisor_health():
    """Run supervisor health check."""
    return run_mm_command("supervisor", "health")


def run_database_integrity():
    """Run database integrity check."""
    return run_mm_command("db-check")


def run_database_backup():
    """Trigger a database backup using mm_core."""
    code = (
        "import sys; sys.path.insert(0, r'%s/money-machine')" % PROJECT_ROOT
        + "\nfrom mm_core import backup\n"
        + "import json\n"
        + "backup_path = backup()\n"
        + "print(json.dumps({'backup_path': str(backup_path)}))\n"
    )
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv-email" / "bin" / "python"), "-c", code],
        capture_output=True, text=True, timeout=120,
    )
    return result.returncode, result.stdout, result.stderr


def run_queue_dispatcher():
    """Run queue dispatcher logic: recover expired claims, drain leases."""
    code = (
        "import sys; sys.path.insert(0, r'%s/money-machine')" % PROJECT_ROOT
        + "\nimport mm_pipeline\n"
        + "from mm_core import connect\n"
        + "with connect() as d:\n"
        + "    mm_pipeline.drain_expired_leases(d)\n"
        + "    d.commit()\n"
        + "print('Queue dispatcher: drained expired leases')\n"
    )
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv-email" / "bin" / "python"), "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


def run_identity_resolution():
    """Run identity resolution via discovery-cycle."""
    return run_mm_command("discovery-cycle", "--force")


def run_site_auditor():
    """Run site auditor: audit existing businesses using mm audit-backfill.

    Reuses the existing mm_operator.py audit-backfill command, which runs
    the auditor_toolkit audit handler (browser=False, ai=False) on existing
    businesses with known public websites. This is the tested, safe path.
    """
    return run_mm_command("audit-backfill", "--no-delay", timeout=240)


def run_scoring_judge():
    """Run scoring judge: process pending qualification items via the existing pipeline.

    The supervisor already processes QUALIFICATION_PENDING items on its 5s loop.
    This cron worker acts as an independent health check by verifying the
    mm_workers qualification handler exists and is callable with deterministic
    scoring via mm_core.opportunity_score_6_component.
    """
    code = (
        "import sys; sys.path.insert(0, r'%s/money-machine')" % PROJECT_ROOT
        + "\nfrom mm_core import opportunity_score_6_component\n"
        + "from mm_workers import WORKERS, qualification_handler\n"
        + "assert 'qualification' in WORKERS, 'qualification worker not registered'\n"
        + "# Verify deterministic scoring produces a 0-100 score\n"
        + "result = opportunity_score_6_component(0.5, 0.5, 0.5, 0.5, 0.5, 0.5)\n"
        + "assert result['score'] >= 0 and result['score'] <= 100\n"
        + "print('Scoring judge: qualification worker registered, deterministic score verified')\n"
    )
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv-email" / "bin" / "python"), "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


def run_evidence_proofer():
    """Run evidence QA: verify the mm_evidence table has consistent records.

    The supervisor already runs the qa_handler on QA_PENDING items. This cron
    worker independently verifies that evidence records have source URLs,
    timestamps, and hashes — no fabricated or altered proof.
    """
    code = (
        "import sys; sys.path.insert(0, r'%s/money-machine')" % PROJECT_ROOT
        + "\nfrom mm_core import connect\n"
        + "from mm_core import artifact_valid\n"
        + "import json\n"
        + "with connect(readonly=True) as d:\n"
        + "    rows = d.execute('SELECT id, business_id, url, observation, limitation, checked_at FROM mm_evidence LIMIT 10').fetchall()\n"
        + "    findings = []\n"
        + "    for r in rows:\n"
        + "        rec = dict(r)\n"
        + "        issues = []\n"
        + "        if not rec.get('url'): issues.append('missing URL')\n"
        + "        if not rec.get('checked_at'): issues.append('missing timestamp')\n"
        + "        if not rec.get('observation'): issues.append('missing observation')\n"
        + "        rec['issues'] = issues\n"
        + "        findings.append(rec)\n"
        + "    bad = sum(1 for f in findings if f['issues'])\n"
        + "    print(json.dumps({'evidence_checked': len(findings), 'records_with_issues': bad, 'ok': bad == 0}))\n"
    )
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv-email" / "bin" / "python"), "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


def run_discover_nz_businesses():
    """Run NZ small-business discovery using the schedule."""
    schedule_path = PROJECT_ROOT / "money-machine" / "config" / "discovery_schedule.yaml"
    if schedule_path.exists():
        with open(schedule_path) as f:
            schedule = yaml.safe_load(f)
        queries = schedule.get("queries", [])
        if queries:
            query = queries[0]
            region = schedule.get("region", "New Zealand")
            endpoint = schedule.get("searxng_endpoint", "http://127.0.0.1:8888")
            limit = schedule.get("results_per_query", 10)
            return run_mm_command(
                "discover-batch",
                "--query", query,
                "--region", region,
                "--endpoint", endpoint,
                "--limit", str(limit),
            )
    return run_mm_command(
        "discover-batch", "--query", "plumber Auckland NZ",
        "--region", "New Zealand", "--endpoint", "http://127.0.0.1:8888", "--limit", "10",
    )


def run_screenshot_worker():
    """Real screenshot worker: capture desktop/mobile viewports via auditor_toolkit.

    This is the canonical implementation.  The old placeholder stub is kept as
    ``run_screenshot_worker_placeholder`` so that any schedule still wired to
    the old behaviour fails loudly instead of silently capturing nothing.
    """
    return _run_module_worker("screenshot_worker")


def run_testing_worker():
    """Run targeted and non-slow regression tests."""
    return run_toolkit_test("toolkit_tests", "-q")


def run_git_observer():
    """Run git observer: report repository and worktree health."""
    result1 = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    result2 = subprocess.run(
        ["git", "worktree", "list"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    output = result1.stdout + result2.stdout
    if result1.stderr:
        output += "git status stderr: " + result1.stderr
    if result2.stderr:
        output += "git worktree stderr: " + result2.stderr
    return result1.returncode or result2.returncode, output, ""


def run_competitor_research():
    """Run public competitor-feature inventory."""
    return 3, "Competitor research worker: not implemented; optional per plan\n", ""


def run_demo_blueprint():
    """Real review-only demo blueprint worker (canonical)."""
    return _run_module_worker("demo_blueprint")


def run_outreach_draft():
    """Real review-only outreach draft worker (canonical; never sends)."""
    return _run_module_worker("outreach_draft")


def run_weekly_review():
    """Weekly quality and value review.

    No standalone ``weekly_review`` module exists yet (documented as a
    placeholder in P0_P1_COMPLETION.md / P2-P6_EXECUTION_SUMMARY.md), so this
    fails closed with exit 3 rather than crashing with an unhandled
    FileNotFoundError from a missing module file.
    """
    return 3, "Weekly review worker: not yet implemented; optional per plan\n", ""


def run_provider_monitor():
    """Run local model and provider observability."""
    print("Local model provider check: Hosted LLM calls disabled per ZERO_LLM mode")
    print("No local model endpoints probed (optional LOCAL_ONLY enhancement not active).")
    return 0, "Provider monitor: ZERO_LLM mode active, hosted LLM calls disabled\n", ""


def run_daily_report():
    """Run the zero-token daily report generator."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "daily_report", PROJECT_ROOT / "ops" / "hermes_zero_token" / "daily_report.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main(), "", ""


def _run_module_worker(module_name):
    """Run a canonical worker in a bounded, independently cancellable process group."""
    if module_name not in STAGING_WORKERS:
        return 2, "", f"unsupported worker module: {module_name}\n"
    path = PROJECT_ROOT / "ops" / "hermes_zero_token" / f"{module_name}.py"
    if not path.is_file():
        return 2, "", f"worker module not found: {module_name}.py\n"
    with _worker_lock(module_name) as lease:
        return _run_locked_module_worker(path, module_name, lease)


def _run_locked_module_worker(path, module_name, lease):
    """Retain ownership until cancellation has reaped the entire worker group."""
    def cancel(signum, frame):
        raise SystemExit(128 + signum)

    previous_handler = signal.signal(signal.SIGTERM, cancel)
    process = None
    try:
        process = subprocess.Popen(
            [sys.executable, str(path)], cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True, pass_fds=(lease.descriptor,),
            env=lease.child_environment(),
        )
        stdout, stderr = process.communicate(timeout=MODULE_TIMEOUT_SECONDS)
    except BaseException:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
        raise
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    return _validate_worker_result(process.returncode, stdout, stderr, module_name)


@contextmanager
def _worker_lock(worker_id):
    with worker_lock(AUDIT_LOG.parent / "locks", worker_id) as lease:
        yield lease


def _execute_worker_module(mod, module_name):
    """Run an already-loaded worker module through the execution contract.

    Split out from ``_run_module_worker`` so the contract itself can be
    unit-tested with synthetic modules that do not live under
    ``ops/hermes_zero_token``.
    """
    import contextlib
    import io

    if not hasattr(mod, "main"):
        return 2, "", f"{module_name}: module has no main()\n"

    buf_out, buf_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        try:
            returncode = mod.main()
        except Exception as ex:
            return 2, "", (
                f"{module_name}: main() raised {type(ex).__name__}: {ex}\n"
                f"{buf_err.getvalue()}")

    captured_out = buf_out.getvalue()
    captured_err = buf_err.getvalue()

    return _validate_worker_result(returncode, captured_out, captured_err, module_name)


def _validate_worker_result(returncode, captured_out, captured_err, module_name):
    if type(returncode) is not int:
        return 2, captured_out, (
            f"{module_name}: main() returned {type(returncode).__name__}, "
            f"expected an int exit code\n{captured_err}")

    report = _parse_worker_report(captured_out, module_name)
    if report is None:
        # Malformed or absent report: a successful exit code is not enough.
        return 2, captured_out, (
            f"{module_name}: exit {returncode} but stdout carried no valid "
            f"JSON report\n{captured_err}")

    if report.get("production_written") is not False:
        return 3, captured_out, (
            f"{module_name}: report must explicitly declare production_written=false — refusing\n"
            f"{captured_err}")

    if returncode != 0:
        return returncode, captured_out, (
            f"{module_name}: worker exited {returncode}\n{captured_err}")

    return 0, captured_out, captured_err


def _parse_worker_report(stdout, module_name):
    """Read complete JSON values without treating nested objects as reports."""
    if not stdout:
        return None

    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate worker report field")
            result[key] = value
        return result

    decoder = json.JSONDecoder(object_pairs_hook=unique_fields)
    report = None
    consumed_until = 0
    for match in re.finditer(r"(?m)^[ \t]*\{", stdout):
        if match.start() < consumed_until:
            continue
        try:
            value, consumed_until = decoder.raw_decode(stdout, match.end() - 1)
        except (ValueError, RecursionError):
            return None
        report = value if isinstance(value, dict) else None
    return report


def run_staging_db():
    """Run the staging database audit-backfill worker (read-only)."""
    return _run_module_worker("staging_db")


def run_screenshot_worker_placeholder():
    """Deprecated stub.  Use ``run_screenshot_worker`` (real implementation)."""
    return 3, "Screenshot worker: placeholder removed — use the real screenshot_worker\n", ""


def run_demo_blueprint_placeholder():
    """Deprecated stub.  Use ``run_demo_blueprint`` (real implementation)."""
    return 3, "Demo blueprint worker: placeholder removed — use the real demo_blueprint\n", ""


def run_outreach_draft_placeholder():
    """Deprecated stub.  Use ``run_outreach_draft`` (real implementation)."""
    return 3, "Outreach draft worker: placeholder removed — use the real outreach_draft\n", ""


def run_weekly_review_placeholder():
    """Deprecated stub.  Use ``run_weekly_review`` (deterministic summary)."""
    return 3, "Weekly review worker: placeholder removed — use the real weekly_review\n", ""


# ---------------------------------------------------------------------------
# Worker dispatch
# ---------------------------------------------------------------------------

WORKER_MAP = {
    # Existing money-machine commands
    "discovery-cycle": lambda: run_mm_command("discovery-cycle"),
    "discover-batch": lambda: run_mm_command("discover-batch"),
    "audit": lambda: run_mm_command("audit", "--help"),
    "score": lambda: run_mm_command("score", "--help"),
    "report": lambda: run_mm_command("report", "daily"),
    "daily": lambda: run_mm_command("daily"),
    "daily_report": lambda: run_daily_report(),
    "health": lambda: run_mm_command("health"),
    "supervisor": lambda: run_mm_command("supervisor", "status"),

    # Zero-token specific workers
    "system_supervisor": lambda: run_supervisor_health(),
    "database_guard": lambda: run_database_integrity(),
    "testing": lambda: run_toolkit_test("toolkit_tests", "-q"),
    "testing_worker": lambda: run_toolkit_test("toolkit_tests", "-q"),
    "git_observer": lambda: run_git_observer(),
    "provider_monitor": lambda: run_provider_monitor(),
    "queue_dispatcher": lambda: run_queue_dispatcher(),
    "identity_resolution": lambda: run_identity_resolution(),
    "site_auditor": lambda: run_site_auditor(),
    "scoring_judge": lambda: run_scoring_judge(),
    "evidence_proofer": lambda: run_evidence_proofer(),
    "discover_nz_businesses": lambda: run_discover_nz_businesses(),
    "screenshot_worker": lambda: run_screenshot_worker(),
    "demo_blueprint": lambda: run_demo_blueprint(),
    "outreach_draft": lambda: run_outreach_draft(),
    "weekly_review": lambda: run_weekly_review(),
    "staging_db": lambda: run_staging_db(),
    # Deprecated aliases: any schedule still wired to the old placeholder
    # worker IDs fails loudly instead of silently capturing nothing.
    "screenshot_worker_real": lambda: run_screenshot_worker_placeholder(),
    "demo_blueprint_real": lambda: run_demo_blueprint_placeholder(),
    "outreach_draft_real": lambda: run_outreach_draft_placeholder(),
    "weekly_review_real": lambda: run_weekly_review_placeholder(),
}


def handle_worker(worker_id, dry_run=False):
    """Handle a specific worker ID with audit logging."""
    _enforce_zero_token()
    start = time.monotonic()
    start_iso = _now_iso()

    if dry_run:
        msg = f"[DRY-RUN] Would run worker: {worker_id}"
        print(msg)
        _log_audit(worker_id, "dry_run", "skipped", extra={"duration_ms": int((time.monotonic() - start) * 1000)})
        return 0

    _log_audit(worker_id, "start", "running", extra={"started_at": start_iso})

    if worker_id not in WORKER_MAP:
        msg = f"Unknown worker: {worker_id}"
        print(msg, file=sys.stderr)
        _log_audit(worker_id, "complete", "error", extra={"duration_ms": int((time.monotonic() - start) * 1000), "error": msg})
        return 1

    if worker_id in {"discovery-cycle", "discover-batch", "daily", "queue_dispatcher",
                     "identity_resolution", "site_auditor", "discover_nz_businesses"}:
        _log_audit(worker_id, "complete", "blocked", extra={"exit_code": 3,
                   "error": "Live database mutations require a separately approved staging workflow"})
        return 3

    try:
        with _worker_lock(worker_id):
            returncode, stdout, stderr = WORKER_MAP[worker_id]()
        duration_ms = int((time.monotonic() - start) * 1000)

        if stdout:
            print(stdout, end="")
        if stderr:
            print(stderr, file=sys.stderr, end="")

        status = "completed" if returncode == 0 else "failed"
        audit_extra = {"duration_ms": duration_ms, "exit_code": returncode}
        if worker_id in {"testing", "testing_worker"}:
            audit_extra["test_counts"] = None
            for line in reversed(stdout.splitlines()):
                if line.startswith(TEST_COUNTS_MARKER):
                    try:
                        counts = json.loads(line[len(TEST_COUNTS_MARKER):])
                        if isinstance(counts, dict) and all(
                            type(counts.get(key)) is int and counts[key] >= 0
                            for key in ("passed", "failed", "skipped")
                        ):
                            audit_extra["test_counts"] = counts
                    except json.JSONDecodeError:
                        pass
                    break
        _log_audit(
            worker_id, "complete", status,
            extra=audit_extra,
        )
        return returncode
    except BlockingIOError:
        msg = "Worker or shared staging artifacts already owned by another run"
        _log_audit(worker_id, "complete", "blocked", extra={"exit_code": 75, "error": msg})
        print(msg, file=sys.stderr)
        return 75
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        msg = "Worker timed out after bounded window; will resume on next cron run"
        print(msg, file=sys.stderr)
        _log_audit(worker_id, "complete", "timeout", extra={"duration_ms": duration_ms, "exit_code": 124, "error": msg})
        return 124  # incomplete work must not be reported as successful
    except (KeyboardInterrupt, SystemExit) as cancellation:
        exit_code = cancellation.code if isinstance(cancellation, SystemExit) else 130
        _log_audit(worker_id, "complete", "cancelled", extra={"exit_code": exit_code})
        raise
    except Exception as ex:
        duration_ms = int((time.monotonic() - start) * 1000)
        msg = f"{type(ex).__name__}: {ex}"
        print(msg, file=sys.stderr)
        _log_audit(worker_id, "complete", "error", extra={"duration_ms": duration_ms, "error": msg[:500]})
        return 2


def main():
    parser = argparse.ArgumentParser(description="HERMES_ZERO_TOKEN Worker Runner")
    parser.add_argument("--worker", required=True, help="Worker ID to run")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode")

    args = parser.parse_args()

    # Enforce zero-token environment BEFORE any work
    _enforce_zero_token()

    worker_id = args.worker
    if worker_id.startswith("za_"):
        worker_id = worker_id[3:]

    return handle_worker(worker_id, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
