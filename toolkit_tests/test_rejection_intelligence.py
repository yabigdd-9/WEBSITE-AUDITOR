import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "money-machine"))
spec = importlib.util.spec_from_file_location(
    "mm_rejection", ROOT / "money-machine" / "mm_rejection.py"
)
rejection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rejection)


def database():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.executescript("""
        CREATE TABLE businesses(id INTEGER PRIMARY KEY);
        INSERT INTO businesses VALUES (1);
        CREATE TABLE experience_ledger(
          id INTEGER PRIMARY KEY, outcome TEXT NOT NULL, actor TEXT NOT NULL,
          observed_at TEXT NOT NULL, business_id INTEGER NOT NULL,
          evidence_hash TEXT NOT NULL, created_at TEXT NOT NULL);
    """)
    rejection.migrate(d)
    return d


def test_false_negative_is_recorded_in_its_own_cluster_counter():
    d = database()

    rejection_id = rejection.detect_false_negative(
        d, 1, "REJECTED", "unrecognized evidence reason", "qualification",
        "QUALIFICATION_FAILED",
    )

    row = d.execute("SELECT * FROM terminal_rejections WHERE id=?", (rejection_id,)).fetchone()
    cluster = d.execute("SELECT * FROM error_clusters").fetchone()
    correction = d.execute("SELECT * FROM human_corrections").fetchone()
    assert row["canonical_reason"] == "INSUFFICIENT_EVIDENCE"
    assert cluster["false_negative"] == 1
    assert cluster["false_positive"] == 0
    assert correction["correction_note"] == "false_negative correction"


def test_error_clusters_increment_when_same_failure_recurs():
    d = database()
    first = rejection.upsert_cluster(
        d, "NO_VERIFIED_EMAIL", "NO_VERIFIED_EMAIL", "contact", "missing email", 1
    )
    second = rejection.upsert_cluster(
        d, "NO_VERIFIED_EMAIL", "NO_VERIFIED_EMAIL", "contact", "missing email", 1
    )
    assert second["id"] == first["id"]
    assert second["observed_count"] == 2
