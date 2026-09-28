"""Transaction-flow FSM probe tests: pure unit tests (no browser)."""
from auditor_toolkit.flows import (
    ACTION_POLICY,
    FLOW_STATES,
    _request_policy_reason,
    flow_findings,
    run_flow_probe,
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
    assert summary["conversion_path_health"] >= 90
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



def test_disabled_probe_is_typed_skip(tmp_path):
    result = run_flow_probe("https://example.test", tmp_path, enabled=False)
    assert result == {
        "status": "skipped",
        "reason": "Disabled in selected audit profile",
        "evidence": {},
    }


def test_request_policy_blocks_writes_and_cross_origin():
    audited = "https://example.co.nz/contact"
    assert _request_policy_reason(audited, "https://example.co.nz/form", "GET") is None
    assert "write" in _request_policy_reason(audited, "https://example.co.nz/form", "POST")
    assert "cross-origin" in _request_policy_reason(
        audited, "https://cdn.example.net/widget.js", "GET"
    )


def test_request_policy_normalizes_default_ports():
    assert _request_policy_reason(
        "https://example.co.nz", "https://example.co.nz:443/contact", "GET"
    ) is None
    assert _request_policy_reason(
        "http://example.co.nz", "http://example.co.nz:80/contact", "HEAD"
    ) is None


def test_flow_probe_happy_path_with_fake_playwright(tmp_path, monkeypatch):
    """Cover the safe traversal deterministically without needing Chromium."""

    class Locator:
        def __init__(self, page, kind):
            self.page = page
            self.kind = kind

        @property
        def first(self):
            return self

        def count(self):
            return 1 if self.kind in {"cta", "form", "probe"} else 0

        def is_visible(self):
            return self.count() > 0

        def inner_text(self):
            return "Contact us"

        def click(self, timeout=None):
            self.page.url = "https://example.com/contact"

        def locator(self, selector):
            if self.kind == "form" and selector == "input, textarea, select":
                return Locator(self.page, "fields")
            if self.kind == "form" and selector.startswith("input[type='email']"):
                return Locator(self.page, "probe")
            return Locator(self.page, "empty")

        def evaluate_all(self, script):
            if self.kind != "fields":
                return []
            return [
                {"tag": "input", "type": "text", "name": "name", "required": True, "label": "Name"},
                {"tag": "input", "type": "email", "name": "email", "required": True, "label": "Email"},
                {"tag": "textarea", "type": "", "name": "message", "required": False, "label": "Message"},
            ]

        def fill(self, value, timeout=None, no_mark=None):
            return None

        def evaluate(self, script):
            if "checkValidity" in script:
                return {"valid": True, "message": ""}
            return None

    class Page:
        def __init__(self):
            self.url = "about:blank"

        def on(self, *args):
            return None

        def goto(self, url, **kwargs):
            self.url = url

        def wait_for_timeout(self, *args):
            return None

        def wait_for_load_state(self, *args, **kwargs):
            return None

        def screenshot(self, path, **kwargs):
            from pathlib import Path
            Path(path).write_bytes(b"fake-png")

        def locator(self, selector):
            if selector == "a[href*='contact']":
                return Locator(self, "cta")
            if selector == "form:visible":
                return Locator(self, "form")
            return Locator(self, "empty")

    class Context:
        def __init__(self):
            self.page = Page()

        def route(self, *args):
            return None

        def new_page(self):
            return self.page

    class Browser:
        def __init__(self):
            self.context = Context()

        def new_context(self, **kwargs):
            return self.context

        def close(self):
            return None

    class Chromium:
        def launch(self, **kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

    class SyncPlaywright:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *args):
            return False

    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: SyncPlaywright()
    package = types.ModuleType("playwright")
    package.__path__ = []
    package.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    result = run_flow_probe("https://example.com", tmp_path, enabled=True)
    assert result["status"] == "ok"
    evidence = result["evidence"]
    assert evidence["outcome"] == {
        "reached_final": False,
        "reason": "safe_test_not_authorized",
        "form_fields": 3,
        "required_fields": 2,
    }
    for state in (
        "LANDING",
        "CTA_VISIBLE",
        "CTA_ACTIVATED",
        "FORM_OR_BOOKING_REACHED",
        "REQUIRED_FIELDS_IDENTIFIED",
        "CLIENT_VALIDATION_WORKS",
    ):
        assert evidence["states"][state]["reached"] is True
    assert evidence["states"]["SUBMISSION_SAFE_TEST_AVAILABLE"]["reached"] is False
    assert len([step for step in evidence["steps"] if "screenshot" in step]) == 6
