import io
import json
import socket
from unittest.mock import MagicMock

import pytest

from auditor_toolkit import fetch_chain as fetch
from auditor_toolkit.monitoring.watchdog import Watchdog

URL = "https://example.test/"


@pytest.fixture
def public_dns(monkeypatch):
    def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


def test_fetch_sidecar_and_plain_fallback(monkeypatch, public_dns):
    monkeypatch.setenv("LIGHTPANDA_URL", "https://fixture.test/")
    def reply(request, timeout):
        assert timeout == 15
        if request.full_url == "https://fixture.test/fetch":
            assert json.loads(request.data) == {"url": URL}
            return io.BytesIO(b'{"html": "<main>Sidecar</main>"}')
        assert request.full_url == URL
        return io.BytesIO(b"<main>Plain response</main>")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", reply)
    assert fetch.fetch_chain(URL, ("l1",))["html"] == "<main>Sidecar</main>"
    monkeypatch.delenv("LIGHTPANDA_URL")
    monkeypatch.delenv("CRAWL4AI_URL", raising=False)
    result = fetch.fetch_chain(URL, ("l1", "l3"))
    assert result["tier"] == "l3"
    assert result["html"] == "<main>Plain response</main>"
    assert result["errors"][0]["tier"] == "l1"


def test_fetch_browser_closes_after_navigation(monkeypatch, public_dns):
    playwright = pytest.importorskip("playwright.sync_api")
    session = MagicMock()
    browser = session.__enter__.return_value.chromium.launch.return_value
    page = browser.new_page.return_value
    page.content.return_value = "<main>Browser response</main>"
    monkeypatch.setattr(playwright, "sync_playwright", lambda: session)
    assert fetch.fetch_chain(URL, ("l2",))["html"] == "<main>Browser response</main>"
    page.goto.assert_called_once_with(URL, wait_until="domcontentloaded", timeout=20000)
    browser.close.assert_called_once()


def test_fetch_reports_unresolvable_host(monkeypatch):
    def fail(*args, **kwargs):
        raise socket.gaierror("fixture DNS unavailable")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    with pytest.raises(RuntimeError, match="Could not resolve host"):
        fetch.fetch_chain(URL, ("l3",))


def test_watchdog_returns_delivery_result_without_real_network(tmp_path, monkeypatch, public_dns):
    watchdog = Watchdog(snapshot_dir=tmp_path, webhook_url=URL)
    watchdog.take_snapshot("example.test", [{"defect_key": "missing-title"}])
    response = MagicMock()
    response.__enter__.return_value.status = 204
    open_url = MagicMock(return_value=response)
    monkeypatch.setattr("urllib.request.urlopen", open_url)
    assert watchdog.send_alert("example.test", ["missing-title"]) == {"status": "sent", "code": 204}
    request = open_url.call_args.args[0]
    assert request.full_url == URL
    assert "missing-title" in json.loads(request.data)["text"]
    open_url.side_effect = OSError("fixture offline")
    assert watchdog.send_alert("example.test", ["missing-title"])["status"] == "failed"
