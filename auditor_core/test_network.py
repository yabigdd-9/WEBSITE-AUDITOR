import asyncio
import socket

import httpx
import pytest

from auditor_core.network import (
    NetworkSafetyError,
    ResponseTooLarge,
    SafeFetcher,
    ensure_public_url,
    normalize_http_url,
)


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


@pytest.mark.asyncio
async def test_redirect_to_private_ip_is_blocked(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "public.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        raise AssertionError(f"unexpected host: {host}")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "public.example"
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        fetcher = SafeFetcher(session)
        with pytest.raises(NetworkSafetyError):
            await fetcher.get_text("https://public.example/")


@pytest.mark.asyncio
async def test_response_body_limit_is_enforced(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 128)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        fetcher = SafeFetcher(session, max_body_bytes=64)
        with pytest.raises(ResponseTooLarge):
            await fetcher.get_text("https://public.example/")


@pytest.mark.asyncio
async def test_public_redirect_chain_is_recorded(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(301, headers={"Location": "/home"})
        return httpx.Response(200, content=b"ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        result = await SafeFetcher(session).get_text("https://public.example/")
        assert result.final_url == "https://public.example/home"
        assert result.text == "ok"
        assert [item["status"] for item in result.redirect_chain] == [301, 200]
