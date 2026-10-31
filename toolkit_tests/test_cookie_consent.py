"""Passive consent capture contracts: no interaction and no cookie values."""
import copy

import pytest

from auditor_toolkit.cookie_consent import analyse_html, analyse_rendered


def capture(cookies=None, controls=None):
    return {"consent": {"interaction": "none", "cookies_before_interaction": cookies or [],
                        "visible_banners": [] if controls is None else [{"controls": controls}]}}


def test_observed_empty_state_is_evidence_without_compliance_claim():
    findings, evidence = analyse_rendered(capture(), "https://fixture.example/")
    assert findings == []
    assert evidence["cookies_before_interaction"] == []
    assert evidence["visible_banner_count"] == 0
    assert "human review" in evidence["limitation"]
    assert evidence["interaction"] == "none"


def test_optional_cookie_and_choice_hints_are_heuristic_and_redact_values():
    data = capture([{"name": "_ga", "value": "PRIVATE COOKIE VALUE", "domain": ".fixture.example", "secure": True}], ["Accept all"])
    original = copy.deepcopy(data)
    first = analyse_rendered(data, "https://fixture.example/")
    assert first == analyse_rendered(data, "https://fixture.example/")
    assert data == original
    assert {f.defect_key for f in first[0]} == {"tracking-cookie-before-choice", "consent-choice-controls-unobserved"}
    assert all(f.confidence == "heuristic" and f.remediation_automation == "HUMAN_REVIEW" for f in first[0])
    assert "PRIVATE COOKIE VALUE" not in str(first)
    assert "value" not in first[1]["cookies_before_interaction"][0]


@pytest.mark.parametrize("controls", [["Accept all", "Reject optional"], ["Allow", "Manage settings"], ["Preferences"]])
def test_recognized_choice_controls_do_not_trigger_missing_choice(controls):
    findings, evidence = analyse_rendered(capture(controls=controls), "https://fixture.example/")
    assert findings == []
    assert evidence["visible_control_labels"] == controls


@pytest.mark.parametrize("data", [{}, {"consent": None}, {"consent": {"interaction": "accepted"}},
    {"consent": {"interaction": "none", "cookies_before_interaction": "unknown", "visible_banners": []}},
    capture([None]), capture([{"name": None}]), capture(controls=[None]),
    {"consent": {"interaction": "none", "cookies_before_interaction": [], "visible_banners": [None]}}])
def test_absent_or_malformed_capture_cannot_report_completed(data):
    with pytest.raises(ValueError):
        analyse_rendered(data, "https://fixture.example/")


def test_capture_bounds_and_static_observation_fail_closed():
    with pytest.raises(ValueError):
        analyse_rendered(capture([{"name": "session"}] * 1001), "https://fixture.example/")
    with pytest.raises(ValueError):
        analyse_rendered({"consent": {"interaction": "none", "cookies_before_interaction": [], "visible_banners": [{"controls": []}] * 21}}, "https://fixture.example/")
    with pytest.raises(ValueError):
        analyse_html("<p>Cookie consent</p>", "https://fixture.example/", {})
