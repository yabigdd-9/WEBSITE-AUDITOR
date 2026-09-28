#!/usr/bin/env python3
"""Pytest tests for mm_search_backend.py.

All network calls are mocked — no real HTTP requests are made.
Verifies:
  1. query() returns candidate dicts with required keys
  2. SearchBlocked is raised when SearXNG is unreachable
  3. SSRF filtering rejects non-loopback endpoints
  4. JSON response parsing handles various formats
  5. Zero external sends are recorded
  6. Candidates are deduplicated by canonical_host
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from mm_search_backend import query, SearchBlocked, status, EXTERNAL_SENDS


def _make_mock_urlopen(data):
    """Return a mock callable for urlopen that yields the JSON-encoded data
    through the context-manager protocol used by mm_discovery.searxng_candidates.
    """
    body = json.dumps(data).encode("utf-8")
    response = MagicMock()
    response.read.return_value = body
    # urlopen(...) returns response; `with urlopen(...) as resp` calls .__enter__()
    urlopen_mock = MagicMock()
    urlopen_mock.return_value.__enter__ = MagicMock(return_value=response)
    urlopen_mock.return_value.__exit__ = MagicMock(return_value=False)
    return urlopen_mock


def test_query_returns_candidate_dicts_with_required_keys():
    """Test that query() returns candidate dicts with required keys."""
    mock_data = {
        "results": [
            {"url": "https://example.com", "title": "Example Website"}
        ]
    }
    with patch('mm_discovery.urlopen', new=_make_mock_urlopen(mock_data)):
        candidates = query("test query", "nz")
        assert len(candidates) == 1
        candidate = candidates[0]
        assert "canonical_host" in candidate
        assert "name" in candidate
        assert "region" in candidate
        assert "public_website" in candidate
        assert "source" in candidate
        assert candidate["canonical_host"] == "example.com"


def test_query_raises_searchblocked_when_unreachable():
    """Test that SearchBlocked is raised when endpoint is unreachable."""
    from urllib.error import URLError
    with patch('mm_discovery.urlopen', side_effect=URLError("Connection refused")):
        with pytest.raises(SearchBlocked) as exc_info:
            query("test query", "nz")
        assert "BLOCKED_SEARCH" in str(exc_info.value)


def test_query_ssrf_filtering_rejects_non_loopback():
    """Test that SSRF filtering rejects non-loopback endpoints."""
    with pytest.raises(ValueError, match="loopback"):
        query("test", "nz", endpoint="http://evil.com:8888")
    with pytest.raises(ValueError, match="loopback"):
        query("test", "nz", endpoint="https://127.0.0.1:8888")  # https not allowed


def test_query_ssrf_filtering_rejects_internal_ips_in_results():
    """Test that internal IP URLs in results are filtered out."""
    mock_data = {
        "results": [
            {"url": "http://127.0.0.1:8080/internal", "title": "Internal Server"},
            {"url": "https://192.168.1.1/admin", "title": "Local Network"},
            {"url": "https://example.com/public", "title": "Public Site"},
        ]
    }
    with patch('mm_discovery.urlopen', new=_make_mock_urlopen(mock_data)):
        candidates = query("test query", "nz")
        # Only the public site should survive
        assert len(candidates) == 1
        assert candidates[0]["canonical_host"] == "example.com"


def test_query_json_response_parsing_handles_various_formats():
    """Test that JSON response parsing handles various formats."""
    # Empty results
    with patch('mm_discovery.urlopen', new=_make_mock_urlopen({"results": []})):
        candidates = query("test", "nz")
        assert candidates == []

    # Malformed result (non-dict entry): searxng_candidates uses `break` on non-dict,
    # so placing it after a valid entry means only valid entries before are returned.
    mock_data = {"results": [{"url": "https://example.com/valid", "title": "Valid"}, "not-a-dict"]}
    with patch('mm_discovery.urlopen', new=_make_mock_urlopen(mock_data)):
        candidates = query("test", "nz")
        assert len(candidates) == 1
        assert candidates[0]["canonical_host"] == "example.com"

    # Missing url field
    mock_data = {"results": [{"title": "No URL Here"}]}
    with patch('mm_discovery.urlopen', new=_make_mock_urlopen(mock_data)):
        candidates = query("test", "nz")
        assert candidates == []


def test_query_zero_external_sends():
    """Test that query() records zero external sends."""
    mock_data = {"results": [{"url": "https://example.com", "title": "Example"}]}
    with patch('mm_discovery.urlopen', new=_make_mock_urlopen(mock_data)):
        query("test query", "nz")
        assert EXTERNAL_SENDS == 0


def test_query_candidates_are_deduplicated():
    """Test that candidates are deduplicated by canonical_host."""
    mock_data = {
        "results": [
            {"url": "https://example.com/page1", "title": "Page 1"},
            {"url": "https://example.com/page2", "title": "Page 2"},  # Same host
            {"url": "https://example.com:8080/page3", "title": "Page 3"},  # Same host w/ port
            {"url": "https://www.example.com/page4", "title": "WWW"},  # www stripped
            {"url": "https://different.com/page5", "title": "Different"},
        ]
    }
    with patch('mm_discovery.urlopen', new=_make_mock_urlopen(mock_data)):
        candidates = query("test query", "nz", limit=10)
        hosts = [c["canonical_host"] for c in candidates]
        # All hosts must be unique
        assert len(hosts) == len(set(hosts))
        assert "example.com" in hosts
        assert "different.com" in hosts
        # Only 2 unique hosts after dedup (www.example.com strips to example.com)
        assert len(candidates) == 2


def test_status_returns_dict_with_reachable_key():
    """Test that status() returns a dict with 'reachable' key."""
    mock_data = {"results": [{"url": "https://example.com", "title": "Example"}]}
    with patch('mm_discovery.urlopen', new=_make_mock_urlopen(mock_data)):
        result = status("http://127.0.0.1:8888")
        assert "reachable" in result
        assert result["reachable"] is True
        assert result["external_sends"] == 0
