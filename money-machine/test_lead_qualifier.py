"""Unit tests for mm_lead_qualifier and mm_lead_qualify modules."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import mm_lead_qualifier as q
import mm_lead_qualify as q2
import unittest


class LeadQualifierUnit(unittest.TestCase):
    def test_normalize_industry_construction_aliases(self):
        self.assertEqual(q.normalize_industry("Construction"), "construction")
        self.assertEqual(q.normalize_industry("Building"), "construction")
        self.assertEqual(q.normalize_industry("Renovations"), "construction")
        self.assertEqual(q.normalize_industry("Contractor"), "construction")

    def test_normalize_industry_services_aliases(self):
        self.assertEqual(q.normalize_industry("Plumbing"), "plumbing")
        self.assertEqual(q.normalize_industry("Plumber"), "plumbing")
        self.assertEqual(q.normalize_industry("Electrical"), "electrical")
        self.assertEqual(q.normalize_industry("Electrician"), "electrical")
        self.assertEqual(q.normalize_industry("HVAC"), "hvac")
        self.assertEqual(q.normalize_industry("Heat Pump"), "hvac")
        self.assertEqual(q.normalize_industry("Climate Control"), "hvac")

    def test_normalize_industry_tech_aliases(self):
        self.assertEqual(q.normalize_industry("SaaS"), "saas")
        self.assertEqual(q.normalize_industry("Software"), "software")
        self.assertEqual(q.normalize_industry("Web Development"), "software")
        self.assertEqual(q.normalize_industry("Technology"), "tech")
        self.assertEqual(q.normalize_industry("Digital Agency"), "tech")

    def test_normalize_industry_default(self):
        self.assertEqual(q.normalize_industry("Unknown Industry"), "default")
        self.assertEqual(q.normalize_industry(""), "default")
        self.assertEqual(q.normalize_industry(None), "default")

    def test_detect_job_signals_high(self):
        text = "We are hiring! Multiple job openings for plumbers and electricians. Join our growing team."
        result = q.detect_job_signals(text)
        self.assertEqual(result["strength"], "high")
        self.assertGreaterEqual(result["score"], 3)
        self.assertTrue(len(result["snippets"]) > 0)

    def test_detect_job_signals_medium(self):
        text = "Our team is expanding. New staff members welcome."
        result = q.detect_job_signals(text)
        self.assertIn(result["strength"], ("medium", "high"))
        self.assertGreaterEqual(result["score"], 1)

    def test_detect_job_signals_none(self):
        text = "Welcome to our website. We provide quality services."
        result = q.detect_job_signals(text)
        self.assertEqual(result["strength"], "none")
        self.assertEqual(result["score"], 0)

    def test_detect_budget_signals_high(self):
        text = "Budget: $50,000 allocated for this project. Investment range $100k-$200k."
        result = q.detect_budget_signals(text)
        self.assertEqual(result["strength"], "high")
        self.assertGreaterEqual(result["score"], 3)
        self.assertTrue(len(result["amounts"]) > 0)

    def test_detect_budget_signals_medium(self):
        text = "Contact us for a quote and pricing information."
        result = q.detect_budget_signals(text)
        self.assertIn(result["strength"], ("medium", "high"))
        self.assertGreaterEqual(result["score"], 1)

    def test_detect_budget_signals_none(self):
        text = "We provide excellent service. Contact us today."
        result = q.detect_budget_signals(text)
        self.assertEqual(result["strength"], "none")
        self.assertEqual(result["score"], 0)

    def test_industry_freshness_days(self):
        self.assertEqual(q.industry_freshness_days("construction"), 14)
        self.assertEqual(q.industry_freshness_days("plumbing"), 14)
        self.assertEqual(q.industry_freshness_days("saas"), 3)
        self.assertEqual(q.industry_freshness_days("tech"), 3)
        self.assertEqual(q.industry_freshness_days("retail"), 7)
        self.assertEqual(q.industry_freshness_days("unknown"), 7)

    def test_industry_weight_multipliers(self):
        mult = q.industry_weight_multipliers("construction")
        self.assertEqual(mult.get("ability_to_pay"), 1.5)
        self.assertEqual(mult.get("urgency"), 1.2)
        self.assertEqual(mult.get("decision_access"), 1.1)

        mult = q.industry_weight_multipliers("saas")
        self.assertEqual(mult.get("pain"), 1.2)
        self.assertEqual(mult.get("fit"), 1.3)
        self.assertEqual(mult.get("demoability"), 1.3)

    def test_industry_offer_matches(self):
        self.assertEqual(q.industry_offer_matches("construction"), ("quoting", "booking", "follow_up"))
        self.assertEqual(q.industry_offer_matches("saas"), ("lead_capture", "crm", "reporting"))
        self.assertEqual(q.industry_offer_matches("retail"), ("lead_capture", "booking", "crm"))
        self.assertEqual(q.industry_offer_matches("unknown"), ("lead_capture", "follow_up", "crm"))

    def test_qualify_lead_hot_construction(self):
        text = "We are hiring plumbers! $75,000 budget for new projects. Expanding our team in Auckland."
        result = q2.qualify_lead(text, industry="plumbing")
        self.assertEqual(result["tier"], "HOT")
        self.assertGreaterEqual(result["qualification_score"], 80)
        self.assertIn("High-confidence hiring/expansion signal detected", result["reasons"])
        self.assertIn("High-confidence budget/investment signal detected", result["reasons"])

    def test_qualify_lead_warm_saas(self):
        text = "We're growing. Multiple positions open. Budget $25k for new tools."
        result = q2.qualify_lead(text, industry="saas")
        self.assertIn(result["tier"], ("WARM", "HOT"))
        self.assertGreaterEqual(result["qualification_score"], 55)

    def test_qualify_lead_cold(self):
        text = "Welcome to our company. We provide services."
        result = q2.qualify_lead(text, industry="unknown")
        self.assertEqual(result["tier"], "COLD")
        self.assertLess(result["qualification_score"], 30)

    def test_qualify_lead_with_extra_signals(self):
        text = "We provide construction services."
        extra = {'recent_job_post': True, 'budget_mentioned': True, 'positive_engagement': True}
        result = q2.qualify_lead(text, industry="construction", extra_signals=extra)
        self.assertIn(result["tier"], ("WARM", "HOT"))
        self.assertGreaterEqual(result["qualification_score"], 55)
        self.assertIn("Recent job posting observed (operator signal)", result["reasons"])

    def test_hot_lead_reasons(self):
        hot_lead = {"tier": "HOT", "reasons": ["Reason 1", "Reason 2", "Reason 3", "Reason 4"]}
        self.assertEqual(q2.hot_lead_reasons(hot_lead), ["Reason 1", "Reason 2", "Reason 3"])

        warm_lead = {"tier": "WARM", "reasons": ["Reason 1"]}
        self.assertEqual(q2.hot_lead_reasons(warm_lead), [])

    def test_export_qualification_config(self):
        config = q2.export_qualification_config()
        self.assertIn("industry_freshness_days", config)
        self.assertIn("industry_weight_multipliers", config)
        self.assertIn("industry_offer_matches", config)
        self.assertIn("job_signal_keywords", config)
        self.assertIn("budget_signal_keywords", config)


if __name__ == "__main__":
    unittest.main()
