"""Offline, real-SQLite admission, crash, concurrency and accounting checks."""

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import mm_financial_admission as admission
import pytest

from toolkit_tests.financial_admission_fixtures import fixture_coordinator, write_fixture_policy

FCC = ("fcc", "fixture:free", "http://127.0.0.1:8082/v1/chat/completions", 64)
HERMES = ("openrouter", "fixture:free", "https://openrouter.ai/api/v1/chat/completions", 64)


def response(model="fixture:free", cost=0, status=200):
    return status, {"model": model, "usage": {"cost": cost}, "choices": [{"message": {"content": "synthetic"}}]}


def rows(coordinator):
    with sqlite3.connect(coordinator.database) as conn:
        return conn.execute("SELECT state FROM reservations ORDER BY rowid").fetchall()


def both_routes():
    return [{"provider": p, "model": m, "endpoint": e} for p, m, e, _ in [FCC, HERMES]]


def test_no_policy_or_environment_flag_can_activate(tmp_path, monkeypatch):
    for name in ["MM_ROOT", "MM_FINANCIAL_ROOT", "HERMES_ALLOW_HOSTED_LLM", "HERMES_ALLOW_PAID_FALLBACK"]:
        monkeypatch.setenv(name, "1")
    coordinator = admission.Coordinator(tmp_path / "absent")
    with pytest.raises(admission.AdmissionError):
        coordinator.execute(*FCC, lambda: pytest.fail("inference dispatched"))
    assert not coordinator.directory.exists()


def test_worktrees_and_runtime_roots_share_control_directory(monkeypatch, tmp_path):
    candidate = Path(__file__).resolve().parents[1]
    canonical = Path("/Users/dd/WEBSITE-AUDITOR")
    assert admission.control_directory(candidate) == admission.control_directory(canonical)
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    assert admission.get_coordinator().directory == admission.control_directory(candidate)


def test_concurrent_providers_share_atomic_account_quota(tmp_path):
    coordinator = fixture_coordinator(tmp_path, routes=both_routes(), limit=4, used=1)

    def attempt(index):
        try:
            coordinator.execute(*(FCC if index % 2 else HERMES), response)
            return True
        except admission.AdmissionError:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        completed = list(executor.map(attempt, range(20)))
    assert sum(completed) == 3
    assert rows(coordinator) == [("SETTLED",)] * 3


@pytest.mark.parametrize("cost", [None, True, False, "NaN", "Infinity", "-1", "bad", "0.01"])
def test_unknown_or_nonzero_accounting_is_persistent_global_stop(tmp_path, cost):
    coordinator = fixture_coordinator(tmp_path, routes=both_routes())
    with pytest.raises(admission.AdmissionStoppedError):
        coordinator.execute(*FCC, lambda: response(cost=cost))
    fresh = admission.Coordinator(tmp_path)
    with pytest.raises(admission.AdmissionStoppedError):
        fresh.execute(*HERMES, lambda: pytest.fail("fallback dispatched"))
    assert rows(coordinator) == [("UNKNOWN",)]


def test_zero_receipt_consumes_quota_and_exact_model_is_required(tmp_path):
    coordinator = fixture_coordinator(tmp_path, limit=2)
    assert coordinator.execute(*FCC, response)[0] == 200
    with pytest.raises(admission.AdmissionStoppedError, match="model_not_approved"):
        coordinator.execute(*FCC, lambda: response(model="other:free"))
    assert rows(coordinator) == [("SETTLED",), ("UNKNOWN",)]


@pytest.mark.parametrize("status", [401, 402, 429])
def test_account_error_blocks_fallback_even_when_reported_free(tmp_path, status):
    coordinator = fixture_coordinator(tmp_path, routes=both_routes())
    with pytest.raises(admission.AdmissionStoppedError, match="quota_block"):
        coordinator.execute(*FCC, lambda: response(status=status))
    with pytest.raises(admission.AdmissionStoppedError):
        coordinator.execute(*HERMES, lambda: pytest.fail("fallback dispatched"))


def test_proven_zero_cost_server_failure_can_use_separately_admitted_fallback(tmp_path):
    coordinator = fixture_coordinator(tmp_path, routes=both_routes(), limit=2)
    assert coordinator.execute(*FCC, lambda: response(status=500))[0] == 500
    assert coordinator.execute(*HERMES, response)[0] == 200
    assert rows(coordinator) == [("SETTLED",), ("SETTLED",)]
    with pytest.raises(admission.AdmissionError, match="quota exhausted"):
        coordinator.execute(*FCC, lambda: pytest.fail("third request"))


def test_pre_dispatch_crash_lease_can_expire_without_spending(tmp_path):
    clock = [1000.0]
    coordinator = fixture_coordinator(tmp_path, limit=1, clock=lambda: clock[0])
    old = coordinator.reserve(*FCC)
    clock[0] += 121
    assert coordinator.execute(*FCC, response)[0] == 200
    with pytest.raises(admission.AdmissionError):
        coordinator.dispatch(old)
    assert rows(coordinator) == [("RELEASED",), ("SETTLED",)]


def test_real_process_crash_after_dispatch_is_not_retried_or_refunded(tmp_path):
    clock = [1000.0]
    coordinator = fixture_coordinator(tmp_path, routes=both_routes(), clock=lambda: clock[0])
    source = Path(admission.__file__).parent
    code = ("import sys,os;sys.path.insert(0,sys.argv[1]);import mm_financial_admission as a;"
            "c=a.Coordinator(sys.argv[2],clock=lambda:1000.0);"
            "t=c.reserve('fcc','fixture:free','http://127.0.0.1:8082/v1/chat/completions',64);"
            "c.dispatch(t);os._exit(17)")
    result = subprocess.run([sys.executable, "-B", "-c", code, str(source), str(tmp_path)],
                            env={"PATH": os.environ.get("PATH", "")}, timeout=10)
    assert result.returncode == 17
    clock[0] += 121
    with pytest.raises(admission.AdmissionStoppedError, match="expired_dispatch"):
        coordinator.execute(*HERMES, lambda: pytest.fail("crashed request refunded"))
    policy = json.loads((tmp_path / "policy.json").read_text())
    policy.update(window_id="NEXT_TEST_WINDOW", window_start=clock[0] - 1, window_end=clock[0] + 3600)
    write_fixture_policy(tmp_path, policy, clock[0])
    with pytest.raises(admission.AdmissionStoppedError):
        coordinator.execute(*HERMES, lambda: pytest.fail("reset bypassed incident"))
    assert rows(coordinator) == [("UNKNOWN",)]


def test_dispatch_token_cannot_be_replayed(tmp_path):
    coordinator = fixture_coordinator(tmp_path)
    token = coordinator.reserve(*FCC)
    coordinator.dispatch(token)
    with pytest.raises(admission.AdmissionError):
        coordinator.dispatch(token)
    coordinator.reconcile(token, *response())
    with pytest.raises(admission.AdmissionError):
        coordinator.reconcile(token, *response())


def test_timeout_retains_unknown_outcome_without_second_action(tmp_path):
    coordinator = fixture_coordinator(tmp_path, routes=both_routes())

    def timeout():
        raise TimeoutError("synthetic")

    with pytest.raises(TimeoutError):
        coordinator.execute(*FCC, timeout)
    with pytest.raises(admission.AdmissionStoppedError):
        coordinator.execute(*HERMES, lambda: pytest.fail("fallback after timeout"))


@pytest.mark.parametrize("operation", ["delete", "corrupt"])
def test_missing_or_corrupt_ledger_is_not_recreated(tmp_path, operation):
    coordinator = fixture_coordinator(tmp_path)
    if operation == "delete":
        coordinator.database.unlink()
    else:
        coordinator.database.write_bytes(b"synthetic-corruption")
    with pytest.raises(admission.AdmissionError):
        coordinator.execute(*FCC, lambda: pytest.fail("accounting unavailable"))
    with pytest.raises(admission.AdmissionError):
        coordinator.initialize()
    assert coordinator.database.exists() == (operation == "corrupt")


def test_accounting_lock_failure_never_dispatches(tmp_path):
    coordinator = fixture_coordinator(tmp_path)
    with sqlite3.connect(coordinator.database) as held:
        held.execute("BEGIN IMMEDIATE")
        with pytest.raises(admission.AdmissionError, match="unavailable"):
            coordinator.execute(*FCC, lambda: pytest.fail("request before reservation commit"))
    assert rows(coordinator) == []


def test_review_binds_entire_policy_and_window_quota_cannot_be_inflated(tmp_path):
    coordinator = fixture_coordinator(tmp_path, limit=1)
    coordinator.execute(*FCC, response)
    policy = json.loads((tmp_path / "policy.json").read_text())
    policy["request_limit"] = 99
    (tmp_path / "policy.json").write_text(json.dumps(policy))
    with pytest.raises(admission.AdmissionError, match="does not bind"):
        coordinator.reserve(*FCC)
    write_fixture_policy(tmp_path, policy, coordinator.clock())
    with pytest.raises(admission.AdmissionError, match="changed within a window"):
        coordinator.reserve(*FCC)


@pytest.mark.parametrize("fault", ["unreviewed", "expired", "duplicate", "symlink", "hardlink", "public"])
def test_invalid_review_artifacts_are_held(tmp_path, fault):
    coordinator = fixture_coordinator(tmp_path)
    path = tmp_path / "entitlement-receipt.json"
    if fault == "unreviewed":
        path.write_text("{}")
    elif fault == "expired":
        coordinator.clock = lambda: 1e12
    elif fault == "duplicate":
        policy = tmp_path / "policy.json"
        policy.write_text(policy.read_text().replace('{', '{"enabled":true,', 1))
    elif fault in {"symlink", "hardlink"}:
        saved = tmp_path / "saved.json"
        path.rename(saved)
        path.symlink_to(saved) if fault == "symlink" else os.link(saved, path)
    else:
        path.chmod(0o644)
    with pytest.raises(admission.AdmissionError):
        coordinator.execute(*FCC, lambda: pytest.fail("unverified account evidence used"))


def test_policy_change_between_reservation_and_dispatch_is_held(tmp_path):
    coordinator = fixture_coordinator(tmp_path)
    token = coordinator.reserve(*FCC)
    policy = json.loads((tmp_path / "policy.json").read_text())
    policy["max_output_tokens"] = 1
    write_fixture_policy(tmp_path, policy, coordinator.clock())
    with pytest.raises(admission.AdmissionError):
        coordinator.dispatch(token)
    assert rows(coordinator) == [("RESERVED",)]


def test_separate_processes_cannot_overbook_one_ledger(tmp_path):
    coordinator = fixture_coordinator(tmp_path, limit=3)
    source = Path(admission.__file__).parent
    code = ("import sys;sys.path.insert(0,sys.argv[1]);import mm_financial_admission as a;"
            "c=a.Coordinator(sys.argv[2]);\n"
            "try:\n c.execute('fcc','fixture:free','http://127.0.0.1:8082/v1/chat/completions',64,"
            "lambda:(200,{'model':'fixture:free','usage':{'cost':0}}))\n"
            "except a.AdmissionError:\n sys.exit(3)\n")
    processes = [subprocess.Popen([sys.executable, "-B", "-c", code, str(source), str(tmp_path)],
                                  env={"PATH": os.environ.get("PATH", "")},
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(8)]
    try:
        for process in processes:
            _stdout, stderr = process.communicate(timeout=10)
            assert not stderr
        assert [p.returncode for p in processes].count(0) == 3
        assert [p.returncode for p in processes].count(3) == 5
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    assert rows(coordinator) == [("SETTLED",)] * 3


def test_earlier_unknown_dispatch_blocks_a_later_reserved_token(tmp_path):
    clock = [1000.0]
    coordinator = fixture_coordinator(tmp_path, clock=lambda: clock[0])
    first = coordinator.reserve(*FCC)
    coordinator.dispatch(first)
    clock[0] += 110
    later = coordinator.reserve(*FCC)
    clock[0] += 11
    with pytest.raises(admission.AdmissionStoppedError, match="expired_dispatch"):
        coordinator.dispatch(later)
    assert rows(coordinator) == [("UNKNOWN",), ("RESERVED",)]
    with pytest.raises(admission.AdmissionStoppedError):
        coordinator.reserve(*FCC)
