"""Tests for deterministic Money Machine preparation.

Synthetic only: no network, model, deployment, or external send.
"""
import json
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


def _write_component_manifests(tmp_path):
    remediation = tmp_path / "remediation"
    demo = tmp_path / "demo"
    remediation.mkdir()
    demo.mkdir()
    (remediation / "remediation.json").write_text(json.dumps({
        "source_run_id": "run-fixture",
        "items": [{"defect_key": "viewport"}],
        "production_changes": 0,
        "external_dispatch": False,
    }))
    demo_html = demo / "index.html"
    demo_html.write_text("<!doctype html><html></html>")
    (demo / "demo.json").write_text(json.dumps({
        "source_run_id": "run-fixture",
        "demo_html": str(demo_html),
        "status": "CONCEPT_ONLY",
        "live_site_changed": False,
        "improvement_claim_valid": False,
        "external_deploy": False,
        "before": None,
        "after": None,
    }))


def test_review_packet_without_rate_never_invents_price_or_draft(tmp_path):
    _write_component_manifests(tmp_path)
    with patch.dict("os.environ", {}, clear=False), \
         patch.object(prep, "_verified_contact", return_value={
             "email": "office@fixture.example.co.nz",
             "verification": "VERIFIED_HIGH",
             "verification_id": 7,
         }):
        import os
        os.environ.pop("MM_HOURLY_RATE_NZD", None)
        packet_path, packet = prep._write_review_packet(
            object(), 7, report(), tmp_path, {"score": 90, "passed": True}
        )

    assert packet_path.is_file()
    assert packet["quote_status"] == "OPERATOR_RATE_REQUIRED"
    assert packet["quote"] is None
    assert packet["draft_status"] == "NOT_GENERATED_RATE_REQUIRED"
    assert packet["commercial_packet"] is None
    assert packet["send_enabled"] is False
    assert packet["external_send_allowed"] is False
    assert packet["external_sends"] == 0
    assert packet["paid_ai_cost_usd"] == 0


def test_review_packet_with_explicit_rate_builds_deterministic_local_packet(tmp_path):
    _write_component_manifests(tmp_path)
    with patch.dict("os.environ", {"MM_HOURLY_RATE_NZD": "150"}, clear=False), \
         patch.object(prep, "_verified_contact", return_value={
             "email": "office@fixture.example.co.nz",
             "verification": "VERIFIED_HIGH",
             "verification_id": 7,
         }):
        packet_path, packet = prep._write_review_packet(
            object(), 7, report(), tmp_path, {"score": 90, "passed": True}
        )

    assert packet_path.is_file()
    assert packet["quote_status"] == "DETERMINISTIC_QUOTE_READY"
    assert packet["quote"]["hourly_rate_nzd"] == "150.00"
    assert packet["quote"]["llm_determined_price"] is False
    assert packet["draft_status"] == "LOCAL_DRAFT_READY"
    assert Path(packet["commercial_packet"]).is_file()
    commercial = json.loads(Path(packet["commercial_packet"]).read_text())
    assert commercial["human_approved"] is False
    assert commercial["send_enabled"] is False
    assert commercial["external_send_allowed"] is False
    assert commercial["outbound_sent"] == 0
    assert commercial["paid_ai_cost_usd"] == 0


def test_qa_pending_prepares_review_packet_before_outreach_pending(tmp_path):
    class Result:
        def fetchone(self):
            return {"score": 90, "passed": 1}

    class DB:
        def execute(self, *_args, **_kwargs):
            return Result()

    packet_path = tmp_path / "review" / "packet.json"
    with patch("mm_workers.qa_handler", return_value=(
        "OUTREACH_PENDING", "demo QA passed", {"score": 90}
    )), patch.object(
        prep, "_canonical_report", return_value=report()
    ), patch.object(
        prep, "_workspace", return_value=tmp_path
    ), patch.object(
        prep, "_write_review_packet", return_value=(
            packet_path,
            {
                "quote_status": "OPERATOR_RATE_REQUIRED",
                "draft_status": "NOT_GENERATED_RATE_REQUIRED",
            },
        )
    ) as writer:
        nxt, reason, evidence = prep.preparation_worker_handler(
            DB(), item("QA_PENDING"), None
        )

    assert nxt == "OUTREACH_PENDING"
    assert evidence["review_packet"] == str(packet_path)
    assert evidence["quote_status"] == "OPERATOR_RATE_REQUIRED"
    assert evidence["human_review_required"] is True
    assert evidence["external_sends"] == 0
    assert evidence["model_calls"] == 0
    writer.assert_called_once()
