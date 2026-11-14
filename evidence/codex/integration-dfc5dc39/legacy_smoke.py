"""Exercise imported SQL/import repairs only against synthetic local fixtures."""

import json
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "money-machine"), str(ROOT)]


def main():
    import mm_dashboard as dashboard
    import mm_ritual_cycles as cycles

    database = sqlite3.connect(":memory:")
    database.execute("CREATE TABLE pipeline_items(state TEXT,created_at TEXT,updated_at TEXT)")
    for delta in ("-10 seconds", "-30 seconds", "+10 seconds"):
        database.execute("INSERT INTO pipeline_items VALUES('AUDITED',datetime('now',?),datetime('now'))", (delta,))
    with patch.object(dashboard, "connect", return_value=database):
        statistics = dashboard.get_worker_statistics()
    assert statistics == {"AUDITED": {"count": 3, "avg_processing_time_seconds": 13.33}}, statistics

    scratch = ROOT / "work/codex-r00/integration"
    with tempfile.TemporaryDirectory(prefix="legacy-smoke-", dir=scratch) as folder:
        path = Path(folder) / "fixture.db"
        database = sqlite3.connect(path)
        database.execute("CREATE TABLE mm_learning(pattern TEXT,expected TEXT,actual TEXT,evidence_ref TEXT,confidence REAL,recommended_change TEXT,created_at TEXT)")
        with patch.object(cycles, "connect", return_value=database), patch.object(
            cycles, "_calculate_ritual_schedule", return_value={"fixture": True}
        ):
            result = cycles.calculate_ritual_timing("daily_purification", reference_time=1.0)
        assert result["status"] == "calculated", result
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as check:
            assert check.execute("SELECT count(*) FROM mm_learning").fetchone() == (1,)
    receipt = {
        "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "dashboard_aggregate_sql": "PASS",
        "contextlib_learning_write_on_synthetic_db": "PASS",
        "scope": "Two imported fixes; synthetic/in-memory databases only, not complete dashboard or ritual acceptance",
    }
    (Path(__file__).parent / "legacy-smoke.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
