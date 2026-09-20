from pathlib import Path

import pytest

from auditor_core.evidence import build_page_evidence
from auditor_core.normalize import normalize_defects
from auditor_core.profiles import detect_site_type, resolve_profile
from auditor_core.registry import get_registry
from auditor_core.remediation import RemediationStateStore
from auditor_core.scoring import category_scores


def test_registry_maps_stable_check_id():
    registry = get_registry()
    found = registry.match("Missing HSTS")
    assert found is not None
    assert found.id == "security.hsts_missing"
    assert registry.taxonomy_version == "2026.09.21"


def test_unknown_legacy_finding_is_flagged_for_review():
    findings = normalize_defects(
        [{"defect": "Something novel", "impact": "Unknown"}],
        url="https://example.com",
    )
    assert findings[0]["check_id"] == "legacy.unclassified"
    assert findings[0]["human_review"] is True
    assert findings[0]["confidence"] == 0.55


def test_page_evidence_hashes_and_redacts_cookie():
    evidence = build_page_evidence(
        "https://example.com",
        "<html><h1>Hello</h1></html>",
        {"status": 200, "Content-Type": "text/html", "Set-Cookie": "secret=1"},
    )
    assert evidence["http_status"] == 200
    assert evidence["html_sha256"]
    assert evidence["response_headers"]["Set-Cookie"] == "[redacted]"


def test_category_scores_are_transparent():
    findings = normalize_defects(
        [
            {"defect": "Missing HSTS", "impact": "header"},
            {"defect": "Missing H1 tag", "impact": "seo"},
        ],
        url="https://example.com",
    )
    scores = category_scores(findings)
    assert scores["meaning"] == "health_score_100_is_best"
    assert scores["categories"]["security"]["finding_count"] == 1
    assert scores["categories"]["seo"]["finding_count"] == 1
    assert scores["overall_health_score"] < 100


def test_site_type_and_profile_detection():
    detected = detect_site_type(
        '<html><button>Add to cart</button><script type="application/ld+json"></script></html>',
        ["Product"],
    )
    assert detected["site_type"] == "ecommerce"
    name, profile = resolve_profile("auto", detected["site_type"])
    assert name == "ecommerce"
    assert profile["browser"] is True


def test_remediation_state_transitions(tmp_path: Path):
    store = RemediationStateStore(tmp_path / "state.json")
    first = store.transition("example|seo.h1_missing", "acknowledged", owner="Dion")
    assert first["status"] == "acknowledged"
    second = store.transition("example|seo.h1_missing", "in_progress")
    assert second["status"] == "in_progress"
    third = store.transition("example|seo.h1_missing", "patched")
    assert third["status"] == "patched"
    verified = store.transition("example|seo.h1_missing", "verified")
    assert verified["last_verified_at"]


def test_invalid_remediation_transition_fails(tmp_path: Path):
    store = RemediationStateStore(tmp_path / "state.json")
    with pytest.raises(ValueError):
        store.transition("example|seo.h1_missing", "verified")


def test_unobserved_categories_are_not_assumed_perfect():
    scores = category_scores([])
    assert scores["overall_health_score"] is None
    assert scores["categories"]["performance"]["score"] is None
    assert scores["categories"]["performance"]["tested"] is False
