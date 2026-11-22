"""Transaction-flow FSM probe tests: pure unit tests (no browser)."""
from auditor_toolkit.flows import (
    ACTION_POLICY,
    FLOW_STATES,
    flow_findings,
)


def _evidence(**overrides):
    base = {
        "mode": "lab",
        "states": {},
        "steps": [],
        "policy": dict(ACTION_POLICY),
        "limitations": "No form submission.",
        "outcome": {},
    }
    base.update(overrides)
    return base


def test_full_happy_path_reaches_form_but_not_submission():
    evidence = _evidence(
        states={
            "LANDING": {"reached": True, "at": "t0"},
            "CTA_VISIBLE": {"reached": True, "at": "t1"},
            "CTA_ACTIVATED": {"reached": True, "at": "t2"},
            "FORM_OR_BOOKING_REACHED": {"reached": True, "at": "t3"},
            "REQUIRED_FIELDS_IDENTIFIED": {"reached": True, "at": "t4"},
            "CLIENT_VALIDATION_WORKS": {"reached": True, "at": "t5"},
            "SUBMISSION_SAFE_TEST_AVAILABLE": {"reached": False, "reason": "PROHIBITED_WITHOUT_AUTHORIZATION"},
            "SUCCESS_OR_CONFIRMATION_STATE": {"reached": False, "reason": "PROHIBITED_WITHOUT_AUTHORIZATION"},
        },
        outcome={"reached_final": False, "reason": "safe_test_not_authorized", "form_fields": 3, "required_fields": 2},
    )
    findings, summary = flow_findings(evidence, "http://example.test/")
    assert findings == []  # a healthy reachable form raises no finding
    assert summary["states_reached"] == 6
    assert summary["outcome"]["reason"] == "safe_test_not_authorized"


def test_submission_states_never_reached_without_authorization():
    evidence = _evidence(
        states={"LANDING": {"reached": True}},
        outcome={"reached_final": False, "reason": "no_primary_cta_found"},
    )
    findings, _ = flow_findings(evidence, "http://example.test/")
    assert evidence["states"].get("SUBMISSION_SAFE_TEST_AVAILABLE") is None or not evidence["states"][
        "SUBMISSION_SAFE_TEST_AVAILABLE"
    ].get("reached")


def test_no_primary_cta_produces_medium_finding():
    evidence = _evidence(
        states={"LANDING": {"reached": True}},
        outcome={"reached_final": False, "reason": "no_primary_cta_found"},
    )
    findings, summary = flow_findings(evidence, "http://example.test/")
    assert [f.defect_key for f in findings] == ["flow-no-primary-cta"]
    assert findings[0].severity == "medium"
    assert findings[0].confidence == "heuristic"
    assert findings[0].check == "flow"


def test_cta_click_failure_produces_observed_finding():
    evidence = _evidence(
        states={
            "LANDING": {"reached": True},
            "CTA_VISIBLE": {"reached": True},
        },
        outcome={"reached_final": False, "reason": "cta_click_failed"},
    )
    findings, _ = flow_findings(evidence, "http://example.test/")
    keys = [f.defect_key for f in findings]
    assert "flow-cta-activation-failed" in keys
    cta_finding = next(f for f in findings if f.defect_key == "flow-cta-activation-failed")
    assert cta_finding.severity == "medium"
    assert cta_finding.confidence == "observed"


def test_no_form_after_cta_produces_finding_with_fallback():
    evidence = _evidence(
        states={
            "LANDING": {"reached": True},
            "CTA_VISIBLE": {"reached": True},
            "CTA_ACTIVATED": {"reached": True},
        },
        outcome={"reached_final": False, "reason": "no_form_or_booking_widget", "conversion_fallback": "a[href^='tel:']"},
    )
    findings, _ = flow_findings(evidence, "http://example.test/")
    finding = next(f for f in findings if f.defect_key == "flow-no-form-after-cta")
    assert "tel:" in finding.observed


def test_probe_error_produces_low_finding():
    evidence = _evidence(status="error", error="playwright missing", reason="playwright missing")
    findings, summary = flow_findings(evidence, "http://example.test/")
    assert [f.defect_key for f in findings] == ["flow-probe-failed"]
    assert findings[0].severity == "low"
    assert summary["states_reached"] == 0


def test_safe_action_policy_boundaries():
    assert ACTION_POLICY["submit_inquiry"] == "PROHIBITED_WITHOUT_AUTHORIZATION"
    assert ACTION_POLICY["start_payment"] == "PROHIBITED"
    assert ACTION_POLICY["click_internal_cta"] == "ALLOWED"
    assert ACTION_POLICY["fill_fields_dummy_no_submit"] == "ALLOWED_IF_NO_SUBMISSION"


def test_fsm_state_order_documented():
    assert FLOW_STATES[0] == "LANDING"
    assert FLOW_STATES[-1] == "SUCCESS_OR_CONFIRMATION_STATE"
    assert "SUBMISSION_SAFE_TEST_AVAILABLE" in FLOW_STATES
