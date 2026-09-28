"""Tests for deterministic Money Machine preparation.

Synthetic only: no network, model, deployment, or external send.
"""
from pathlib import Path
from unittest.mock import patch

import mm_preparation_worker as prep
import mm_workers


def report():
    return {
        "run_id": "run-fixture",
        "status": "complete",
        "url": "https://fixture.example.co.nz/",
        "artifacts": {"json": "/tmp/run-fixture/report.json"},
        "defects": [{"defect_key": "viewport"}],
    }


def item(state, bid=7):
    return {"state": state, "business_id": bid, "payload": "{}"}


def test_verified_enters_remediation_without_models_or_sends():
    nxt, reason, evidence = prep.preparation_worker_handler(None, item("VERIFIED"), None)
    assert nxt == "REMEDIATION_PENDING"
    assert evidence["model_calls"] == 0
    assert evidence["paid_ai_cost_usd"] == 0
    assert evidence["external_sends"] == 0


def test_remediation_pending_builds_preview_and_advances_one_edge(tmp_path):
    remediation = {
        "items": [{"defect_key": "viewport"}],
        "production_changes": 0,
        "external_dispatch": False,
    }
    with patch.object(prep, "_canonical_report", return_value=report()), \
         patch.object(prep, "_workspace", return_value=tmp_path), \
         patch.object(prep, "_build_remediation", return_value=remediation) as build:
        nxt, reason, evidence = prep.preparation_worker_handler(
            object(), item("REMEDIATION_PENDING"), None
        )

    assert nxt == "DEMO_PENDING"
    assert evidence["preview_items"] == 1
    assert evidence["production_changes"] == 0
    assert evidence["external_dispatch"] is False
    assert evidence["model_calls"] == 0
    assert evidence["paid_ai_cost_usd"] == 0
    assert evidence["external_sends"] == 0
    build.assert_called_once()


def test_demo_pending_builds_local_concept_and_never_deploys(tmp_path):
    remediation = {"items": [], "production_changes": 0, "external_dispatch": False}
    demo_path = tmp_path / "demo" / "index.html"
    demo = {
        "demo_html": str(demo_path),
        "status": "CONCEPT_ONLY",
        "local_concept": True,
        "live_site_changed": False,
        "external_deploy": False,
    }
    with patch.object(prep, "_canonical_report", return_value=report()), \
         patch.object(prep, "_workspace", return_value=tmp_path), \
         patch.object(prep, "_build_remediation", return_value=remediation), \
         patch.object(prep, "_build_demo", return_value=demo):
        nxt, reason, evidence = prep.preparation_worker_handler(
            object(), item("DEMO_PENDING"), None
        )

    assert nxt == "DEMO_READY"
    assert evidence["status"] == "CONCEPT_ONLY"
    assert evidence["local_concept"] is True
    assert evidence["live_site_changed"] is False
    assert evidence["external_deploy"] is False
    assert evidence["model_calls"] == 0
    assert evidence["external_sends"] == 0


def test_demo_ready_records_deterministic_qa_before_qa_pending(tmp_path):
    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    demo = demo_dir / "index.html"
    demo.write_text("<!doctype html><html></html>")

    with patch.object(prep, "_canonical_report", return_value=report()), \
         patch.object(prep, "_workspace", return_value=tmp_path), \
         patch("mm_operator.demo_qa", return_value={"score": 90, "passed": True}) as qa:
        nxt, reason, evidence = prep.preparation_worker_handler(
            object(), item("DEMO_READY"), None
        )

    assert nxt == "QA_PENDING"
    assert evidence["score"] == 90
    assert evidence["passed"] is True
    assert evidence["model_calls"] == 0
    assert evidence["external_sends"] == 0
    qa.assert_called_once()


def test_worker_registration_consumes_demo_ready():
    states, handler = mm_workers.WORKERS["preparation"]
    assert "DEMO_READY" in states
    assert handler is prep.preparation_worker_handler
