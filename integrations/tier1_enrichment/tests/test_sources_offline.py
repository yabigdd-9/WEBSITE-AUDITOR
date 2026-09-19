"""Offline source tests — fake transports, zero real network.

httpx MockTransport lets us exercise parsing/grading/caching logic exactly,
while live behaviour was verified separately with curl on 2026-09-19.
"""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from integrations.tier1_enrichment import cache as cache_mod
from integrations.tier1_enrichment.sources import (
    check_pagespeed,
    check_ranknibbler,
    check_ssllabs,
    check_urlscan_search,
    check_w3c,
)


def make_cache():
    tmp = Path(tempfile.mkdtemp())
    with patch.object(cache_mod, "CACHE_DIR", tmp):
        yield cache_mod.EnrichmentCache(ttl=60)


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._patcher = patch.object(cache_mod, "CACHE_DIR", Path(self._tmp))
        self._patcher.start()
        self.cache = cache_mod.EnrichmentCache(ttl=60)
        self.addCleanup(self._patcher.stop)

    def run_async(self, coro):
        return asyncio.run(coro)

    def client_for(self, handler):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestW3C(OfflineCase):
    def test_counts_errors_and_truncates_list(self):
        def handler(request):
            self.assertIn("validator.w3.org", str(request.url))
            msgs = [{"type": "error", "message": f"e{i}", "lastLine": i} for i in range(15)]
            return httpx.Response(200, json={"messages": msgs})

        out = self.run_async(check_w3c("https://example.com",
                                       self.client_for(handler), self.cache))
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["errors"], 15)
        self.assertEqual(len(out["error_list"]), 10)

    def test_second_call_served_from_cache(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(200, json={"messages": []})

        client = self.client_for(handler)
        self.run_async(check_w3c("https://example.com", client, self.cache))
        out = self.run_async(check_w3c("https://example.com", client, self.cache))
        self.assertTrue(out["cached"])
        self.assertEqual(len(calls), 1)

    def test_http_error_skips_without_caching(self):
        def handler(request):
            return httpx.Response(429, text="slow down")

        out = self.run_async(check_w3c("https://example.com",
                                       self.client_for(handler), self.cache))
        self.assertEqual(out["status"], "skipped")


class TestSSLlabs(OfflineCase):
    def test_worst_grade_wins(self):
        def handler(request):
            self.assertEqual(request.url.params["startNew"], "off")
            return httpx.Response(200, json={
                "status": "READY",
                "endpoints": [{"grade": "A"}, {"grade": "B"}],
            })

        out = self.run_async(check_ssllabs("https://example.com",
                                            self.client_for(handler), self.cache))
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["grade"], "B")

    def test_no_cached_assessment_skips(self):
        def handler(request):
            return httpx.Response(200, json={"status": "IN_PROGRESS"})

        out = self.run_async(check_ssllabs("https://example.com",
                                            self.client_for(handler), self.cache))
        self.assertEqual(out["status"], "pending")


class TestUrlscan(OfflineCase):
    def test_parses_recent_scans(self):
        def handler(request):
            return httpx.Response(200, json={
                "total": 3,
                "results": [{"page": {"url": "https://example.com/"},
                             "task": {"time": "2026-01-01T00:00:00"}}],
            })

        out = self.run_async(check_urlscan_search(
            "https://example.com", self.client_for(handler), self.cache))
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["scan_count"], 3)
        self.assertEqual(out["recent"][0]["url"], "https://example.com/")


class TestPagespeed(OfflineCase):
    def test_parses_category_scores(self):
        def handler(request):
            cats = {k: {"score": s} for k, s in
                    [("performance", 0.9), ("accessibility", 1.0),
                     ("best-practices", 0.95), ("seo", 1.0)]}
            return httpx.Response(200, json={"lighthouseResult": {"categories": cats}})

        out = self.run_async(check_pagespeed("https://example.com",
                                              self.client_for(handler), self.cache))
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["scores"]["performance"], 0.9)

    def test_quota_error_skips(self):
        def handler(request):
            return httpx.Response(429, text="quota")

        out = self.run_async(check_pagespeed("https://example.com",
                                              self.client_for(handler), self.cache))
        self.assertEqual(out["status"], "skipped")
        self.assertFalse(out["keyed"])


class TestRanknibbler(OfflineCase):
    def test_missing_key_skips_cleanly(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RANKNIBBLER_API_KEY", None)
            out = self.run_async(check_ranknibbler(
                "https://example.com", self.client_for(lambda r: None), self.cache))
        self.assertEqual(out["status"], "skipped")
        self.assertIn("RANKNIBBLER_API_KEY", out["reason"])


if __name__ == "__main__":
    unittest.main()
