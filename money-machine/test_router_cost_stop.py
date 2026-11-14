"""Billing ambiguity blocks fallback and remains blocked across calls."""
import io
import json
import urllib.error
from unittest.mock import patch

import mm_model_router as router
import pytest


@pytest.fixture(autouse=True)
def no_provider_subprocess(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("provider subprocess forbidden")
    monkeypatch.setattr(router.subprocess, "run", forbidden)


@pytest.mark.parametrize("cost", [None, True, "NaN", "-1", "bad", "0.01"])
def test_unknown_or_nonzero_cost_stops_before_fallback(tmp_path, monkeypatch, cost):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    payload = {"model": "fixture:free", "choices": [{"message": {"content": "fixture"}}], "usage": {"cost": cost}}
    with patch.object(router, "_open_local", return_value=io.BytesIO(json.dumps(payload).encode())), \
         patch.object(router, "_hermes_complete", side_effect=AssertionError("no fallback")):
        with pytest.raises(router.CostSafetyStop):
            router.local_complete("synthetic", lookup=lambda lane: "fixture:free")
    assert (tmp_path / "state/model-routing-cost-stop.json").exists()
    with patch.object(router, "_lookup_route", side_effect=AssertionError("no route probe")):
        with pytest.raises(router.CostSafetyStop):
            router.local_complete("synthetic")


def test_explicit_zero_cost_answer_remains_permitted(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    payload = {"model": "fixture:free", "choices": [{"message": {"content": "fixture"}}], "usage": {"cost": "0"}}
    with patch.object(router, "_open_local", return_value=io.BytesIO(json.dumps(payload).encode())):
        result = router.local_complete("synthetic", lookup=lambda lane: "fixture:free")
    assert result["text"] == "fixture"
    assert not (tmp_path / "state/model-routing-cost-stop.json").exists()


@pytest.mark.parametrize("fault", [
    TimeoutError("uncertain"),
    urllib.error.HTTPError("http://127.0.0.1", 429, "quota", {}, None),
    urllib.error.HTTPError("http://127.0.0.1", 402, "billing", {}, None),
])
def test_dispatch_uncertainty_or_quota_denies_another_provider(tmp_path, monkeypatch, fault):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    with patch.object(router, "_open_local", side_effect=fault), \
         patch.object(router, "_hermes_complete", side_effect=AssertionError("no fallback")):
        with pytest.raises(router.CostSafetyStop):
            router.local_complete("synthetic", lookup=lambda lane: "fixture:free")
    incident = json.loads((tmp_path / "state/model-routing-cost-stop.json").read_text())
    assert incident["reason"] == "dispatch_outcome_unknown"
