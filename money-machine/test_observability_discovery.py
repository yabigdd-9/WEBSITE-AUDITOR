import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

import mm_observability as obs
import mm_recurring_discovery as recurring
import mm_search_backend


def config():
    return {
        "enabled": True,
        "interval_minutes": 360,
        "region": "New Zealand",
        "searxng_endpoint": "http://127.0.0.1:8888",
    }


def test_discovery_health_reports_absent_state_and_typed_search_failure(tmp_path):
    state = tmp_path / "recurring.json"
    probe = {
        "provider": "searxng",
        "endpoint": "http://127.0.0.1:8888",
        "ok": False,
        "state": mm_search_backend.BLOCKED_NOT_LISTENING,
    }
    with patch.object(recurring, "load_config", return_value=config()), \
         patch.object(recurring, "DEFAULT_STATE", state), \
         patch.object(mm_search_backend, "probe", return_value=probe):
        result = obs._discovery_health()

    assert result["enabled"] is True
    assert result["state_file_exists"] is False
    assert result["last_finished_at"] is None
    assert result["due_now"] is True
    assert result["searxng"]["state"] == mm_search_backend.BLOCKED_NOT_LISTENING
    assert result["external_sends"] == 0
    assert result["paid_calls"] == 0


def test_discovery_health_surfaces_last_cycle_and_next_due(tmp_path):
    state = tmp_path / "recurring.json"
    last = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)
    state.write_text(json.dumps({
        "last_finished_at": last.isoformat(),
        "collection_counts": {"candidates": 4, "source_errors": 0},
        "intake_counts": {"inserted": 2, "duplicates": 2, "rejected": 0},
        "sources": [{"source": "fixture", "candidates": 4}],
    }))
    probe = {
        "provider": "searxng",
        "endpoint": "http://127.0.0.1:8888",
        "ok": True,
        "state": mm_search_backend.OK,
    }
    with patch.object(recurring, "load_config", return_value=config()), \
         patch.object(recurring, "DEFAULT_STATE", state), \
         patch.object(mm_search_backend, "probe", return_value=probe):
        result = obs._discovery_health()

    expected = last + dt.timedelta(minutes=360)
    actual = dt.datetime.fromisoformat(result["next_due_at"])
    assert abs((actual - expected).total_seconds()) < 1
    assert result["due_now"] is False
    assert result["collection_counts"]["candidates"] == 4
    assert result["intake_counts"]["inserted"] == 2
    assert result["searxng"]["state"] == mm_search_backend.OK
