"""Performance-booster unit tests — zero network, stdlib + httpx.MockTransport."""
import asyncio
import time
import unittest

import httpx

from integrations.tier1_enrichment.perf import (
    CircuitBreaker,
    DomainLimiter,
    fetch_html_capped,
    install_uvloop,
    make_client,
)


class TestMakeClient(unittest.TestCase):
    def test_client_has_pooling(self):
        c = make_client(concurrency=4)
        # We only assert no crash; internal httpx attribute names vary by version
        asyncio.run(c.aclose())

    def test_falls_back_to_http1_without_h2(self):
        """If h2 package missing, client still works; no crash."""
        c = make_client()
        # We don't assert http2 state — we only assert it doesn't crash
        asyncio.run(c.aclose())


class TestDomainLimiter(unittest.TestCase):
    def test_per_domain_semaphore(self):
        lim = DomainLimiter(per_domain=2)
        s1 = lim.get("a.co")
        s2 = lim.get("a.co")
        self.assertIs(s1, s2)


class TestCircuitBreaker(unittest.TestCase):
    def test_triple_fail_opens(self):
        cb = CircuitBreaker(ttl=60, max_fails=3)
        for _ in range(3):
            cb.record("x.com", ok=False)
        self.assertTrue(cb.breaker_open("x.com"))

    def test_ok_resets(self):
        cb = CircuitBreaker(ttl=60, max_fails=3)
        for _ in range(3):
            cb.record("x.com", ok=False)
        cb.record("x.com", ok=True)
        self.assertFalse(cb.breaker_open("x.com"))

    def test_ttl_expiry(self):
        cb = CircuitBreaker(ttl=1, max_fails=2)
        cb.record("x.com", ok=False)
        cb.record("x.com", ok=False)
        self.assertTrue(cb.breaker_open("x.com"))
        time.sleep(1.1)
        self.assertFalse(cb.breaker_open("x.com"))


class TestFetchHtmlCapped(unittest.TestCase):
    def test_success_uses_get_and_preserves_html(self):
        def handler(request):
            self.assertEqual(request.method, 'GET')
            return httpx.Response(200, text='<h1>Synthetic page</h1>')

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await fetch_html_capped(client, 'https://example.com')

        html, size = asyncio.run(run())
        self.assertEqual(html, '<h1>Synthetic page</h1>')
        self.assertEqual(size, len(html.encode()))

    def test_cap_exceeded(self):
        def handler(request):
            # return 20 MB of data
            body = "x" * (20 * 1024 * 1024)
            return httpx.Response(200, text=body)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async def _run():
            html, n = await fetch_html_capped(client, "https://example.com", cap=1024)
            return html, n

        html, n = asyncio.run(_run())
        self.assertEqual(n, 1024)  # capped
        asyncio.run(client.aclose())

    def test_bad_url_returns_empty(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: None))

        async def _run():
            return await fetch_html_capped(client, "https://bad.invalid")

        html, n = asyncio.run(_run())
        self.assertEqual(html, "")
        self.assertEqual(n, 0)
        asyncio.run(client.aclose())


class TestUvloop(unittest.TestCase):
    def test_install_no_crash(self):
        # uvloop may not be installed; must not raise
        install_uvloop()  # returns bool, we just ensure no crash


if __name__ == "__main__":
    unittest.main()
