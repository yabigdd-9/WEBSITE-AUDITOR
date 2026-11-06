"""No sockets or DNS: exercise the real HTTPX/HTTPCore connection boundary."""
import socket
import ssl

import httpcore
import pytest

from auditor_toolkit.common import Fetcher, PublicHTTPTransport, PublicNetworkBackend


class RecordingStream(httpcore.MockStream):
    def __init__(self, owner, response):
        super().__init__([response])
        self.owner = owner

    def write(self, buffer, timeout=None):
        self.owner.writes.append(bytes(buffer))

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.owner.sni.append(server_hostname)
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert ssl_context.check_hostname
        return self


class RecordingBackend:
    def __init__(self, responses=None):
        self.targets, self.writes, self.sni = [], [], []
        self.responses = list(responses or [b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok'])

    def connect_tcp(self, host, port, **kwargs):
        self.targets.append((host, port))
        return RecordingStream(self, self.responses.pop(0))


def addresses(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, 443))]


def test_dns_rebind_after_initial_validation_is_blocked_before_connect(monkeypatch):
    resolutions = iter(['93.184.216.34', '127.0.0.1'])
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: addresses(next(resolutions)))
    raw = RecordingBackend()
    fetcher = Fetcher(transport=PublicHTTPTransport(PublicNetworkBackend(raw)), min_interval=0)
    try:
        with pytest.raises(ValueError, match='non-global'):
            fetcher.get('https://controlled.example/')
        assert raw.targets == []
    finally:
        fetcher.close()


def test_connection_is_numeric_and_preserves_original_host_and_tls_name(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: addresses('93.184.216.34'))
    raw = RecordingBackend()
    fetcher = Fetcher(transport=PublicHTTPTransport(PublicNetworkBackend(raw)), min_interval=0)
    try:
        response = fetcher.get('https://public.example/path')
        assert response.text == 'ok'
        assert str(response.url) == 'https://public.example/path'
        assert raw.targets == [('93.184.216.34', 443)]
        assert raw.sni == ['public.example']
        assert b'Host: public.example\r\n' in b''.join(raw.writes)
    finally:
        fetcher.close()


def test_redirect_rebinding_is_also_blocked(monkeypatch):
    resolutions = iter(['93.184.216.34'] * 3 + ['169.254.169.254'])
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: addresses(next(resolutions)))
    raw = RecordingBackend([b'HTTP/1.1 302 Found\r\nLocation: https://redirect.example/metadata\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'])
    fetcher = Fetcher(transport=PublicHTTPTransport(PublicNetworkBackend(raw)), min_interval=0)
    try:
        with pytest.raises(ValueError, match='non-global'):
            fetcher.get('https://public.example/')
        assert raw.targets == [('93.184.216.34', 443)]
    finally:
        fetcher.close()


def test_default_public_fetcher_installs_connection_guard():
    fetcher = Fetcher()
    try:
        assert isinstance(fetcher.client._transport, PublicHTTPTransport)
    finally:
        fetcher.close()


@pytest.mark.parametrize('ip', ['10.0.0.1', '127.0.0.1', '169.254.169.254', '192.168.1.1', '::1', 'fc00::1'])
def test_non_global_connection_targets_are_rejected(monkeypatch, ip):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: addresses(ip))
    raw = RecordingBackend()
    with pytest.raises(ValueError):
        PublicNetworkBackend(raw).connect_tcp('controlled.example', 443)
    assert raw.targets == []
