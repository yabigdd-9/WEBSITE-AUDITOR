import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_monitor():
    spec = importlib.util.spec_from_file_location("monitor_audits_test", ROOT / "monitor-audits.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_targets_deduplicates_and_ignores_comments(tmp_path: Path):
    monitor = load_monitor()
    target_file = tmp_path / "targets.txt"
    target_file.write_text("# client sites\nhttps://a.example\nhttps://b.example\nhttps://a.example\n")
    targets = monitor.load_targets(["https://b.example", "https://c.example"], str(target_file))
    assert targets == ["https://b.example", "https://c.example", "https://a.example"]


def test_safe_domain_is_filename_safe():
    monitor = load_monitor()
    assert monitor.safe_domain("https://WWW.Example.co.nz/path") == "www.example.co.nz"


def test_atomic_json_replaces_file(tmp_path: Path):
    monitor = load_monitor()
    state = tmp_path / "state.json"
    monitor.atomic_json(state, {"cycle": 1})
    monitor.atomic_json(state, {"cycle": 2})
    assert '"cycle": 2' in state.read_text()
