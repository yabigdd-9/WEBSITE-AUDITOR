import socket

import httpx
import pytest

from auditor_core.assets import audit_image_urls, discover_image_urls


def test_discover_image_urls_handles_src_and_srcset():
    html = """
    <img src="/hero.jpg" srcset="/hero-2x.jpg 2x, https://cdn.example/image.webp 3x">
    <picture><source srcset="/wide.webp 1200w"></picture>
    <img src="data:image/png;base64,AAAA">
    """
    urls = discover_image_urls(html, "https://example.co.nz/")
    assert urls == [
        "https://example.co.nz/hero.jpg",
        "https://example.co.nz/hero-2x.jpg",
        "https://cdn.example/image.webp",
        "https://example.co.nz/wide.webp",
    ]


@pytest.mark.asyncio
async def test_broken_image_audit_records_http_errors(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/broken.jpg":
            return httpx.Response(404)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        defects, evidence = await audit_image_urls(
            session,
            ["https://example.co.nz/good.jpg", "https://example.co.nz/broken.jpg"],
            user_agent="WebsiteAuditor",
        )
    assert defects[0]["defect"] == "1 broken image(s)"
    assert evidence["broken"][0]["status"] == 404
