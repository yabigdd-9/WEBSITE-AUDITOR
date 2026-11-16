import copy
import hashlib
import tempfile
from pathlib import Path

import pytest

from scripts import cloud_opportunities as opportunities
from scripts import cloud_prospect_pipeline as pipeline
from scripts.pipeline_store import PipelineStore

NOW = 1767225600


@pytest.fixture
def policy():
    return opportunities.load_policy(Path(__file__).resolve().parents[1])


@pytest.fixture
def entry():
    return dict(
        domain="example.com", status="COMPLETE", run_id="canonical-1",
        timestamp="2026-01-01T00:00:00Z", internal_scope_draft="INTERNAL SCOPE DRAFT - DO NOT SEND",
        findings=[dict(
            finding_id="fixture-1", defect_key="viewport", confidence="observed", severity="high",
            observed="Viewport declaration absent in the inspected HTML.",
            evidence_ref="html", evidence_check="html", evidence_check_status="ok",
            source_url="https://example.com/", remediation_action="Review and add viewport metadata.",
            independently_verified=False,
        )],
    )


def test_scores_are_deterministic_explained_and_not_intent(entry, policy):
    first = opportunities.score(entry, {}, policy, now=NOW)
    assert first == opportunities.score(copy.deepcopy(entry), {}, policy, now=NOW)
    assert first["score"] == 50
    assert first["buying_intent"] == "unknown"
    assert first["contact_eligible"] is False
    assert first["breakdown"]["delivery_feasibility"]["value"] == 0
    assert set(first["missing_context"]) == {"delivery_feasibility", "business_service_fit"}
    assert first["evidence"][0]["finding_id"] == "fixture-1"
    assert first["evidence"][0]["audit_run_id"] == entry["run_id"]
    configured = opportunities.score(entry, {"delivery_feasibility": 80, "business_service_fit": 60}, policy, now=NOW)
    assert configured["score"] == 75


@pytest.mark.parametrize("field,value", [
    ("confidence", "heuristic"), ("evidence_check_status", "partial"),
    ("evidence_ref", "missing"), ("source_url", ""), ("observed", ""),
    ("finding_id", ""), ("remediation_action", ""), ("severity", "speculative"),
    ("defect_key", "unsupported-rebuild"),
])
def test_hard_evidence_service_gates(entry, policy, field, value):
    entry["findings"][0][field] = value
    result = opportunities.score(entry, {}, policy, now=NOW)
    assert result["status"] == "quarantined"
    assert result["score"] is None
    with pytest.raises(ValueError):
        opportunities.proposal(entry, {}, policy, now=NOW)


def test_partial_empty_duplicate_and_suppressed_never_qualify(entry, policy):
    for status in ("partial", "ERROR", "INCOMPLETE"):
        assert opportunities.score({**entry, "status": status}, {}, policy, now=NOW)["score"] is None
    assert opportunities.score({**entry, "findings": []}, {}, policy, now=NOW)["score"] is None
    assert opportunities.score({**entry, "findings": entry["findings"] * 2}, {}, policy, now=NOW)["reason"] == "duplicate_finding"
    for flag in ("suppressed", "contact_prohibited"):
        assert opportunities.score(entry, {flag: True}, policy, now=NOW)["score"] is None


def test_missing_dates_reduce_score_and_unconfigured_prices_stay_unknown(entry, policy):
    del entry["timestamp"]
    score = opportunities.score(entry, {}, policy, now=NOW)
    assert score["score"] == 45
    draft = opportunities.proposal(entry, {}, policy, now=NOW)
    assert draft["pricing_status"] == "Pricing not configured"
    assert draft["indicative_quote"] is None
    assert draft["estimated_effort"] is None
    assert draft["items"][0]["complexity"] == "Unestimated"
    assert draft["binding_quote"] is False
    assert draft["approval_status"] == "HUMAN_REVIEW_REQUIRED"
    assert draft["version_sha256"] == opportunities.proposal(entry, {}, policy, now=NOW)["version_sha256"]


def test_existing_quote_rules_only_use_configured_rate_and_effort(entry, policy):
    policy["hourly_rate_nzd"] = "100"  # Synthetic fixture rate, never production config.
    assert opportunities.proposal(entry, {}, policy, now=NOW)["indicative_quote"] is None
    policy["effort_bands"] = {"viewport": "XS"}
    draft = opportunities.proposal(entry, {}, policy, now=NOW)
    assert draft["indicative_quote"]["price_band_nzd"] == {"low": "50.00", "high": "172.50"}
    original = draft["version_sha256"]
    policy["hourly_rate_nzd"] = "110"
    assert opportunities.proposal(entry, {}, policy, now=NOW)["version_sha256"] != original


def test_invalid_policy_and_service_context_fail_closed(entry, policy):
    original = copy.deepcopy(policy)
    for rate in ("NaN", "Infinity", "0", "-1", "10001"):
        with pytest.raises(ValueError):
            opportunities.validate_policy({**original, "hourly_rate_nzd": rate})
    policy["weights"]["recency"] = 10
    with pytest.raises(ValueError):
        opportunities.score(entry, {}, policy, now=NOW)
    with pytest.raises(ValueError):
        opportunities.score(entry, {"business_service_fit": True}, original, now=NOW)


def test_pipeline_persists_exact_versions_and_owner_rejections(entry, policy):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = PipelineStore(root / "pipeline.sqlite3")
        identity = hashlib.sha256(b"example.com").hexdigest()
        rows = [dict(domain="example.com", url="https://example.com/", business_service_fit=60)]

        def audit(sites, workspace, entries):
            entries.append(copy.deepcopy(entry))
            return [{"status": "COMPLETE"}]

        with store.transaction(bootstrap=True) as state:
            pipeline.process(state, rows, now=NOW, run_id="first", workspace=root,
                             audit=audit, robots=lambda _: True, opportunity_policy=policy)
        saved = store.read()["prospects"][identity]
        assert saved["opportunity"]["score"] == 59
        assert len(saved["proposal_versions"]) == 1
        with store.transaction() as state:
            opportunities.enrich(state, policy, now=NOW)
        assert len(store.read()["prospects"][identity]["proposal_versions"]) == 1
        with store.transaction() as state:
            opportunities.reject_recommendation(
                state["prospects"][identity], actor="fixture-owner", reason="Outside current capabilities", now=NOW
            )
        with store.transaction() as state:
            opportunities.enrich(state, policy, now=NOW)
        saved = store.read()["prospects"][identity]
        assert saved["opportunity"]["status"] == "owner_rejected"
        assert saved["proposal_version"] is None
        assert saved["recommendation_reviews"][0]["reason"] == "Outside current capabilities"
        with pytest.raises(ValueError):
            with store.transaction() as state:
                state["prospects"][identity]["proposal_versions"][0]["pricing_status"] = "tampered"
        with pytest.raises(ValueError):
            with store.transaction() as state:
                state["prospects"][identity]["recommendation_reviews"].clear()


def test_invalid_policy_rejects_before_any_request(policy):
    policy["weights"]["recency"] = 99
    with pytest.raises(ValueError):
        pipeline.process(pipeline.empty_state(), [], now=NOW, run_id="blocked", workspace=Path("/tmp"),
                         opportunity_policy=policy, robots=lambda _: pytest.fail("Network request"))
