"""Synthetic account evidence for offline accounting tests; never live approval."""

import hashlib
import json
import time
from pathlib import Path

import mm_financial_admission as admission


def fixture_coordinator(directory, *, routes=None, limit=100, used=0, clock=time.time, initialize=True):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    policy = {
        "version": 1, "enabled": True, "ledger_id": "TEST_SYNTHETIC_LEDGER",
        "account_id": "TEST_SYNTHETIC_ACCOUNT", "window_id": "TEST_SYNTHETIC_WINDOW",
        "window_start": clock() - 1, "window_end": clock() + 3600,
        "quota_unit": "requests", "included_zero_cost": True,
        "request_limit": limit, "used_requests": used, "max_output_tokens": 2048,
        "reservation_ttl_seconds": 120,
        "routes": routes or [{"provider": "fcc", "model": "fixture:free",
                              "endpoint": "http://127.0.0.1:8082/v1/chat/completions"}],
    }
    write_fixture_policy(directory, policy, clock())
    coordinator = admission.Coordinator(directory, clock=clock)
    if initialize:
        coordinator.initialize()
    return coordinator


def write_fixture_policy(directory, policy, now):
    """Explicit fixture only: no independent or production entitlement is claimed."""
    directory = Path(directory)
    policy = {k: v for k, v in policy.items() if k != "entitlement_receipt_sha256"}
    digest = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()
    receipt = {"status": "APPROVED_INCLUDED_ZERO_COST", "policy_sha256": digest,
               "account_id": policy["account_id"], "reviewer": "TEST_SYNTHETIC_REVIEWER",
               "reviewed_at": now, "valid_until": policy["window_end"]}
    raw = json.dumps(receipt).encode()
    policy["entitlement_receipt_sha256"] = hashlib.sha256(raw).hexdigest()
    for name, data in [("entitlement-receipt.json", raw), ("policy.json", json.dumps(policy).encode())]:
        path = directory / name
        path.write_bytes(data)
        path.chmod(0o600)
