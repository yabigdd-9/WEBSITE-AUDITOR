"""No-network behavioral tests for the free-only role dispatcher."""
import copy
from pathlib import Path
import unittest

import yaml
from free_role_router import RouteError, free_model, route, validate

ROOT = Path(__file__).resolve().parents[2]

# The checked-in Money Machine role policy is the router's canonical config.
_ROUTING_CONFIG = ROOT / "money-machine/config/routing.yaml"
_CONFIG_PRESENT = _ROUTING_CONFIG.is_file()
_CONFIG_ABSENT = ("BLOCKED_FIXTURE: money-machine/config/routing.yaml not "
                  "present in this environment")


@unittest.skipUnless(_CONFIG_PRESENT, _CONFIG_ABSENT)
class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load(_ROUTING_CONFIG.read_text())
        ids = {m for spec in self.config["roles"].values() for m in [spec["preferred"], *spec.get("fallbacks", [])]}
        self.catalog = {m: {"id": m, "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": ["text", "image"]}} for m in ids}
        self.calls = []

    def respond(self, path, key, body):
        self.calls.append(body)
        return 200, {"model": body["model"], "choices": [{"message": {"content": "synthetic response"},
            "finish_reason": "stop"}], "usage": {"cost": 0}}

    def test_role_specific_primary(self):
        for role, spec in self.config["roles"].items():
            result = route(self.config, role, "fixture", "fake", self.catalog, self.respond)
            self.assertEqual(result["requested_model"], spec["preferred"])
            self.assertFalse(result["approval_granted"])
        self.assertNotEqual(self.config["roles"]["RESEARCHER"]["preferred"], self.config["roles"]["PRIMARY_CODER"]["preferred"])

    def test_endpoint_429_falls_back_without_dropping_zero_caps(self):
        def flaky(path, key, body):
            if not self.calls:
                self.calls.append(body)
                return 429, {"error": {"message": "provider overloaded"}}
            return self.respond(path, key, body)
        result = route(self.config, "SECONDARY_CODER", "fixture", "fake", self.catalog, flaky)
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["requested_model"], self.config["roles"]["SECONDARY_CODER"]["fallbacks"][0])
        for call in self.calls:
            self.assertTrue(call["provider"]["require_parameters"])
            self.assertTrue(all(v == 0 for v in call["provider"]["max_price"].values()))
            self.assertNotIn("tools", call)

    def test_daily_quota_stops_instead_of_model_loop(self):
        def quota(path, key, body):
            self.calls.append(body)
            return 429, {"error": {"metadata": {"limit_source": "openrouter_free_tier_daily"}}}
        with self.assertRaisesRegex(RouteError, "Daily free quota"):
            route(self.config, "MASTER_ORCHESTRATOR", "fixture", "fake", self.catalog, quota)
        self.assertEqual(len(self.calls), 1)

    def test_paid_catalog_change_blocks_before_request(self):
        slug = self.config["roles"]["MASTER_ORCHESTRATOR"]["preferred"]
        self.catalog[slug]["pricing"]["completion"] = "0.00001"
        with self.assertRaisesRegex(RouteError, "zero cost"):
            route(self.config, "MASTER_ORCHESTRATOR", "fixture", "fake", self.catalog, self.respond)
        self.assertEqual(self.calls, [])

    def test_unknown_or_nonfree_route_rejected(self):
        with self.assertRaisesRegex(RouteError, "Unknown role"):
            route(self.config, "SEND_OUTREACH", "fixture", "fake", self.catalog, self.respond)
        self.config["roles"]["JUDGE"]["fallbacks"] = ["vendor/paid-model"]
        with self.assertRaises(RouteError):
            validate(self.config)

    def test_parameter_protection_cannot_be_disabled(self):
        self.config["policy"]["require_parameters"] = False
        with self.assertRaises(RouteError):
            validate(self.config)

    def test_vision_skips_text_only_primary(self):
        slug = self.config["roles"]["VISION"]["preferred"]
        self.catalog[slug]["architecture"]["input_modalities"] = ["text"]
        result = route(self.config, "VISION", "fixture", "fake", self.catalog, self.respond, image_data="data:image/png;base64,fixture")
        self.assertTrue(result["fallback_used"])

    def test_reasoning_alone_is_not_a_successful_answer(self):
        def empty(path, key, body):
            return 200, {"model": body["model"], "choices": [{"message": {"content": "", "reasoning": "not an answer"}}]}
        with self.assertRaisesRegex(RouteError, "All permitted"):
            route(self.config, "FINANCE_AGENT", "fixture", "fake", self.catalog, empty)

    def test_same_model_judge_not_independent(self):
        role = self.config["roles"]["JUDGE"]
        self.catalog.pop(role["preferred"])
        result = route(self.config, "JUDGE", "fixture", "fake", self.catalog, self.respond, creator_model=role["fallbacks"][0])
        self.assertFalse(result["independent_review"])
        self.assertFalse(result["approval_granted"])

    def test_reported_cost_stops(self):
        def paid(path, key, body):
            return 200, {"usage": {"cost": .01}}
        with self.assertRaisesRegex(RouteError, "Unexpected reported cost"):
            route(self.config, "MASTER_ORCHESTRATOR", "fixture", "fake", self.catalog, paid)


if __name__ == "__main__":
    unittest.main()
