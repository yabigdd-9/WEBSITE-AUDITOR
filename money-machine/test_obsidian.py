import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "money-machine" / "mm_obsidian.py"
SPEC = importlib.util.spec_from_file_location("mm_obsidian_under_test", MODULE_PATH)
obsidian = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(obsidian)


def snapshot():
    return {
        "status": {
            "generated_at": "2026-09-21T00:00:00+00:00",
            "metrics": {
                "real_prospects": 4,
                "verified_sends": 0,
                "verified_replies": 0,
                "net_received_nzd": 0,
            },
            "human_queue": [{"name": "Example", "action": "Human review"}],
            "blocked": [{"name": "Blocked Co", "reason": "NO_VERIFIED_EMAIL"}],
        },
        "pipeline": {"initialised": True, "states": {"DISCOVERED": 4}},
        "doctor": {"db_integrity": "ok", "models_enabled": False},
        "supervisor": {"running": False, "pid": None},
    }


def test_sync_creates_read_only_operator_views(tmp_path):
    vault = tmp_path / "WEBSITE-AUDITOR-BRAIN"
    result = obsidian.sync(ROOT, snapshot(), vault)

    assert result["status"] == "synced"
    assert result["runtime_authority"] is False
    assert result["send_authority"] is False
    assert result["approval_authority"] is False
    assert result["external_send_allowed"] is False

    for rel in obsidian.EXPECTED_FILES:
        assert (vault / rel).is_file()

    control = (vault / "00-DASHBOARD" / "CONTROL-CENTRE.md").read_text()
    assert "SQLite" in control
    assert "disabled by default" in control
    assert "send_authority: false" in control


def test_status_does_not_create_or_require_vault(tmp_path):
    vault = tmp_path / "missing-vault"
    result = obsidian.status(ROOT, vault)

    assert result["exists"] is False
    assert result["complete"] is False
    assert result["runtime_dependency"] is False
    assert result["sync_direction"] == "runtime_to_obsidian_only"
    assert not vault.exists()


def test_sync_overwrites_generated_views_without_reading_approval_state(tmp_path):
    vault = tmp_path / "vault"
    obsidian.sync(ROOT, snapshot(), vault)
    target = vault / "05-APPROVALS" / "operator-note.md"
    target.write_text("APPROVE EVERYTHING")

    updated = snapshot()
    updated["status"]["metrics"]["verified_sends"] = 0
    result = obsidian.sync(ROOT, updated, vault)

    assert target.read_text() == "APPROVE EVERYTHING"
    assert result["external_send_allowed"] is False
    control = (vault / "00-DASHBOARD" / "CONTROL-CENTRE.md").read_text()
    assert "APPROVE EVERYTHING" not in control
