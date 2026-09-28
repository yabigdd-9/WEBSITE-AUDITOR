"""Regression coverage for bounded, multi-lane discovery intake."""
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
MM_DIR = ROOT / "money-machine"
if str(MM_DIR) not in sys.path:
    sys.path.insert(0, str(MM_DIR))

import mm_discovery as discovery


def db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.executescript("""
        CREATE TABLE businesses(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, region TEXT,
          public_website TEXT, source TEXT, discovered_at TEXT,
          current_status TEXT, is_dummy INTEGER DEFAULT 0);
        CREATE TABLE mm_deals(
          id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER NOT NULL,
          stage TEXT NOT NULL, updated_at TEXT);
        CREATE TABLE mm_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_at TEXT NOT NULL,
          action TEXT NOT NULL, business_id INTEGER, detail TEXT);
    """)
    discovery.mm_pipeline.migrate(d)
    return d


def test_multi_source_collection_dedupes_hosts_and_retains_each_lane(tmp_path):
    nzbn = tmp_path / "nzbn.json"
    nzbn.write_text(json.dumps({"items": [{
        "nzbn": "9429000000009", "entityName": "Koru Plumbing Limited",
        "website": "https://koru.example/about", "region": "Canterbury",
    }]}), encoding="utf-8")
    directory = tmp_path / "directory.csv"
    directory.write_text(
        "business_name,website,region\nKoru Plumbing,https://www.koru.example/contact,Canterbury\n"
        "Harbour Electric,harbour.example,Wellington\n", encoding="utf-8")

    with patch.object(discovery, "searxng_candidates", return_value=[{
        "name": "Harbour Electric", "region": "Wellington",
        "public_website": "https://harbour.example/", "canonical_host": "harbour.example",
        "source": "searxng-local:test", "source_lane": "searxng",
    }]) as search:
        result = discovery.collect_multi_source(
            files=[nzbn, directory], queries=["electrician Wellington"],
            region="Wellington", limit=10)

    assert result["counts"] == {
        "sources": 3, "candidates": 4, "unique_hosts": 2,
        "source_errors": 0, "rejected_rows": 0,
    }
    assert len(result["candidates"]) == 2
    koru = next(row for row in result["candidates"] if row["canonical_host"] == "koru.example")
    assert {source["lane"] for source in koru["provenance_sources"]} == {"nzbn", "directory"}
    search.assert_called_once_with("electrician Wellington", "Wellington", "http://127.0.0.1:8888", 10)

    d = db()
    intake = discovery.ingest(d, result["candidates"])
    koru_id = next(item["business_id"] for item in intake["inserted"] if item["canonical_host"] == "koru.example")
    event = json.loads(d.execute(
        "SELECT detail FROM mm_events WHERE business_id=? AND action='discovery_intake'", (koru_id,)
    ).fetchone()[0])
    assert {source["lane"] for source in event["provenance"]["sources"]} == {"nzbn", "directory"}


def test_multi_source_collection_keeps_success_when_optional_search_is_blocked(tmp_path):
    source = tmp_path / "curated.json"
    source.write_text(json.dumps([{
        "name": "Southern Builders", "website": "southern.example", "region": "Otago",
    }]), encoding="utf-8")
    with patch.object(discovery, "searxng_candidates", side_effect=discovery.SearchBlocked(
        "BLOCKED_SEARCH_SERVICE_ABSENT", "http://127.0.0.1:8888", "offline")):
        result = discovery.collect_multi_source(
            files=[source], queries=["builder Dunedin"], region="Otago")
    assert len(result["candidates"]) == 1
    assert result["counts"]["source_errors"] == 1
    assert "BLOCKED_SEARCH_SERVICE_ABSENT" in result["sources"][1]["error"]


def test_multi_source_collection_requires_sources_and_bounds_batches():
    with pytest.raises(ValueError, match="at least one"):
        discovery.collect_multi_source()
    with pytest.raises(ValueError, match="region is required"):
        discovery.collect_multi_source(queries=["builder"])
    with pytest.raises(ValueError, match="import files"):
        discovery.collect_multi_source(files=["x"] * (discovery.MAX_BATCH_FILES + 1))
