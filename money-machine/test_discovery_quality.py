"""Tests for deterministic v45 discovery quality classification.

Synthetic-only. No network, no model calls, no database writes, no sends.
"""
import unittest
from unittest.mock import patch

import mm_discovery
import mm_discovery_quality as q


class DiscoveryQualityClassifier(unittest.TestCase):

    def test_nz_business_homepage_accepts(self):
        result = q.classify_candidate({
            "name": "Smith Plumbing",
            "source_url": "https://smithplumbing.co.nz/",
            "region": "Canterbury",
        })
        self.assertEqual(result["classification"], q.BUSINESS_HOME)
        self.assertEqual(result["disposition"], q.ACCEPT)
        self.assertIn("nz_domain", result["supporting_signals"])

    def test_business_service_page_accepts(self):
        result = q.classify_candidate({
            "name": "Fixture Electrical",
            "source_url": "https://fixtureelectrical.co.nz/services/heat-pumps",
            "region": "Canterbury",
        })
        self.assertEqual(result["classification"], q.BUSINESS_SERVICE_PAGE)
        self.assertEqual(result["disposition"], q.ACCEPT)

    def test_known_directory_rejects(self):
        result = q.classify_candidate({
            "source_url": "https://yellow.co.nz/christchurch/plumbers",
            "region": "Canterbury",
        })
        self.assertEqual(result["classification"], q.DIRECTORY)
        self.assertEqual(result["disposition"], q.REJECT)
        self.assertGreaterEqual(result["confidence"], 0.9)

    def test_social_profile_rejects(self):
        result = q.classify_candidate({
            "source_url": "https://www.facebook.com/fixtureplumbing",
        })
        self.assertEqual(result["classification"], q.SOCIAL_PROFILE)
        self.assertEqual(result["disposition"], q.REJECT)

    def test_marketplace_rejects(self):
        result = q.classify_candidate({
            "source_url": "https://www.trademe.co.nz/a/services/trades/plumbing",
        })
        self.assertEqual(result["classification"], q.MARKETPLACE)
        self.assertEqual(result["disposition"], q.REJECT)

    def test_news_site_rejects(self):
        result = q.classify_candidate({
            "source_url": "https://www.stuff.co.nz/business/example-story",
        })
        self.assertEqual(result["classification"], q.NEWS)
        self.assertEqual(result["disposition"], q.REJECT)

    def test_government_registry_is_specific(self):
        result = q.classify_candidate({
            "source_url": "https://companies-register.companiesoffice.govt.nz/company/123",
        })
        self.assertEqual(result["classification"], q.REGISTRY)
        self.assertEqual(result["disposition"], q.REJECT)

    def test_generic_government_rejects(self):
        result = q.classify_candidate({
            "source_url": "https://www.business.govt.nz/getting-started/",
        })
        self.assertEqual(result["classification"], q.GOVERNMENT)
        self.assertEqual(result["disposition"], q.REJECT)

    def test_job_board_rejects(self):
        result = q.classify_candidate({
            "source_url": "https://www.seek.co.nz/job/12345",
        })
        self.assertEqual(result["classification"], q.JOB_BOARD)
        self.assertEqual(result["disposition"], q.REJECT)

    def test_document_rejects(self):
        result = q.classify_candidate({
            "source_url": "https://fixture.co.nz/brochure.pdf",
        })
        self.assertEqual(result["classification"], q.DOCUMENT)
        self.assertEqual(result["disposition"], q.REJECT)

    def test_ambiguous_result_is_review_not_reject(self):
        result = q.classify_candidate({
            "source_url": "https://unknown.example.xyz/about/something",
            "region": "New Zealand",
        })
        self.assertEqual(result["classification"], q.UNKNOWN)
        self.assertEqual(result["disposition"], q.REVIEW)

    def test_directory_like_unknown_domain_is_review_below_reject_threshold(self):
        result = q.classify_candidate({
            "source_url": "https://some-new-source.co.nz/businesses/christchurch",
        })
        self.assertEqual(result["classification"], q.AGGREGATOR)
        self.assertEqual(result["disposition"], q.REVIEW)
        self.assertLess(result["confidence"], 0.9)

    def test_filter_keeps_review_cases_and_filters_only_confident_junk(self):
        batch = q.filter_candidates([
            {"source_url": "https://goodplumber.co.nz/", "name": "Good Plumber"},
            {"source_url": "https://yellow.co.nz/christchurch/plumbers"},
            {"source_url": "https://new-source.xyz/unusual"},
        ], "Canterbury")

        self.assertEqual(batch["counts"], {"accepted": 2, "rejected": 1, "review": 1})
        self.assertEqual(batch["rejected"][0]["classification"], q.DIRECTORY)
        self.assertEqual(
            batch["accepted"][0]["discovery_quality"]["classification"],
            q.BUSINESS_HOME,
        )
        self.assertEqual(
            batch["accepted"][1]["discovery_quality"]["disposition"],
            q.REVIEW,
        )
        self.assertEqual(batch["paid_calls"], 0)
        self.assertEqual(batch["external_sends"], 0)

    def test_invalid_non_object_fails_closed_in_filter(self):
        batch = q.filter_candidates(["not-an-object"])
        self.assertEqual(batch["counts"]["rejected"], 1)
        self.assertEqual(batch["rejected"][0]["reason"], "candidate_not_object")

    def test_batch_search_wrapper_filters_junk_without_network(self):
        rows = [
            {
                "name": "goodplumber.co.nz",
                "public_website": "https://goodplumber.co.nz/",
                "source_url": "https://goodplumber.co.nz/",
                "source": "searxng-local:test",
            },
            {
                "name": "yellow.co.nz",
                "public_website": "https://yellow.co.nz/",
                "source_url": "https://yellow.co.nz/christchurch/plumbers",
                "source": "searxng-local:test",
            },
            {
                "name": "unknown-source.xyz",
                "public_website": "https://unknown-source.xyz/",
                "source_url": "https://unknown-source.xyz/unusual",
                "source": "searxng-local:test",
            },
        ]
        with patch.object(mm_discovery, "searxng_candidates", return_value=rows):
            accepted, report, rejected = mm_discovery._collect_search_source(
                "plumber christchurch",
                "Canterbury",
                "http://127.0.0.1:8888",
                10,
            )

        self.assertEqual(len(accepted), 2)
        self.assertEqual(report["quality_rejected"], 1)
        self.assertEqual(report["quality_review"], 1)
        self.assertEqual(rejected[0]["classification"], q.DIRECTORY)
        self.assertIn("discovery_quality", accepted[0])
        self.assertIn("discovery_quality", accepted[1])

    def test_normalization_preserves_quality_provenance(self):
        quality = q.classify_candidate({
            "name": "Fixture Plumbing",
            "source_url": "https://fixtureplumbing.co.nz/",
            "region": "Canterbury",
        })
        candidate = mm_discovery.normalize_candidate({
            "name": "Fixture Plumbing",
            "website": "https://fixtureplumbing.co.nz/",
            "region": "Canterbury",
            "source": "fixture",
            "discovery_quality": quality,
        })
        self.assertEqual(
            candidate["discovery_quality"]["rule_version"],
            "discovery-quality-v1",
        )
        self.assertEqual(
            candidate["discovery_quality"]["classification"],
            q.BUSINESS_HOME,
        )


if __name__ == "__main__":
    unittest.main()
