"""Offline checks for the local bridge's transport boundary."""
import importlib.util
import urllib.error
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8082")
    path = Path(__file__).resolve().parents[1] / "money-machine/scripts/fcc-bridge.py"
    spec = importlib.util.spec_from_file_location("fcc_bridge_transport_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("host", ["example.com", "192.168.1.2", "0.0.0.0", "::", "127.0.0.1@remote.test"])
def test_remote_and_injected_hosts_are_rejected(bridge, host):
    with pytest.raises(ValueError):
        bridge.local_fcc_url(host, 8082)


@pytest.mark.parametrize("host,url", [
    ("127.0.0.1", "http://127.0.0.1:8082"),
    ("localhost", "http://localhost:8082"),
    ("::1", "http://[::1]:8082"),
])
def test_loopback_endpoints_preserved(bridge, host, url):
    assert bridge.local_fcc_url(host, 8082) == url


def test_redirects_cannot_forward_credentials(bridge):
    request = urllib.request.Request("http://127.0.0.1:8082/v1", headers={"Authorization": "Bearer synthetic"})
    with pytest.raises(urllib.error.HTTPError):
        bridge.NoRedirect().redirect_request(request, None, 302, "Found", {}, "http://remote.test/")


def test_local_transport_bypasses_proxies(bridge, monkeypatch):
    seen = []
    class Opener:
        def open(self, request, timeout):
            seen.append(timeout)
            return "offline"
    def build(*handlers):
        assert handlers[0].proxies == {}
        assert isinstance(handlers[1], bridge.NoRedirect)
        return Opener()
    monkeypatch.setattr(bridge.urllib.request, "build_opener", build)
    assert bridge.open_local_request(urllib.request.Request(bridge.FCC_URL), 2) == "offline"
    assert seen == [2]
