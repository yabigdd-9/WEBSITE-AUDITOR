from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "activate-scanning.sh"


def test_scanning_activation_is_focused_and_never_touches_fcc():
    text = SCRIPT.read_text()
    assert "money-machine/scripts/searxng.sh\" install" in text
    assert "./mm searxng verify" in text
    assert "money-machine/supervisor/launchd.py\" install" in text
    assert "./mm discovery-cycle --force" in text
    assert "./mm supervisor status" in text
    assert "./mm health" in text

    lowered = text.lower()
    assert "fcc" not in lowered
    assert "local-machine.sh" not in lowered
    assert "record-sent" not in lowered
    assert "transport-send" not in lowered


def test_scanning_activation_verifies_search_before_forced_cycle():
    text = SCRIPT.read_text()
    assert text.index("./mm searxng verify") < text.index("./mm discovery-cycle --force")
