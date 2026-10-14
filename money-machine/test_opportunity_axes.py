"""Pipeline qualification keeps commercial and technical scores independent."""
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MM_DIR = ROOT / "money-machine"
if str(MM_DIR) not in sys.path:
    sys.path.insert(0, str(MM_DIR))

import mm_pipeline  # noqa: E402 - explicit standalone test import path
import mm_workers  # noqa: E402 - explicit standalone test import path

from toolkit_tests.coverage_fixtures import with_current_coverage  # noqa: E402


def database():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.execute("CREATE TABLE businesses(id INTEGER PRIMARY KEY, name TEXT, region TEXT, public_website TEXT)")
    d.execute("CREATE TABLE mm_evidence(id INTEGER PRIMARY KEY, business_id INTEGER)")
    mm_pipeline.migrate(d)
    d.execute("INSERT INTO businesses(id,name,region,public_website) "
              "VALUES(1,'Fixture Plumbing','Canterbury','https://fixture.example')")
    return d


def lead(score, tier="COLD"):
    return {"qualification_score": score, "tier": tier, "reasons": ["fixture signal"]}


def record(d, state, evidence):
    mm_pipeline._record(d, 1, None, state, "fixture", "captured stage evidence", evidence)


def qualify(d, commercial_score, payload=None):
    row = {"business_id": 1, "payload": json.dumps(payload or {})}
    with patch("mm_lead_qualifier.qualify_lead", return_value=lead(commercial_score)):
        return mm_workers.qualification_handler(d, row, None)


def test_qualification_keeps_high_commercial_and_low_technical_scores_separate():
    d = database()
    record(d, "AUDITED", {"defect_count": 1, "score": 25})
    record(d, "QUALIFICATION_PENDING", {"opportunity_score": {"score": 44.5}})

    state, _, result = qualify(d, 85)

    assert state == "CONTACT_PENDING"
    assert result["commercial_score"] == 85
    assert result["commercial_opportunity_score"] == 44.5
    assert result["commercial_opportunity"]["score"] == 44.5
    assert result["technical_score"] == 25
    assert result["qualification_basis"] == ["commercial"]
    assert "combined_score" not in result


def test_technical_only_qualification_does_not_inflate_commercial_score():
    d = database()
    record(d, "AUDITED", {"defect_count": 4, "score": 72})
    record(d, "QUALIFICATION_PENDING", {"opportunity_score": {"score": 10}})

    state, _, result = qualify(d, 12)

    assert state == "CONTACT_PENDING"
    assert result["commercial_score"] == 12
    assert result["commercial_opportunity_score"] == 10
    assert result["commercial_opportunity"]["score"] == 10
    assert result["technical_score"] == 72
    assert result["technical_tier"] == "HIGH_NEED"
    assert result["qualification_basis"] == ["technical"]


def test_missing_audit_event_cannot_create_technical_score_from_intake_payload():
    d = database()

    state, _, result = qualify(d, 5, payload={"score": 99, "defect_count": 20})

    assert state == "REJECTED"
    assert result["technical_score"] is None
    assert result["technical_evidence"]["stage"] == "MISSING"
    assert result["qualification_basis"] == []


def test_invalid_or_zero_finding_evidence_stays_unknown():
    assert mm_workers._technical_opportunity({"defect_count": 0, "score": 100}) == (None, 0)
    assert mm_workers._technical_opportunity({"defect_count": 2, "score": "unknown"}) == (None, 2)
    assert mm_workers._technical_opportunity({"defect_count": 2, "score": float("nan")}) == (None, 2)
    assert mm_workers._technical_opportunity({"defect_count": 2, "score": float("inf")}) == (None, 2)
    assert mm_workers._technical_opportunity({"defect_count": 2, "score": 140}) == (100.0, 2)


def test_audit_handler_persists_canonical_defect_score_field():
    d = database()
    report = {
        "run_id": "run-opportunity",
        "status": "complete",
        "profile": "static",
        "defects": [{"defect_key": "missing-title"}],
        "defect_score": 75,
        "health_score": 25,
        "checks": {"fetch": {"required": True, "status": "ok"}},
        "artifacts": {"json": "/tmp/run-opportunity/report.json"},
    }
    report = with_current_coverage(report)

    with patch("auditor_toolkit.storage.History") as history_cls, patch(
        "auditor_toolkit.pipeline.run_audit", return_value=report
    ):
        history_cls.return_value.get_latest_valid_audit.return_value = None
        state, _, evidence = mm_workers.audit_handler(d, {"business_id": 1}, None)

    assert state == "AUDITED"
    assert evidence["defect_count"] == 1
    assert evidence["score"] == 75
    assert evidence["health_score"] == 25
    assert evidence["audit_engine"] == "auditor_toolkit"
    assert evidence["model_calls"] == 0
    assert evidence["external_sends"] == 0


def test_audit_adapter_uses_current_canonical_severity_score():
    report = {
        "run_id": "current-schema", "status": "complete", "defects": [{}],
        "severity_score": 44, "score": 44, "health_score": 56,
    }
    evidence = mm_workers._audit_evidence(report)
    assert evidence["score"] == 44
    assert evidence["score_source"] == "severity_score"
    assert mm_workers._technical_opportunity(evidence) == (44.0, 1)


def test_explicit_unknown_severity_does_not_fall_back_to_health_or_legacy_score():
    evidence = mm_workers._audit_evidence({
        "defects": [{}], "severity_score": None, "score": 99, "health_score": 1,
    })
    assert mm_workers._technical_opportunity(evidence) == (None, 1)
