import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MM_DIR = ROOT / "money-machine"
if str(MM_DIR) not in sys.path:
    sys.path.insert(0, str(MM_DIR))

SPEC = importlib.util.spec_from_file_location("mm_obsidian_under_test", MM_DIR / "mm_obsidian.py")
obsidian = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(obsidian)


def test_obsidian_sync_is_read_only_view(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    vault = tmp_path / "vault"
    (repo / "state").mkdir(parents=True)
    (repo / "reports").mkdir(parents=True)

    (repo / "MASTER_PLAN.md").write_text("# Plan\ncanonical\n", encoding="utf-8")
    (repo / "CURRENT_STATE.md").write_text("# State\ncurrent\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# Changelog\nentry\n", encoding="utf-8")
    (repo / "reports" / "DAILY_OPERATOR.md").write_text("# Daily\nno sends\n", encoding="utf-8")
    (repo / "reports" / "KPI_DASHBOARD.md").write_text("# KPI\n0 paid\n", encoding="utf-8")
    (repo / "state" / "health.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (repo / "state" / "metrics.jsonl").write_text(json.dumps({"queue": 2}) + "\n", encoding="utf-8")
    (repo / "state" / "errors.jsonl").write_text(json.dumps({"error": "fixture"}) + "\n", encoding="utf-8")

    before = {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file()
    }

    monkeypatch.setenv("MM_ROOT", str(repo))
    monkeypatch.setenv("MM_OBSIDIAN_ROOT", str(vault))

    result = obsidian.sync()

    assert result["ready"] is True
    assert result["runtime_dependency"] is False
    assert result["canonical_runtime_state"] is False
    assert result["canonical_send_authority"] is False
    assert result["generated_count"] == len(obsidian.GENERATED)

    control = (vault / "00-DASHBOARD" / "CONTROL-CENTRE.md").read_text()
    assert "Live outreach: disabled by default" in control
    assert "Canonical runtime state: SQLite + state files" in control

    after = {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file()
    }
    assert after == before


def test_obsidian_status_reports_missing_then_ready(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    vault = tmp_path / "vault"
    monkeypatch.setenv("MM_ROOT", str(repo))
    monkeypatch.setenv("MM_OBSIDIAN_ROOT", str(vault))

    initial = obsidian.status()
    assert initial["ready"] is False
    assert initial["runtime_dependency"] is False
    assert initial["missing_folders"]

    obsidian.sync()
    final = obsidian.status()
    assert final["ready"] is True
    assert final["missing_folders"] == []
    assert final["missing_generated_files"] == []
