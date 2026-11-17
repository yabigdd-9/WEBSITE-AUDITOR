"""Exercise GBP authorization, refresh and evidence using synthetic HTTP only."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from auditor_toolkit.local_seo.adapters import authorized_gbp as gbp


@pytest.fixture(autouse=True)
def isolated_auth(monkeypatch):
    monkeypatch.setattr(gbp, "_auth_config", gbp.GBPAuthConfig())
    monkeypatch.setattr(gbp, "_enabled", False)
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected HTTP request")
    monkeypatch.setattr(httpx, "get", forbidden)
    monkeypatch.setattr(httpx, "post", forbidden)


def response(data, status=200):
    return httpx.Response(status, json=data, request=httpx.Request("GET", "https://example.com"))


def authorize():
    gbp.configure_auth("synthetic-client", "synthetic-secret", "synthetic-refresh")
    assert not gbp.is_enabled()
    assert gbp.enable_gbp()


def test_auth_and_per_call_opt_in_are_both_required():
    assert not gbp.enable_gbp()
    assert gbp.list_locations("accounts/test", enable=True) == []
    assert gbp.get_location("accounts/test/locations/test", enable=True) is None
    authorize()
    assert gbp.list_locations("accounts/test") == []
    assert gbp.get_location("accounts/test/locations/test") is None
    gbp.disable_gbp()
    assert not gbp.is_enabled()
    assert gbp.list_locations("accounts/test", enable=True) == []


def test_refresh_records_new_token_and_preserves_credentials(monkeypatch):
    authorize()
    requests = []
    def post(url, **kwargs):
        requests.append((url, kwargs))
        return response({"access_token": "synthetic-access", "expires_in": 600})
    monkeypatch.setattr(httpx, "post", post)
    before = datetime.now(timezone.utc)
    assert gbp._get_access_token() == "synthetic-access"
    assert len(requests) == 1
    url, kwargs = requests[0]
    assert url == "https://oauth2.googleapis.com/token"
    assert kwargs["data"] == {
        "client_id": "synthetic-client", "client_secret": "synthetic-secret",
        "refresh_token": "synthetic-refresh", "grant_type": "refresh_token",
    }
    assert gbp._auth_config.refresh_token == "synthetic-refresh"
    assert before + timedelta(seconds=599) < datetime.fromisoformat(gbp._auth_config.token_expires_at)
    # A valid cached token must not refresh on every request.
    assert gbp._get_access_token() == "synthetic-access"
    assert len(requests) == 1


@pytest.mark.parametrize("expiry", ["2000-01-01T00:00:00+00:00", "invalid"])
def test_expired_and_invalid_expiry_refresh_the_token(monkeypatch, expiry):
    monkeypatch.setattr(gbp, "_auth_config", gbp.GBPAuthConfig(
        client_id="synthetic", refresh_token="refresh", access_token="old", token_expires_at=expiry,
    ))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: response({"access_token": "new"}))
    assert gbp._get_access_token() == "new"


def test_refresh_failure_does_not_use_a_stale_token(monkeypatch):
    authorize()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: response({}, status=401))
    assert gbp._get_access_token() is None
    assert gbp.list_locations("accounts/test", enable=True) == []
    assert gbp.get_location("accounts/test/locations/test", enable=True) is None


def test_no_refresh_without_refresh_credential(monkeypatch):
    assert gbp._refresh_access_token() is None
    monkeypatch.setattr(gbp, "_auth_config", gbp.GBPAuthConfig(client_id="synthetic", access_token="cached"))
    assert gbp._get_access_token() == "cached"


def location_payload():
    return {
        "title": "Synthetic Workshop", "storeCode": "fixture-1",
        "address": {"addressLines": ["123 Example Street", "Christchurch"]},
        "primaryPhone": "+6435550100", "websiteUri": "https://example.com",
        "latlng": {"latitude": -43.53, "longitude": 172.63},
        "primaryCategory": {"displayName": "Workshop"},
        "additionalCategories": [{"displayName": "Repairs"}, {}],
        "regularHours": {"periods": [
            {"openDay": "MONDAY", "openTime": "09:00", "closeTime": "17:00"}, {},
        ]},
        "state": "OPEN",
    }


def test_authorized_locations_preserve_source_and_stable_evidence(monkeypatch):
    authorize()
    monkeypatch.setattr(gbp, "_get_access_token", lambda: "synthetic-access")
    payload = location_payload()
    requests = []
    def get(url, **kwargs):
        requests.append((url, kwargs))
        return response({"locations": [payload]} if url.endswith("/locations") else payload)
    monkeypatch.setattr(httpx, "get", get)
    locations = gbp.list_locations("accounts/test", enable=True)
    single = gbp.get_location("accounts/test/locations/fixture-1", enable=True)
    assert len(locations) == 1
    assert single == locations[0]
    assert single.to_dict() == {
        "name": "Synthetic Workshop", "store_code": "fixture-1",
        "address": "123 Example Street, Christchurch", "phone": "+6435550100",
        "website": "https://example.com", "categories": ["Workshop", "Repairs"],
        "geo": {"latitude": -43.53, "longitude": 172.63},
        "hours": {"MONDAY": "09:00-17:00"}, "state": "OPEN",
    }
    assert single.raw == payload
    first, second = single.to_external_evidence(), locations[0].to_external_evidence()
    assert first.evidence_id == second.evidence_id
    assert first.raw_artifact_hash == second.raw_artifact_hash
    assert first.provider == "Google Business Profile"
    assert first.query == "fixture-1"
    assert first.source_confidence == 0.95
    assert datetime.fromisoformat(first.retrieved_at).tzinfo is not None
    assert [url for url, _ in requests] == [
        "https://mybusiness.googleapis.com/v4/accounts/test/locations",
        "https://mybusiness.googleapis.com/v4/accounts/test/locations/fixture-1",
    ]
    assert all(kwargs["headers"]["Authorization"] == "Bearer synthetic-access" for _, kwargs in requests)
    assert all(kwargs["timeout"] == 30 for _, kwargs in requests)


@pytest.mark.parametrize("status", [401, 429, 503])
def test_provider_errors_return_no_unverified_evidence(monkeypatch, status):
    authorize()
    monkeypatch.setattr(gbp, "_get_access_token", lambda: "synthetic-access")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: response({}, status=status))
    assert gbp.list_locations("accounts/test", enable=True) == []
    assert gbp.get_location("accounts/test/locations/test", enable=True) is None


def test_empty_location_has_no_invented_coordinates_or_categories():
    location = gbp._parse_gbp_location({})
    assert location.to_dict()["geo"] is None
    assert location.categories == []
    assert location.hours == {}
    assert location.address == ""
    named = gbp.GBPLocation(name="Synthetic", raw={"title": "Synthetic"})
    assert named.to_external_evidence().query == "Synthetic"
    changed = gbp.GBPLocation(name="Synthetic", raw={"title": "Changed"})
    assert named.to_external_evidence().evidence_id != changed.to_external_evidence().evidence_id
