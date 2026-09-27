import socket

import httpcore
import httpx
import pytest

from auditor_toolkit.common import Fetcher, _PinnedSyncBackend, validate_url

PUBLIC_V4 = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))


def test_validate_url_keeps_its_string_return_contract_and_strips_fragments(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [PUBLIC_V4])

    result = validate_url("https://example.com/page#section")

    assert result == "https://example.com/page"
    assert isinstance(result, str)


def test_validate_url_rejects_a_host_with_any_non_global_answer(monkeypatch):
    private_v4 = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: [PUBLIC_V4, private_v4]
    )

    with pytest.raises(ValueError, match="non-global"):
        validate_url("https://example.com")


def test_pinned_backend_connects_to_the_validated_ip(monkeypatch):
    calls = []

    def fake_connect(self, **kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect)
    backend = _PinnedSyncBackend("93.184.216.34")

    stream = backend.connect_tcp(
        host="example.com",
        port=443,
        timeout=4,
        local_address=None,
        socket_options=None,
    )

    assert stream is not None
    assert calls[0]["host"] == "93.184.216.34"
    assert calls[0]["port"] == 443
    assert calls[0]["timeout"] == 4


def test_pinned_backend_refuses_non_global_addresses():
    with pytest.raises(ValueError, match="globally routable"):
        _PinnedSyncBackend("127.0.0.1")


def test_injected_mock_transport_remains_in_use(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [PUBLIC_V4])
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text="fixture", request=request)

    fetcher = Fetcher(transport=httpx.MockTransport(handler), min_interval=0)
    try:
        response = fetcher.get("https://example.com/fixture")
    finally:
        fetcher.close()

    assert response.status_code == 200
    assert requests[0].url.host == "example.com"
