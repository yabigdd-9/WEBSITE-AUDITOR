"""Enrichment contract tests: additive-only merge, fail-closed sources."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from integrations.tier1_enrichment import cache as cache_mod
from integrations.tier1_enrichment import enrich as enrich_mod
from integrations.tier1_enrichment.enrich import enrich_async


class EnrichCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._patcher = patch.object(cache_mod, "CACHE_DIR", Path(self._tmp))
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def run_async(self, coro):
        return asyncio.run(coro)


class TestEnrichAsync(EnrichCase):
    def test_headers_only_needs_no_network(self):
        out = self.run_async(enrich_async("https://example.com", {},
                                          include=("headers",)))
        self.assertEqual(out["security_headers"]["grade"], "F")
        self.assertEqual(set(out), {"security_headers", "keyed_sources_configured"})

    def test_failing_source_fails_closed(self):
        async def boom(url, client, cache):
            raise ConnectionError("dns blew up")

        with patch.object(enrich_mod, "check_w3c", boom):
            out = self.run_async(enrich_async("https://example.com", {},
                                              include=("w3c",)))
        self.assertEqual(out["w3c"]["status"], "skipped")
        self.assertIn("ConnectionError", out["w3c"]["reason"])

    def test_keyed_source_flags_report_key_status(self):
        out = self.run_async(enrich_async("https://example.com", {},
                                          include=("headers",)))
        self.assertIn("pagespeed", out["keyed_sources_configured"])
        self.assertIn("ranknibbler", out["keyed_sources_configured"])


class TestEnrichAuditMerge(EnrichCase):
    def test_merge_is_additive(self):
        audit = {"url": "https://example.com", "domain": "example.com",
                 "defects": [{"defect": "Missing H1 tag", "impact": "x"}],
                 "defect_count": 1, "score": 12}
        out = enrich_mod.enrich_audit(dict(audit), {},
                                      include=("headers",))  # no network
        self.assertEqual(out["domain"], "example.com")
        self.assertIn("enrichment", out)
        self.assertGreaterEqual(out["defect_count"], 1)
        self.assertTrue(any("Strict-Transport" in d.get("defect", "")
                            or "strict-transport" in d.get("defect", "")
                            for d in out["defects"]))

    def test_enrich_audit_inside_running_loop(self):
        """Regression: --enrich calls enrich_audit from a running loop."""
        async def _run():
            return enrich_mod.enrich_audit(
                {"url": "https://example.com", "defects": []},
                {}, include=("headers",))  # no network

        out = self.run_async(_run())
        self.assertIn("enrichment", out)
        self.assertEqual(out["enrichment"]["security_headers"]["grade"], "F")

    def test_unreachable_everything_still_returns_audit(self):
        def handler(request):
            raise httpx.ConnectError("nope")

        async def _run():
            async with httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)) as client:
                from integrations.tier1_enrichment.sources import check_w3c
                return await check_w3c("https://example.com", client,
                                       cache_mod.EnrichmentCache())

        out = self.run_async(_run())
        self.assertEqual(out["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
