"""Zero-network tests of the opt-in Google Business Profile integration.

Synthetic credentials are never sent to Google. All HTTP calls are mocked;
the adapter is required to fail closed without explicit authorization/opt-in.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from auditor_toolkit.local_seo.adapters import authorized_gbp as gbp


def example_location():
    return {
        "title": "Sample NZ Trades",
        "storeCode": "NZ-EXAMPLE-001",
        "address": {"addressLines": ["42 Example Road", "Christchurch 8011"]},
        "primaryPhone": "+6430000000",
        "websiteUri": "https://example.co.nz",
        "primaryCategory": {"displayName": "Plumber"},
        "additionalCategories": [{"displayName": "Contractor"}, {"displayName": ""}],
        "latlng": {"latitude": -43.53, "longitude": 172.63},
        "regularHours": {"periods": [
            {"openDay": "MONDAY", "openTime": "09:00", "closeTime": "17:00"},
            {"openDay": "", "openTime": "09:00", "closeTime": "17:00"},
        ]},
        "state": "OPEN",
    }


def fake_response(payload):
    response = Mock()
    response.json.return_value = payload
    return response


class TestGBPOAuthFailClosed(unittest.TestCase):
    def setUp(self):
        previous = (gbp._auth_config, gbp._enabled)
        self.addCleanup(lambda: setattr(gbp, "_auth_config", previous[0]))
        self.addCleanup(lambda: setattr(gbp, "_enabled", previous[1]))
        gbp.configure_auth()
        gbp.disable_gbp()

    def test_default_is_disabled_and_never_fetches_without_credentials(self):
        with patch("httpx.get", side_effect=AssertionError("No external request allowed")):
            self.assertFalse(gbp.is_enabled())
            self.assertFalse(gbp.enable_gbp())
            self.assertEqual(gbp.list_locations("accounts/test", enable=True), [])
            self.assertIsNone(gbp.get_location("accounts/test/locations/1", enable=True))

    def test_auth_configuration_does_not_enable_api_calls(self):
        gbp.configure_auth("client", "synthetic-secret", "synthetic-refresh-token")
        self.assertTrue(gbp._auth_config.is_configured)
        self.assertFalse(gbp.is_enabled())
        with patch("httpx.get", side_effect=AssertionError("Explicit enable required")):
            self.assertEqual(gbp.list_locations("accounts/test", enable=True), [])
            self.assertIsNone(gbp.get_location("accounts/test/locations/1", enable=True))

    def test_opt_in_and_per_call_enable_both_required(self):
        gbp.configure_auth("client", "synthetic-secret", "synthetic-refresh-token")
        self.assertTrue(gbp.enable_gbp())
        self.assertTrue(gbp.is_enabled())
        with patch("httpx.get", side_effect=AssertionError("Per-call enable required")):
            self.assertEqual(gbp.list_locations("accounts/test"), [])
            self.assertIsNone(gbp.get_location("accounts/test/locations/1"))
        gbp.disable_gbp()
        self.assertFalse(gbp.is_enabled())

    def test_client_id_and_token_required(self):
        gbp.configure_auth("", "synthetic-secret", "synthetic-refresh-token")
        self.assertFalse(gbp.enable_gbp())
        gbp.configure_auth("client", "secret", "")
        self.assertFalse(gbp.enable_gbp())

    def test_refresh_without_refresh_token_cannot_make_request(self):
        gbp.configure_auth("client", "secret", "")
        with patch("httpx.post", side_effect=AssertionError("No refresh token")):
            self.assertIsNone(gbp._refresh_access_token())

    def test_failed_refresh_never_uses_empty_token(self):
        gbp.configure_auth("client", "synthetic-secret", "synthetic-refresh-token")
        with patch("httpx.post", side_effect=RuntimeError("mock offline HTTP failure")):
            self.assertIsNone(gbp._refresh_access_token())
        self.assertEqual(gbp._auth_config.access_token, "")

    def test_refresh_creates_fresh_expiring_token_with_explicit_grant(self):
        gbp.configure_auth("client", "synthetic-secret", "synthetic-refresh-token")
        with patch("httpx.post", return_value=fake_response({
            "access_token": "synthetic-access-token",
            "expires_in": 900,
        })) as outbound:
            self.assertEqual(gbp._refresh_access_token(), "synthetic-access-token")
        outbound.assert_called_once()
        self.assertEqual(outbound.call_args.args[0], gbp._TOKEN_ENDPOINT)
        self.assertEqual(outbound.call_args.kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(
            outbound.call_args.kwargs["data"]["refresh_token"], "synthetic-refresh-token"
        )
        self.assertEqual(gbp._auth_config.access_token, "synthetic-access-token")
        self.assertGreater(
            datetime.fromisoformat(gbp._auth_config.token_expires_at),
            datetime.now(timezone.utc),
        )

    def test_valid_cached_access_token_never_refreshes(self):
        gbp._auth_config = gbp.GBPAuthConfig(
            client_id="client",
            access_token="synthetic-cached-token",
            token_expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        )
        with patch.object(gbp, "_refresh_access_token", side_effect=AssertionError("No refresh")):
            self.assertEqual(gbp._get_access_token(), "synthetic-cached-token")

    def test_expired_and_malformed_expiry_both_refresh(self):
        for expires in [
            (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "not-a-timestamp",
        ]:
            with self.subTest(expires=expires):
                gbp._auth_config = gbp.GBPAuthConfig(
                    client_id="client",
                    refresh_token="synthetic-refresh-token",
                    access_token="synthetic-old-token",
                    token_expires_at=expires,
                )
                with patch.object(gbp, "_refresh_access_token", return_value="new") as refresh:
                    self.assertEqual(gbp._get_access_token(), "new")
                refresh.assert_called_once()

    def test_no_cached_access_token_refreshes(self):
        gbp.configure_auth("client", "secret", "synthetic-refresh-token")
        with patch.object(gbp, "_refresh_access_token", return_value="new") as refresh:
            self.assertEqual(gbp._get_access_token(), "new")
        refresh.assert_called_once()


class TestGBPLocationsOffline(unittest.TestCase):
    def setUp(self):
        previous = (gbp._auth_config, gbp._enabled)
        self.addCleanup(lambda: setattr(gbp, "_auth_config", previous[0]))
        self.addCleanup(lambda: setattr(gbp, "_enabled", previous[1]))
        gbp.configure_auth("client", "synthetic-secret", "synthetic-refresh-token")
        self.assertTrue(gbp.enable_gbp())

    def test_no_access_token_returns_without_api_call(self):
        with patch.object(gbp, "_get_access_token", return_value=None):
            with patch("httpx.get", side_effect=AssertionError("No token, no request")):
                self.assertEqual(gbp.list_locations("accounts/test", enable=True), [])
                self.assertIsNone(gbp.get_location("accounts/test/locations/1", enable=True))

    def test_list_locations_maps_only_mock_google_results(self):
        with patch.object(gbp, "_get_access_token", return_value="synthetic-access-token"):
            with patch("httpx.get", return_value=fake_response({
                "locations": [example_location()],
            })) as request:
                locations = gbp.list_locations("accounts/test", enable=True)
        self.assertEqual(len(locations), 1)
        self.assertIsInstance(locations[0], gbp.GBPLocation)
        self.assertEqual(locations[0].name, "Sample NZ Trades")
        self.assertEqual(locations[0].geo.latitude, -43.53)
        self.assertEqual(locations[0].categories, ["Plumber", "Contractor"])
        self.assertEqual(locations[0].hours, {"MONDAY": "09:00-17:00"})
        self.assertEqual(
            request.call_args.args[0], "https://mybusiness.googleapis.com/v4/accounts/test/locations"
        )
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"], "Bearer synthetic-access-token"
        )
        self.assertEqual(request.call_args.kwargs["timeout"], 30)

    def test_get_single_location_uses_bearer_token_and_parser(self):
        with patch.object(gbp, "_get_access_token", return_value="synthetic-access-token"):
            with patch("httpx.get", return_value=fake_response(example_location())) as request:
                location = gbp.get_location("accounts/test/locations/12", enable=True)
        self.assertEqual(location.store_code, "NZ-EXAMPLE-001")
        self.assertEqual(request.call_args.args[0], (
            "https://mybusiness.googleapis.com/v4/accounts/test/locations/12"
        ))

    def test_get_and_list_errors_return_no_results_not_partial_evidence(self):
        with patch.object(gbp, "_get_access_token", return_value="synthetic-access-token"):
            with patch("httpx.get", side_effect=RuntimeError("mock network failure")):
                self.assertEqual(gbp.list_locations("accounts/test", enable=True), [])
                self.assertIsNone(gbp.get_location("accounts/test/locations/12", enable=True))

    def test_parser_handles_no_optional_fields_without_faking_coordinates(self):
        empty = gbp._parse_gbp_location({"title": "Anonymous"})
        self.assertIsNone(empty.geo)
        self.assertEqual(empty.categories, [])
        self.assertEqual(empty.hours, {})
        self.assertEqual(empty.to_dict()["geo"], None)
        self.assertEqual(empty.to_dict()["name"], "Anonymous")

    def test_evidence_has_stable_content_hash_and_source_provenance(self):
        parsed = gbp._parse_gbp_location(example_location())
        evidence_a = parsed.to_external_evidence()
        evidence_b = parsed.to_external_evidence()
        self.assertEqual(evidence_a.provider, "Google Business Profile")
        self.assertEqual(evidence_a.source_confidence, 0.95)
        self.assertEqual(evidence_a.evidence_id, evidence_b.evidence_id)
        self.assertEqual(evidence_a.raw_artifact_hash, evidence_b.raw_artifact_hash)
        self.assertEqual(evidence_a.query, "NZ-EXAMPLE-001")
        self.assertEqual(evidence_a.name, "Sample NZ Trades")
        self.assertEqual(evidence_a.freshness, "OPEN")
        self.assertEqual(evidence_a.geo.longitude, 172.63)


if __name__ == "__main__":
    unittest.main()
