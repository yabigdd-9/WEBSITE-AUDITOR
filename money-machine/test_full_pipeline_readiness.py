import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "full-pipeline.py"
spec = importlib.util.spec_from_file_location("full_pipeline_under_test", MODULE_PATH)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


def test_email_discovery_accepts_missing_state(tmp_path):
    pipeline.AUDITS = tmp_path / "audits"
    pipeline.AUDITS.mkdir()
    pipeline.CFG = {
        "quiet": True,
        "delay": 0,
        "output_dir": str(tmp_path),
        "max_workers": 1,
    }
    results, errors = pipeline.run_email_discovery(max_workers=1, state=None)
    assert results == {}
    assert errors == {}


def test_load_and_save_state_roundtrip(tmp_path):
    state_file = tmp_path / "pipeline-state.json"
    original = pipeline.STATE_FILE
    try:
        pipeline.STATE_FILE = state_file
        state = {"completed": {"example.com": ["email"]}}
        pipeline.save_state(state)
        assert pipeline.load_state() == state
    finally:
        pipeline.STATE_FILE = original
