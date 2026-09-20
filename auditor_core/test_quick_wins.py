import json
from pathlib import Path

from auditor_core.quick_wins import quick_wins_markdown, rank_quick_wins


FIXTURES = Path(__file__).with_name("fixtures")


def test_quick_wins_rank_low_effort_high_confidence_first():
    remediation = json.loads((FIXTURES / "remediation_sample.json").read_text())
    report = rank_quick_wins(remediation)
    assert report["quick_wins"][0]["check_id"] == "seo.h1_missing"
    assert report["quick_wins"][0]["quick_win_score"] > report["quick_wins"][1]["quick_win_score"]


def test_quick_wins_markdown_is_portable():
    remediation = json.loads((FIXTURES / "remediation_sample.json").read_text())
    text = quick_wins_markdown(rank_quick_wins(remediation))
    assert "# Quick Wins — example.co.nz" in text
    assert "Missing H1 tag" in text
