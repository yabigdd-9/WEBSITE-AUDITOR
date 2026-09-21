"""Opt-in real PDF and browser review of monthly artifact delivery."""

import os
import threading
import time
import uuid
from pathlib import Path

import pytest
from test_agency_revenue_monthly import config, seed

from auditor_toolkit.monthly import generate_monthly
from auditor_toolkit.portal import create_app, setup_password

pytestmark = pytest.mark.skipif(
    os.environ.get("WA_BROWSER_E2E") != "1", reason="Opt-in real Chromium test"
)


def test_monthly_pdf_and_portal(tmp_path):
    import uvicorn
    from playwright.sync_api import sync_playwright

    root = (
        Path(os.environ["WA_MONTHLY_DEMO_ROOT"]) / uuid.uuid4().hex[:8]
        if os.environ.get("WA_MONTHLY_DEMO_ROOT")
        else tmp_path
    )
    seed(root)
    generated = generate_monthly(root, config(), "one", "2026-08")
    assert generated["status"] == "ready", generated["pdf"]
    assert Path(generated["artifacts"]["pdf"]).read_bytes().startswith(b"%PDF")
    assert generated["revenue"]["revenue_at_risk_nzd_monthly"]["high"] == "2700.00"
    setup_password(root, "monthly fixture password")
    app = create_app(root)
    uvconfig = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(uvconfig)
    sock = uvconfig.bind_socket()
    address = f"http://127.0.0.1:{sock.getsockname()[1]}"
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(address)
                page.get_by_label("Password").fill("monthly fixture password")
                page.get_by_role("button", name="Log in").click()
                page.get_by_role("link", name="Monthly report drafts").click()
                assert page.get_by_role("heading", name="Monthly report drafts").is_visible()
                with page.expect_download() as pending:
                    page.get_by_role("link", name="pdf", exact=True).click()
                assert pending.value.suggested_filename == "monthly-report.pdf"
                with page.expect_download() as pending:
                    page.get_by_role("link", name="email", exact=True).click()
                assert pending.value.suggested_filename == "email.eml"
                page.goto(address)
                page.get_by_role("button", name="Log out").click()
                response = page.request.get(
                    address + "/monthly-artifacts/" + generated["id"] + "/pdf"
                )
                assert response.status == 401
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
    print("MONTHLY_PDF=" + generated["artifacts"]["pdf"])
    print("MONTHLY_JSON=" + generated["artifacts"]["json"])
