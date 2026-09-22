"""Opt-in real Chromium flow-probe e2e against a local fixture server.

Run with WA_BROWSER_E2E=1. The fixture serves a landing page with a contact
CTA that navigates to a form page with required fields and HTML5 validation —
exercising LANDING → CTA_VISIBLE → CTA_ACTIVATED → FORM_OR_BOOKING_REACHED →
REQUIRED_FIELDS_IDENTIFIED → CLIENT_VALIDATION_WORKS. Submission states stay
PROHIBITED_WITHOUT_AUTHORIZATION.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from auditor_toolkit.flows import run_flow_probe

pytestmark = pytest.mark.skipif(
    os.environ.get("WA_BROWSER_E2E") != "1",
    reason="Set WA_BROWSER_E2E=1 for real local Chromium flow-probe test",
)

LANDING_HTML = (
    b"<!doctype html><html lang='en'><head><title>Flow fixture</title></head><body>"
    b"<main><h1>Flow fixture</h1>"
    b"<a id='cta' href='/contact'>Contact us</a></main></body></html>"
)

FORM_HTML = (
    b"<!doctype html><html lang='en'><head><title>Contact</title></head><body>"
    b"<main><h1>Contact</h1>"
    b"<form id='enquiry' action='#' method='get'>"
    b"<label for='name'>Name</label><input id='name' name='name' required>"
    b"<label for='email'>Email</label><input id='email' name='email' type='email' required>"
    b"<label for='message'>Message</label><textarea id='message' name='message'></textarea>"
    b"<button type='submit'>Send</button>"
    b"</form></main></body></html>"
)


class FlowFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = LANDING_HTML if self.path == "/" else FORM_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_real_browser_flow_probe_full_traversal(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FlowFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        result = run_flow_probe(url, tmp_path, enabled=True, allow_private=True)
        assert result["status"] == "ok", result
        evidence = result["evidence"]
        states = evidence["states"]
        # The deterministic FSM reached every allowed state in order.
        for state in (
            "LANDING",
            "CTA_VISIBLE",
            "CTA_ACTIVATED",
            "FORM_OR_BOOKING_REACHED",
            "REQUIRED_FIELDS_IDENTIFIED",
            "CLIENT_VALIDATION_WORKS",
        ):
            assert states[state]["reached"], state
        # Submission states are explicitly withheld by the safe-action policy.
        assert states["SUBMISSION_SAFE_TEST_AVAILABLE"]["reached"] is False
        assert (
            states["SUBMISSION_SAFE_TEST_AVAILABLE"]["reason"] == "PROHIBITED_WITHOUT_AUTHORIZATION"
        )
        assert evidence["outcome"]["reason"] == "safe_test_not_authorized"
        assert evidence["outcome"]["form_fields"] == 3
        assert evidence["outcome"]["required_fields"] == 2
        # Step screenshots exist on disk with hashes.
        step_shots = [s for s in evidence["steps"] if "screenshot" in s]
        assert len(step_shots) >= 4
        from pathlib import Path

        for step in step_shots:
            assert Path(step["screenshot"]["path"]).stat().st_size > 0
            assert len(step["screenshot"]["sha256"]) == 64
        # Console error capture is present.
        assert "console_errors" in evidence
    finally:
        server.shutdown()


def test_real_browser_flow_probe_no_cta_page(tmp_path):
    """A page with no CTA ends cleanly with no_primary_cta_found."""

    class NoCtaHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<!doctype html><html><head><title>No CTA</title></head><body><p>Nothing here</p></body></html>"
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), NoCtaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        result = run_flow_probe(url, tmp_path, enabled=True, allow_private=True)
        assert result["status"] == "ok"
        evidence = result["evidence"]
        assert evidence["outcome"]["reason"] == "no_primary_cta_found"
        assert evidence["states"]["LANDING"]["reached"]
        assert not evidence["states"].get("CTA_VISIBLE", {}).get("reached")
        # Derive findings exactly as the pipeline would.
        from auditor_toolkit.flows import flow_findings

        findings, _ = flow_findings(evidence, url)
        assert [f.defect_key for f in findings] == ["flow-no-primary-cta"]
    finally:
        server.shutdown()
