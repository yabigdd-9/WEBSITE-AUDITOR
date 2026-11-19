"""Desktop/mobile owner workflow against synthetic records and loopback only."""

import hashlib
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from auditor_toolkit.portal import create_app, setup_password
from scripts import cloud_opportunities as opportunities
from scripts.pipeline_store import PipelineStore
from scripts.report_archive import EncryptedReportArchive, import_ciphertext
from toolkit_tests.test_report_archive import envelope

pytestmark = pytest.mark.skipif(
    os.environ.get("WA_BROWSER_E2E") != "1", reason="Set WA_BROWSER_E2E=1 for local Chromium"
)
PASSWORD = "synthetic-browser-owner-password"
DOMAIN = "example.com"


def seed_records(root):
    store = PipelineStore(root / "pipeline.sqlite3")
    identity = hashlib.sha256(DOMAIN.encode()).hexdigest()
    audit_id = hashlib.sha256(b"browser-synthetic-audit").hexdigest()
    now = datetime.now(timezone.utc)
    with store.transaction(bootstrap=True) as state:
        state["prospects"][identity] = dict(
            domain=DOMAIN, status="complete", draft="INTERNAL SCOPE DRAFT - DO NOT SEND",
            discovery={"business_name": "Synthetic Christchurch Services <script>fixture</script>"},
            audit=dict(
                domain=DOMAIN, status="COMPLETE", run_id="browser-fixture",
                timestamp=now.isoformat(), findings=[dict(
                    finding_id="finding-1", defect_key="viewport", severity="medium",
                    confidence="observed", observed="Observed synthetic missing viewport",
                    remediation_action="Review viewport", source_url="https://example.com",
                    evidence_ref="html", evidence_check="html", evidence_check_status="ok",
                )],
            ),
        )
        state["audit_runs"] = [dict(
            audit_id=audit_id, prospect_id=identity, status="complete",
            canonical_run_id="browser-fixture", execution_timestamp=now.isoformat(),
        )]
        opportunities.enrich(
            state, opportunities.load_policy(Path(__file__).resolve().parents[1]),
            now=now.timestamp(),
        )
    archive_root = root / "sealed"
    archive_root.mkdir(mode=0o700)
    data = envelope()
    source = root / "synthetic.enc.json"
    source.write_bytes(data)
    artifact_id = import_ciphertext(
        store, EncryptedReportArchive(archive_root), source,
        expected_sha256=hashlib.sha256(data).hexdigest(), audit_ids=[audit_id],
        source_run_id="123", source_artifact_id="456", created_at=now.isoformat(),
        source_expires_at=(now + timedelta(days=30)).isoformat(),
        retain_until=(now + timedelta(days=60)).isoformat(), owner_reviewed=True,
        actor="synthetic-fixture-owner", reason="Synthetic ciphertext association", now=now.timestamp(),
    )
    return store, identity, archive_root, artifact_id


@pytest.fixture
def dashboard_server():
    import uvicorn

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store, identity, archive_root, artifact_id = seed_records(root)
        history = root / "history"
        setup_password(history, PASSWORD)
        app = create_app(history, pipeline_db=store.path, report_archive_root=archive_root)
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        server = uvicorn.Server(config)
        sock = config.bind_socket()
        address = f"http://127.0.0.1:{sock.getsockname()[1]}"
        worker = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and worker.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started, "Local fixture server did not start"
            yield address, store, identity, artifact_id
        finally:
            server.should_exit = True
            worker.join(10)
            sock.close()


def assert_fits_viewport(page):
    sizes = page.evaluate("({content: document.documentElement.scrollWidth, viewport: innerWidth})")
    assert sizes["viewport"] == page.viewport_size["width"]
    assert sizes["content"] <= sizes["viewport"] + 1


def review_pages(page, address, store, identity):
    before = store.read()
    headings = {
        "/pipeline": "Pipeline overview", "/pipeline/prospects": "Prospects",
        f"/pipeline/prospects/{identity}": DOMAIN, "/pipeline/discovery": "Discovery review",
        "/pipeline/reports": "Encrypted audit reports", "/pipeline/outreach": "Outreach review",
        "/pipeline/projects": "Client projects", "/pipeline/health": "System health",
    }
    for path, title in headings.items():
        response = page.goto(address + path)
        assert response.status == 200
        assert response.headers["cache-control"] == "no-store"
        assert "script-src 'none'" in response.headers["content-security-policy"]
        assert page.get_by_role("heading", name=title, exact=True).is_visible()
        assert_fits_viewport(page)
    assert store.read() == before


def approve_and_accept(page, address, store, identity):
    from playwright.sync_api import expect

    page.goto(address + f"/pipeline/prospects/{identity}")
    expect(page.get_by_text("Pricing not configured", exact=False)).to_be_visible()
    assert page.locator("script").count() == 0
    page.get_by_label("Review reason").fill("Synthetic scope reviewed in browser")
    page.get_by_role("button", name="Approve internal proposal", exact=True).click()
    expect(page.get_by_role("heading", name="Record customer acceptance")).to_be_visible()
    saved = store.read()["prospects"][identity]
    assert saved["approvals"][-1]["version_sha256"] == saved["proposal_version"]
    assert saved["approvals"][-1]["decision"] == "approved"
    assert saved.get("outreach_events", []) == []
    assert saved.get("projects", {}) == {}
    page.get_by_label("Acceptance evidence SHA-256").fill("a" * 64)
    page.get_by_label("Acceptance note").fill("Synthetic accepted proposal fixture only")
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name="Create project record", exact=True).click()
    expect(page.get_by_role("heading", name="Client projects", exact=True)).to_be_visible()
    projects = store.read()["prospects"][identity]["projects"]
    assert len(projects) == 1
    project = next(iter(projects.values()))
    assert project["automated_changes"] == 0
    assert project["automatic_invoicing"] is False
    assert_fits_viewport(page)


@pytest.mark.parametrize("viewport", [
    {"width": 1440, "height": 1000}, {"width": 390, "height": 844},
], ids=["desktop", "mobile"])
def test_owner_pipeline_in_real_browser(dashboard_server, viewport):
    from playwright.sync_api import sync_playwright

    address, store, identity, artifact_id = dashboard_server
    with sync_playwright() as playwright:
        options = {"headless": True}
        executable = os.environ.get("WA_E2E_CHROMIUM_EXECUTABLE")
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(
            viewport=viewport, is_mobile=viewport["width"] < 500,
            has_touch=viewport["width"] < 500, accept_downloads=True,
        )
        blocked = []

        def local_only(route):
            if route.request.url.startswith(address + "/"):
                route.continue_()
            else:
                blocked.append(route.request.url)
                route.abort()

        context.route("**/*", local_only)
        try:
            page = context.new_page()
            unauthenticated = page.goto(address + "/pipeline")
            assert unauthenticated.status == 401
            page.goto(address + "/login")
            assert_fits_viewport(page)
            page.get_by_label("Password").fill(PASSWORD)
            page.get_by_role("button", name="Log in", exact=True).click()
            page.wait_for_url(address + "/")
            review_pages(page, address, store, identity)
            page.goto(address + "/pipeline/prospects")
            page.get_by_label("Search business or domain").fill(DOMAIN)
            page.get_by_role("button", name="Search", exact=True).click()
            page.get_by_role("link", name=DOMAIN, exact=True).click()
            assert page.url == address + f"/pipeline/prospects/{identity}"
            page.get_by_role("link", name="Review linked encrypted audit reports").click()
            with page.expect_download() as downloaded:
                page.get_by_role("link", name="Download encrypted report", exact=True).click()
            assert downloaded.value.suggested_filename == artifact_id + ".enc.json"
            assert Path(downloaded.value.path()).read_bytes() == envelope()
            approve_and_accept(page, address, store, identity)
            page.goto(address + "/")
            page.get_by_role("button", name="Log out", exact=True).click()
            page.wait_for_url("**/login")
            response = page.goto(address + "/pipeline/reports")
            assert response.status == 401
            assert blocked == []
        finally:
            context.close()
            browser.close()
