import json

from website_auditor.monitoring.watchdog import Watchdog


def test_watchdog_uses_bounded_latest_previous_files(tmp_path):
    wd = Watchdog(snapshot_dir=tmp_path)
    first = [{"defect_key": "a", "severity": "medium"}]
    second = [
        {"defect_key": "a", "severity": "medium"},
        {"defect_key": "b", "severity": "high"},
    ]

    first_result = wd.run_check("example.co.nz", first)
    second_result = wd.run_check("example.co.nz", second)

    assert first_result["first_audit"] is True
    assert second_result["regressions"] == ["b"]
    assert second_result["classification"] == "MAJOR_REGRESSION"
    assert (tmp_path / "example.co.nz_latest.json").exists()
    assert (tmp_path / "example.co.nz_previous.json").exists()
    assert len(list(tmp_path.glob("example.co.nz_*.json"))) == 2


def test_watchdog_reports_improvement(tmp_path):
    wd = Watchdog(snapshot_dir=tmp_path)
    wd.run_check(
        "example.co.nz",
        [
            {"defect_key": "a", "severity": "medium"},
            {"defect_key": "b", "severity": "medium"},
        ],
    )
    result = wd.run_check("example.co.nz", [{"defect_key": "a", "severity": "medium"}])
    assert result["resolved"] == ["b"]
    assert result["classification"] == "IMPROVEMENT"


def test_watchdog_migrates_from_legacy_timestamp_snapshot(tmp_path):
    legacy = tmp_path / "example.co.nz_20260927_120000.json"
    legacy.write_text(json.dumps({
        "domain": "example.co.nz",
        "defect_keys": ["old"],
        "count": 1,
    }))
    wd = Watchdog(snapshot_dir=tmp_path)
    result = wd.detect_regressions(
        "example.co.nz",
        [{"defect_key": "new", "severity": "low"}],
    )
    assert result["regressions"] == ["new"]
    assert result["resolved"] == ["old"]
