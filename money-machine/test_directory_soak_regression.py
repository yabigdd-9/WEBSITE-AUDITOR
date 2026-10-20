"""Authorized synthetic regression for the directory intake soak failure."""

from copy import deepcopy

import pytest

import mm_discovery as discovery
import mm_discovery_quality as quality


@pytest.mark.parametrize("host", [
    "yelp.com", "www.yelp.com", "m.yelp.com", "biz.yelp.com", "a.b.yelp.com",
    "M.YELP.COM", "yelp.com.", "m.yelp.com.",
])
def test_known_yelp_hosts_reject_with_versioned_evidence(host):
    candidate = {"source_url": f"https://{host}/search?cflt=plumbing", "name": host}
    original = deepcopy(candidate)
    result = quality.classify_candidate(candidate, "New Zealand")
    assert result["classification"] == quality.DIRECTORY
    assert result["disposition"] == quality.REJECT
    assert result["rule_version"] == "discovery-quality-v1.1"
    assert result["confidence"] >= 0.9
    assert result["supporting_signals"]
    assert candidate == original


@pytest.mark.parametrize("host", [
    "notyelp.com", "yelp.com.example.net", "m-yelp.com", "yelp.example", "yelp.com.au",
])
def test_hostname_lookalikes_are_not_known_yelp_directories(host):
    result = quality.classify_candidate({"url": f"https://{host}/"})
    # Preserve the existing plausible-homepage classification; identity remains unproven.
    assert result["classification"] == quality.BUSINESS_HOME
    assert result["disposition"] == quality.ACCEPT
    assert not any("known_directory_domain" in clue for clue in result["supporting_signals"])


@pytest.mark.parametrize("host", ["yellow.co.nz", "finda.co.nz", "nzs.com", "zenbu.co.nz"])
def test_existing_directory_filter_is_preserved(host):
    result = quality.classify_candidate({"url": f"https://{host}/"})
    assert result["classification"] == quality.DIRECTORY
    assert result["disposition"] == quality.REJECT


def test_saved_failure_shape_is_filtered_before_intake(monkeypatch):
    rows = [
        {"name": "m.yelp.com", "public_website": "https://m.yelp.com/",
         "source_url": "https://m.yelp.com/search?cflt=plumbing&find_loc=Christchurch",
         "source": "searxng-local:synthetic"},
        {"name": "Fixture Plumbing", "public_website": "https://fixtureplumbing.co.nz/",
         "source_url": "https://fixtureplumbing.co.nz/"},
        {"name": "Novel source", "public_website": "https://new-source.example/",
         "source_url": "https://new-source.example/unusual"},
    ]
    original = deepcopy(rows)
    calls = []

    def search(*args):
        calls.append(args)
        return rows

    monkeypatch.setattr(discovery, "searxng_candidates", search)
    accepted, summary, rejected = discovery._collect_search_source(
        "plumber Christchurch", "New Zealand", "http://127.0.0.1:8888", 10)
    assert calls == [("plumber Christchurch", "New Zealand", "http://127.0.0.1:8888", 10)]
    assert len(accepted) == 2
    assert summary["quality_rejected"] == 1
    assert summary["quality_review"] == 1
    assert summary["quality_rule_version"] == "discovery-quality-v1.1"
    assert rejected[0]["classification"] == quality.DIRECTORY
    assert rejected[0]["rule_version"] == summary["quality_rule_version"]
    assert all(row["discovery_quality"]["rule_version"] == summary["quality_rule_version"]
               for row in accepted)
    assert accepted[1]["discovery_quality"]["disposition"] == quality.REVIEW
    assert rows == original


def test_summary_version_comes_from_classifier(monkeypatch):
    monkeypatch.setattr(quality, "RULE_VERSION", "synthetic-version-for-provenance")
    monkeypatch.setattr(discovery, "searxng_candidates", lambda *args: [
        {"source_url": "https://m.yelp.com/"},
        {"source_url": "https://fixtureplumbing.co.nz/", "name": "Fixture Plumbing"},
    ])
    accepted, summary, rejected = discovery._collect_search_source(
        "synthetic", "New Zealand", "http://127.0.0.1:8888", 2)
    assert summary["quality_rule_version"] == quality.RULE_VERSION
    assert rejected[0]["rule_version"] == quality.RULE_VERSION
    assert accepted[0]["discovery_quality"]["rule_version"] == quality.RULE_VERSION


def test_filtered_yelp_result_never_becomes_an_intake_job(monkeypatch):
    from test_discovery_batch import db

    monkeypatch.setattr(discovery, "searxng_candidates", lambda *args: [
        {"name": "m.yelp.com", "public_website": "https://m.yelp.com/",
         "source_url": "https://m.yelp.com/search?cflt=plumbing"},
        {"name": "Fixture Plumbing", "public_website": "https://fixtureplumbing.co.nz/",
         "source_url": "https://fixtureplumbing.co.nz/"},
    ])
    collected = discovery.collect_multi_source(queries=["synthetic plumbing"], region="New Zealand")
    assert len(collected["candidates"]) == 1
    database = db()  # Fresh synthetic in-memory schema; execution guards prohibit file databases.
    try:
        intake = discovery.ingest(database, collected["candidates"])
        assert len(intake["inserted"]) == 1
        assert database.execute("SELECT count(*) FROM businesses WHERE public_website LIKE '%yelp%'").fetchone()[0] == 0
        assert database.execute("SELECT count(*) FROM pipeline_items").fetchone()[0] == 1
        assert database.execute("SELECT state FROM pipeline_items").fetchone()[0] == "DISCOVERED"
    finally:
        database.close()
