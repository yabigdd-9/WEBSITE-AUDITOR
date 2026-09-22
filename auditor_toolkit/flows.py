"""Transaction-flow evidence: finite-state traversal of CTA/form/booking paths.

Deterministic, read-mostly browser probe. Follows the safe-action policy from
the v8 upgrade investigation: internal CTA clicks are allowed; form filling is
allowed only without submission; submission, payment and cart side effects are
prohibited by default. Every observed step is recorded with evidence so a human
reviewer can replay what the probe actually did.

No network egress happens here beyond loading the page already authorised by
run_browser_checks: the module is exercised against the same audited URL.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .common import validate_url

# Finite-state machine states, ordered by expected traversal.
FLOW_STATES = (
    "LANDING",
    "CTA_VISIBLE",
    "CTA_ACTIVATED",
    "FORM_OR_BOOKING_REACHED",
    "REQUIRED_FIELDS_IDENTIFIED",
    "CLIENT_VALIDATION_WORKS",
    "SUBMISSION_SAFE_TEST_AVAILABLE",
    "SUCCESS_OR_CONFIRMATION_STATE",
)

# Allowed interaction policy per action class (v8 safe-action policy).
ACTION_POLICY = {
    "click_internal_cta": "ALLOWED",
    "open_booking_widget": "ALLOWED",
    "fill_fields_dummy_no_submit": "ALLOWED_IF_NO_SUBMISSION",
    "submit_inquiry": "PROHIBITED_WITHOUT_AUTHORIZATION",
    "start_payment": "PROHIBITED",
    "add_to_cart": "ALLOWED_IF_NO_CHECKOUT",
    "active_vulnerability_scan": "PROHIBITED_BY_DEFAULT",
}

# Selectors that identify a primary conversion CTA, tried in order.
_CTA_SELECTORS = (
    "a[href*='contact']",
    "a[href*='book']",
    "a[href*='quote']",
    "a[href*='enquire']",
    "main a[href^='/']:not([href*='privacy']):not([href*='terms'])",
    "main button",
    "main [role=button]",
)

_FORM_SELECTORS = (
    "form:visible",
    "[role=dialog] form",
    "form input, form textarea, form select",
)

_PHONE_SELECTORS = ("a[href^='tel:']",)
_MAILTO_SELECTORS = ("a[href^='mailto:']",)

# Bound probe so a runaway page cannot loop forever.
_MAX_STEPS = 12
_STEP_TIMEOUT_MS = 4_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact(path: Path) -> dict:
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def run_flow_probe(url, output_dir, enabled=True, allow_private=False):
    """Drive the transaction-flow FSM against ``url``; return evidence dict.

    Never submits forms. Writes step screenshots into ``output_dir``. Result
    shape: {"status": "ok"|"skipped"|"error", "evidence": {...}} matching
    run_browser_checks conventions.
    """
    if not enabled:
        return {"status": "skipped", "reason": "Disabled in selected audit profile", "evidence": {}}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = {
        "mode": "lab",
        "states": {},
        "steps": [],
        "policy": dict(ACTION_POLICY),
        "limitations": "No form submission, payment or cart side effect; no synthetic inquiry sent.",
        "started_at": _now(),
    }
    try:
        from playwright.sync_api import sync_playwright

        validate_url(url, allow_private)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    service_workers="block",
                    viewport={"width": 1366, "height": 900},
                )
                # Same write-request guard philosophy as run_browser_checks:
                # anything not GET/HEAD/OPTIONS is aborted before it leaves.
                def guard(route):
                    try:
                        validate_url(route.request.url, allow_private)
                        if route.request.method not in ("GET", "HEAD", "OPTIONS"):
                            raise ValueError("Flow probe blocks write requests")
                        route.continue_()
                    except Exception as exc:
                        evidence.setdefault("blocked_requests", []).append(
                            {"reason": str(exc)[:300]}
                        )
                        route.abort()

                context.route("**/*", guard)
                page = context.new_page()
                console_errors: list[str] = []
                page.on("pageerror", lambda e: console_errors.append(str(e)[:500]))

                def record(state, detail=None, screenshot_name=None):
                    entry = {"state": state, "at": _now(), "detail": detail or {}}
                    if screenshot_name:
                        path = output_dir / screenshot_name
                        try:
                            page.screenshot(path=str(path), timeout=_STEP_TIMEOUT_MS)
                            entry["screenshot"] = _artifact(path)
                        except Exception as exc:
                            entry["screenshot_error"] = str(exc)[:200]
                    evidence["steps"].append(entry)
                    evidence["states"][state] = {
                        "reached": True,
                        "at": entry["at"],
                    }

                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(500)
                record("LANDING", {"url": page.url}, "flow-0-landing.png")

                # CTA_VISIBLE: locate a primary conversion CTA.
                cta = None
                for selector in _CTA_SELECTORS:
                    locator = page.locator(selector).first
                    try:
                        if locator.count() and locator.is_visible():
                            cta = (selector, locator)
                            break
                    except Exception:
                        continue
                if cta is None:
                    evidence["outcome"] = {
                        "reached_final": False,
                        "reason": "no_primary_cta_found",
                    }
                    evidence["console_errors"] = console_errors
                    evidence["finished_at"] = _now()
                    return {"status": "ok", "evidence": evidence}
                selector, cta_locator = cta
                record(
                    "CTA_VISIBLE",
                    {"selector": selector, "text": (cta_locator.inner_text() or "")[:120]},
                    "flow-1-cta.png",
                )

                # CTA_ACTIVATED: click internal CTA (ALLOWED by policy).
                try:
                    cta_locator.click(timeout=_STEP_TIMEOUT_MS)
                    page.wait_for_load_state("domcontentloaded", timeout=10_000)
                    page.wait_for_timeout(400)
                    record("CTA_ACTIVATED", {"landed_url": page.url}, "flow-2-activated.png")
                except Exception as exc:
                    evidence["steps"].append(
                        {"state": "CTA_ACTIVATED", "at": _now(), "failed": True, "reason": str(exc)[:300]}
                    )
                    evidence["outcome"] = {
                        "reached_final": False,
                        "reason": "cta_click_failed",
                    }
                    evidence["console_errors"] = console_errors
                    evidence["finished_at"] = _now()
                    return {"status": "ok", "evidence": evidence}

                # FORM_OR_BOOKING_REACHED: look for a form or booking widget.
                form = None
                for form_selector in _FORM_SELECTORS:
                    locator = page.locator(form_selector).first
                    try:
                        if locator.count() and locator.is_visible():
                            form = (form_selector, locator)
                            break
                    except Exception:
                        continue
                if form is None:
                    # Phone/mailto fallbacks still count as a conversion path.
                    fallback = None
                    for phone_selector in _PHONE_SELECTORS:
                        if page.locator(phone_selector).first.count():
                            fallback = phone_selector
                            break
                    if fallback is None:
                        for mailto_selector in _MAILTO_SELECTORS:
                            if page.locator(mailto_selector).first.count():
                                fallback = mailto_selector
                                break
                    evidence["outcome"] = {
                        "reached_final": False,
                        "reason": "no_form_or_booking_widget",
                        "conversion_fallback": fallback,
                    }
                    evidence["console_errors"] = console_errors
                    evidence["finished_at"] = _now()
                    return {"status": "ok", "evidence": evidence}
                form_selector, form_locator = form
                record(
                    "FORM_OR_BOOKING_REACHED",
                    {"selector": form_selector, "landed_url": page.url},
                    "flow-3-form.png",
                )

                # REQUIRED_FIELDS_IDENTIFIED: enumerate required fields.
                fields = form_locator.locator("input, textarea, select").evaluate_all(
                    """els => els.slice(0, 25).map(el => ({
                        tag: el.tagName.toLowerCase(),
                        type: el.getAttribute('type') || '',
                        name: el.getAttribute('name') || '',
                        required: el.required || el.getAttribute('required') !== null,
                        label: (el.labels && el.labels[0] && el.labels[0].innerText || '').trim().slice(0, 80),
                    }))"""
                )
                required_fields = [f for f in fields if f["required"]]
                record(
                    "REQUIRED_FIELDS_IDENTIFIED",
                    {"field_count": len(fields), "required": [f["name"] or f["label"] for f in required_fields]},
                    "flow-4-fields.png",
                )

                # CLIENT_VALIDATION_WORKS: type into a non-submitted field and
                # read validity state (ALLOWED_IF_NO_SUBMISSION by policy).
                validation = {"tested": False}
                if fields:
                    try:
                        probe = form_locator.locator("input[type='email'], input[type='text'], input:not([type])").first
                        if probe.count() and probe.is_visible():
                            probe.fill("flow-probe@example.invalid", timeout=_STEP_TIMEOUT_MS, no_mark=True)
                            probe.evaluate("el => el.dispatchEvent(new Event('input', {bubbles: true}))")
                            probe.evaluate("el => el.dispatchEvent(new Event('blur', {bubbles: true}))")
                            page.wait_for_timeout(150)
                            validity = probe.evaluate(
                                "el => ({valid: el.checkValidity(), message: el.validationMessage || ''})"
                            )
                            validation = {"tested": True, **validity}
                            probe.fill("", timeout=_STEP_TIMEOUT_MS, no_mark=True)
                    except Exception as exc:
                        validation = {"tested": False, "reason": str(exc)[:200]}
                record("CLIENT_VALIDATION_WORKS", validation, "flow-5-validation.png")

                # SUBMISSION_SAFE_TEST_AVAILABLE + SUCCESS_OR_CONFIRMATION_STATE
                # are PROHIBITED_WITHOUT_AUTHORIZATION: recorded as not reached
                # with explicit policy reason, never attempted.
                evidence["states"]["SUBMISSION_SAFE_TEST_AVAILABLE"] = {
                    "reached": False,
                    "reason": "PROHIBITED_WITHOUT_AUTHORIZATION",
                }
                evidence["states"]["SUCCESS_OR_CONFIRMATION_STATE"] = {
                    "reached": False,
                    "reason": "PROHIBITED_WITHOUT_AUTHORIZATION",
                }
                evidence["outcome"] = {
                    "reached_final": False,
                    "reason": "safe_test_not_authorized",
                    "form_fields": len(fields),
                    "required_fields": len(required_fields),
                }
                evidence["console_errors"] = console_errors
                evidence["finished_at"] = _now()
                return {"status": "ok", "evidence": evidence}
            finally:
                browser.close()
    except Exception as exc:
        evidence["error"] = str(exc)[:500]
        evidence["finished_at"] = _now()
        return {"status": "error", "reason": str(exc)[:300], "evidence": evidence}


def flow_findings(evidence: dict, url: str):
    """Derive deterministic findings from flow-probe evidence.

    Returns (findings, summary) where findings are low-noise, evidence-backed
    and map to the conversion fault category used elsewhere in the toolkit.
    """
    from .checks import Finding

    findings: list = []
    states = evidence.get("states", {})
    outcome = evidence.get("outcome", {})
    summary = {"states_reached": sum(1 for s in states.values() if s.get("reached")), "outcome": outcome}

    if evidence.get("status") == "error":
        findings.append(
            Finding(
                "flow-probe-failed",
                "Flow probe could not complete",
                evidence.get("reason", "unknown error"),
                "low",
                url,
                check="flow",
                confidence="observed",
                evidence_source="browser:flow probe",
                observed=str(evidence.get("error", ""))[:200],
                business_impact="Conversion path health unknown for this run.",
                remediation_action="Re-run flow probe; check browser availability.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="S",
            )
        )
        return findings, summary

    if states.get("CTA_VISIBLE", {}).get("reached") and not states.get("CTA_ACTIVATED", {}).get("reached"):
        findings.append(
            Finding(
                "flow-cta-activation-failed",
                "Primary CTA click did not navigate",
                "CTA visible but activation failed",
                "medium",
                url,
                check="flow",
                confidence="observed",
                evidence_source="browser:flow probe",
                observed=str(outcome.get("reason", "cta_click_failed")),
                business_impact="Visitors clicking the main call-to-action may hit a dead end.",
                remediation_action="Verify CTA target link/handler resolves to a working page.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="S",
            )
        )
    if outcome.get("reason") == "no_primary_cta_found":
        findings.append(
            Finding(
                "flow-no-primary-cta",
                "No primary conversion CTA found",
                "No contact/booking/quote CTA detected on landing view",
                "medium",
                url,
                check="flow",
                confidence="heuristic",
                evidence_source="browser:flow probe",
                observed="no selector from flow CTA list matched a visible element",
                business_impact="Visitors may not find the main conversion action.",
                remediation_action="Surface a visible primary CTA above the fold.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="S",
            )
        )
    if outcome.get("reason") == "no_form_or_booking_widget":
        fallback = outcome.get("conversion_fallback")
        findings.append(
            Finding(
                "flow-no-form-after-cta",
                "CTA path ends without a form or booking widget",
                "Reached CTA target but no form was reachable",
                "medium",
                url,
                check="flow",
                confidence="observed",
                evidence_source="browser:flow probe",
                observed=f"fallback path: {fallback or 'none'}",
                business_impact="Lead capture depends on a working enquiry form; absence loses enquiries.",
                remediation_action="Add a reachable enquiry/booking form on the CTA target page.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="M",
            )
        )
    return findings, summary
