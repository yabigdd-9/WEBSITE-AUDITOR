import importlib.util
import io
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
MODULE_PATH = MM_DIR / "mm_discovery.py"
spec = importlib.util.spec_from_file_location("mm_discovery_under_test", MODULE_PATH)
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


def db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.executescript(
        """
        CREATE TABLE businesses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          region TEXT,
          public_website TEXT,
          source TEXT,
          discovered_at TEXT,
          current_status TEXT,
          is_dummy INTEGER DEFAULT 0);
        CREATE TABLE mm_deals(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          business_id INTEGER NOT NULL,
          stage TEXT NOT NULL,
          updated_at TEXT);
        CREATE TABLE mm_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_at TEXT NOT NULL,
          action TEXT NOT NULL,
          business_id INTEGER,
          detail TEXT);
        """
    )
    discovery.mm_pipeline.migrate(d)
    return d


def test_root_url_and_candidate_normalization():
    url, host = discovery.root_url("www.example.co.nz/contact")
    assert url == "https://www.example.co.nz/"
    assert host == "example.co.nz"
    candidate = discovery.normalize_candidate(
        {"business_name": "Example", "website": "example.co.nz", "city": "Christchurch"},
        default_source="fixture",
    )
    assert candidate["name"] == "Example"
    assert candidate["region"] == "Christchurch"
    assert candidate["canonical_host"] == "example.co.nz"
    assert candidate["source"] == "fixture"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://10.0.0.2",
        "ftp://example.com",
    ],
)
def test_candidate_rejects_private_or_non_http_urls(url):
    with pytest.raises(ValueError):
        discovery.root_url(url)


def test_ingest_enqueues_only_discovered_and_dedupes():
    d = db()
    first = discovery.ingest(
        d,
        [
            {"name": "Alpha", "website": "https://alpha.example", "region": "Canterbury"},
            {"name": "Same Domain", "website": "https://www.alpha.example/about", "region": "Canterbury"},
            {"name": "Beta", "website": "beta.example", "region": "Canterbury"},
        ],
    )
    d.commit()
    assert first["counts"] == {"inserted": 2, "duplicates": 1, "rejected": 0}
    assert first["outreach_eligible"] is False
    states = [r["state"] for r in d.execute("SELECT state FROM pipeline_items ORDER BY business_id")]
    assert states == ["DISCOVERED", "DISCOVERED"]
    assert d.execute("SELECT count(*) FROM businesses").fetchone()[0] == 2
    assert d.execute("SELECT count(*) FROM mm_deals WHERE stage='DISCOVERED'").fetchone()[0] == 2

    second = discovery.ingest(
        d,
        [{"name": "Alpha renamed", "website": "https://alpha.example", "region": "Canterbury"}],
    )
    assert second["counts"]["inserted"] == 0
    assert second["counts"]["duplicates"] == 1


def test_dry_run_does_not_write():
    d = db()
    result = discovery.ingest(
        d,
        [{"name": "Alpha", "website": "alpha.example", "region": "Canterbury"}],
        dry_run=True,
    )
    assert result["counts"]["inserted"] == 1
    assert result["inserted"][0]["dry_run"] is True
    assert d.execute("SELECT count(*) FROM businesses").fetchone()[0] == 0


def test_read_candidates_csv_and_rejections(tmp_path):
    path = tmp_path / "prospects.csv"
    path.write_text(
        "business_name,website,region\n"
        "Alpha,alpha.example,Canterbury\n"
        "Bad,http://127.0.0.1,Canterbury\n",
        encoding="utf-8",
    )
    rows, rejected = discovery.read_candidates(path, default_source="csv-test")
    assert len(rows) == 1
    assert rows[0]["source"] == "csv-test"
    assert len(rejected) == 1


def test_searxng_must_be_loopback():
    for endpoint in ("https://127.0.0.1:8888", "http://example.com:8888"):
        with pytest.raises(ValueError, match="loopback"):
            discovery.searxng_candidates("plumber", "Canterbury", endpoint=endpoint)


def test_searxng_results_are_rooted_deduped_and_contact_free():
    payload = json.dumps(
        {
            "results": [
                {"title": "Alpha", "url": "https://alpha.example/services/plumbing"},
                {"title": "Alpha Contact", "url": "https://www.alpha.example/contact"},
                {"title": "Beta", "url": "https://beta.example/about"},
            ]
        }
    ).encode()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return payload

    with patch.object(discovery, "urlopen", return_value=Response()) as request:
        rows = discovery.searxng_candidates(
            "plumber christchurch",
            "Canterbury",
            endpoint="http://127.0.0.1:8888",
            limit=10,
        )
    assert [r["canonical_host"] for r in rows] == ["alpha.example", "beta.example"]
    assert rows[0]["public_website"] == "https://alpha.example/"
    assert all("email" not in row for row in rows)
    request.assert_called_once()
