import json
from urllib.error import URLError

import pytest

import mm_search_backend as search


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, n=-1):
        return self.body


@pytest.fixture
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(search.core, "root", lambda: tmp_path)
    return tmp_path


def test_loopback_invariant_is_enforced():
    with pytest.raises(ValueError):
        search._endpoint("https://127.0.0.1:8888")
    with pytest.raises(ValueError):
        search._endpoint("http://example.com:8888")


def test_credentials_in_endpoint_are_rejected():
    with pytest.raises(ValueError):
        search._endpoint("http://user:pass@127.0.0.1:8888")


def test_probe_reports_not_listening_as_typed_state(monkeypatch, isolated_state):
    def fail(*args, **kwargs):
        raise URLError(ConnectionRefusedError())
    monkeypatch.setattr(search, "urlopen", fail)
    result = search.probe()
    assert result["state"] == search.BLOCKED_NOT_LISTENING
    assert result["ok"] is False


def test_probe_reports_html_response_as_json_disabled(monkeypatch, isolated_state):
    monkeypatch.setattr(search, "urlopen", lambda *a, **k: FakeResponse(b"<html>no json</html>"))
    result = search.probe()
    assert result["state"] == search.BLOCKED_NOT_JSON
    assert result["json_api_enabled"] is False


def test_probe_rejects_oversized_response(monkeypatch, isolated_state):
    monkeypatch.setattr(
        search,
        "urlopen",
        lambda *a, **k: FakeResponse(b"x" * (search.MAX_RESPONSE + 1)),
    )
    result = search.probe()
    assert result["state"] == search.BLOCKED_TOO_LARGE


def test_probe_rejects_invalid_json_document(monkeypatch, isolated_state):
    monkeypatch.setattr(
        search,
        "urlopen",
        lambda *a, **k: FakeResponse(json.dumps({"nope": 1}).encode()),
    )
    result = search.probe()
    assert result["state"] == search.BLOCKED_INVALID_JSON


def test_ok_probe_counts_results(monkeypatch, isolated_state):
    body = json.dumps({"results": [{"url": "https://example.co.nz"}]}).encode()
    monkeypatch.setattr(search, "urlopen", lambda *a, **k: FakeResponse(body))
    result = search.probe()
    assert result["state"] == search.OK
    assert result["result_count"] == 1


def test_cache_hit_avoids_second_request(monkeypatch, isolated_state):
    calls = {"n": 0}

    def ok(*args, **kwargs):
        calls["n"] += 1
        body = json.dumps({
            "results": [
                {
                    "title": "Example",
                    "url": "https://example.co.nz",
                    "content": "business",
                    "engines": ["google"],
                    "score": 1.0,
                }
            ]
        }).encode()
        return FakeResponse(body)

    monkeypatch.setattr(search, "urlopen", ok)
    first = search.search("plumber", "Christchurch", cache_hours=24)
    second = search.search("plumber", "Christchurch", cache_hours=24)
    assert first["state"] == search.OK
    assert second["cache"] == "hit"
    assert calls["n"] == 1


def test_cache_expiry_forces_refetch(monkeypatch, isolated_state):
    monkeypatch.setattr(search.time, "time", lambda: 100000.0)
    endpoint, _ = search._endpoint("http://127.0.0.1:8888")
    params = {
        "q": "plumber Christchurch",
        "format": "json",
        "categories": "general",
        "safesearch": "1",
        "language": "en",
    }
    key = search.cache_key(endpoint, "plumber", "Christchurch", {"limit": 20, **params})
    cache_path = search._cache_dir() / (key + ".json")
    cache_path.write_text(json.dumps({
        "cached_at": 100000.0 - 25 * 3600,
        "payload": {"results": [{"url": "https://old.example"}]},
    }))
    calls = {"n": 0}

    def ok(*args, **kwargs):
        calls["n"] += 1
        return FakeResponse(json.dumps({"results": [{"url": "https://fresh.example"}]}).encode())

    monkeypatch.setattr(search, "urlopen", ok)
    result = search.search("plumber", "Christchurch", cache_hours=24)
    assert result["state"] == search.OK
    assert result["results"][0]["url"] == "https://fresh.example"
    assert calls["n"] == 1


def test_replay_uses_cache_without_network(monkeypatch, isolated_state):
    monkeypatch.setattr(
        search,
        "urlopen",
        lambda *a, **k: FakeResponse(
            json.dumps({"results": [{"url": "https://cached.example"}]}).encode()
        ),
    )
    search.search("roofer", "Canterbury", cache_hours=24)

    def should_not_run(*args, **kwargs):
        raise AssertionError("network should not be used")
    monkeypatch.setattr(search, "urlopen", should_not_run)

    result = search.search("roofer", "Canterbury", cache_hours=24, use_network=False)
    assert result["state"] == search.OK
    assert result["cache"] == "hit"


def test_breaker_opens_after_repeated_failures(monkeypatch, isolated_state):
    monkeypatch.setenv("MM_SEARCH_BREAKER_FAILS", "2")
    monkeypatch.setenv("MM_SEARCH_BREAKER_COOLDOWN", "300")
    monkeypatch.setattr(search.time, "time", lambda: 1000.0)

    def fail(*args, **kwargs):
        raise URLError(ConnectionRefusedError())
    monkeypatch.setattr(search, "urlopen", fail)

    one = search.search("builder", "Auckland", cache_hours=0)
    two = search.search("builder", "Auckland", cache_hours=0)
    three = search.search("builder", "Auckland", cache_hours=0)
    assert one["state"] == search.BLOCKED_NOT_LISTENING
    assert two["state"] == search.BLOCKED_NOT_LISTENING
    assert three["state"] == search.BLOCKED_CIRCUIT_OPEN


def test_provider_output_has_no_contact_or_send_authority(monkeypatch, isolated_state):
    body = json.dumps({
        "results": [{
            "title": "Business",
            "url": "https://example.co.nz",
            "content": "hello",
            "email": "should-not-pass-through@example.co.nz",
            "recipient": "person@example.co.nz",
        }]
    }).encode()
    monkeypatch.setattr(search, "urlopen", lambda *a, **k: FakeResponse(body))
    result = search.search("electrician", "Wellington", cache_hours=0)
    encoded = json.dumps(result).lower()
    assert '"email"' not in encoded
    assert '"recipient"' not in encoded
    assert "external_send" not in encoded
