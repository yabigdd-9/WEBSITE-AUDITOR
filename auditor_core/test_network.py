import asyncio
import socket

import pytest

from auditor_core.network import NetworkSafetyError, ensure_public_url, normalize_http_url


def test_normalize_rejects_non_http_scheme():
    with pytest.raises(NetworkSafetyError):
        normalize_http_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_literal_private_ip_is_blocked():
    with pytest.raises(NetworkSafetyError):
        await ensure_public_url("http://127.0.0.1/")


@pytest.mark.asyncio
async def test_localhost_is_blocked():
    with pytest.raises(NetworkSafetyError):
        await ensure_public_url("http://localhost/")


@pytest.mark.asyncio
async def test_hostname_resolving_private_ip_is_blocked(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(NetworkSafetyError):
        await ensure_public_url("https://example.invalid/")


@pytest.mark.asyncio
async def test_hostname_resolving_public_ip_is_allowed(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    value = await ensure_public_url("https://example.invalid/path#fragment")
    assert value == "https://example.invalid/path"
