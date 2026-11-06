import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

import yaml

import mm_recurring_discovery as recurring

UTC = dt.timezone.utc


def write_config(path, **overrides):
    config = {
        "enabled": True,
        "interval_minutes": 360,
        "region": "New Zealand",
        "searxng_endpoint": "http://127.0.0.1:8888",
        "results_per_query": 5,
        "inbox_dir": "discovery-inbox",
        "queries": ["plumber Christchurch NZ"],
    }
    config.update(overrides)
    path.write_text(yaml.safe_dump(config))
    return path


def test_disabled_schedule_does_not_run(tmp_path):
    cfg = write_config(tmp_path / "cfg.yaml", enabled=False)
    result = recurring.run_due(
        object(), config_path=cfg, state_path=tmp_path / "state.json"
    )
    assert result["ran"] is False
    assert result["external_sends"] == 0
    assert result["paid_calls"] == 0


def test_recent_run_is_not_repeated(tmp_path):
    cfg = write_config(tmp_path / "cfg.yaml")
    now = dt.datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"last_finished_at": now.isoformat()}))
    result = recurring.run_due(
        object(), config_path=cfg, state_path=state, at=now
    )
    assert result["ran"] is False
    assert result["reason"] == "disabled_or_not_due"


def test_force_bypasses_interval_but_not_disabled_schedule(tmp_path):
    now = dt.datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"last_finished_at": now.isoformat()}))
    cfg = write_config(tmp_path / "cfg.yaml")

    collection = {
        "candidates": [],
        "sources": [{"source": "fixture", "kind": "search", "candidates": 0}],
        "source_rejections": [],
        "counts": {
            "sources": 1, "candidates": 0, "unique_hosts": 0,
            "source_errors": 0, "rejected_rows": 0,
        },
    }
    intake = {
        "counts": {"inserted": 0, "duplicates": 0, "rejected": 0},
        "outreach_eligible": False,
    }
    with patch.object(
        recurring.mm_discovery, "collect_multi_source", return_value=collection
    ) as collect, patch.object(
        recurring.mm_discovery, "ingest", return_value=intake
    ):
        result = recurring.run_due(
            object(), config_path=cfg, state_path=state, at=now, force=True
        )
    assert result["ran"] is True
    assert result["forced"] is True
    assert result["external_sends"] == 0
    assert result["paid_calls"] == 0
    collect.assert_called_once()

    disabled = write_config(tmp_path / "disabled.yaml", enabled=False)
    result = recurring.run_due(
        object(), config_path=disabled, state_path=tmp_path / "disabled-state.json",
        at=now, force=True
    )
    assert result["ran"] is False
    assert result["reason"] == "disabled"


def test_due_cycle_collects_and_ingests_without_send_or_paid_calls(tmp_path):
    cfg = write_config(tmp_path / "cfg.yaml")
    state = tmp_path / "state.json"
    candidate = {
        "name": "Fixture Plumbing",
        "public_website": "https://fixture-plumbing.example.nz/",
        "canonical_host": "fixture-plumbing.example.nz",
        "region": "New Zealand",
        "source": "fixture",
    }
    collection = {
        "candidates": [candidate],
        "sources": [{"source": "fixture", "kind": "search", "candidates": 1}],
        "source_rejections": [],
        "counts": {
            "sources": 1, "candidates": 1, "unique_hosts": 1,
            "source_errors": 0, "rejected_rows": 0,
        },
    }
    intake = {
        "counts": {"inserted": 1, "duplicates": 0, "rejected": 0},
        "outreach_eligible": False,
    }
    at = dt.datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
    with patch.object(
        recurring.mm_discovery, "collect_multi_source", return_value=collection
    ) as collect, patch.object(
        recurring.mm_discovery, "ingest", return_value=intake
    ) as ingest:
        result = recurring.run_due(
            object(), config_path=cfg, state_path=state, at=at
        )
    assert result["ran"] is True
    assert result["intake_counts"]["inserted"] == 1
    assert result["external_sends"] == 0
    assert result["paid_calls"] == 0
    collect.assert_called_once()
    ingest.assert_called_once()
    saved = json.loads(state.read_text())
    assert saved["last_finished_at"] == at.isoformat()


def test_no_sources_records_safe_noop(tmp_path):
    cfg = write_config(tmp_path / "cfg.yaml", queries=[], inbox_dir="missing")
    state = tmp_path / "state.json"
    at = dt.datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
    with patch.object(recurring.mm_core, "root", return_value=tmp_path):
        result = recurring.run_due(
            object(), config_path=cfg, state_path=state, at=at
        )
    assert result["ran"] is False
    assert result["reason"] == "no_sources"
    assert result["external_sends"] == 0
