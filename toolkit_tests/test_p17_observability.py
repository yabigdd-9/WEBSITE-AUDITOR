import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MM_DIR = ROOT / "money-machine"
if str(MM_DIR) not in sys.path:
    sys.path.insert(0, str(MM_DIR))

SPEC = importlib.util.spec_from_file_location("mm_observability_under_test", MM_DIR / "mm_observability.py")
obs = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(obs)


def seed(root: Path):
    (root / "database").mkdir(parents=True)
    (root / "state" / "worker-logs").mkdir(parents=True)
    db = root / "database" / "money_machine.db"
    d = sqlite3.connect(db)
    d.executescript(
        """
        CREATE TABLE pipeline_items(
          business_id INTEGER PRIMARY KEY,
          state TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 5,
          next_retry_at TEXT,
          lease_owner TEXT,
          lease_until TEXT,
          heartbeat_at TEXT,
          last_error TEXT,
          updated_at TEXT NOT NULL);
        CREATE TABLE mm_metrics(name TEXT PRIMARY KEY,value INTEGER NOT NULL,updated_at TEXT);
        CREATE TABLE worker_registry(
          worker_id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          hostname TEXT NOT NULL,
          pid INTEGER NOT NULL,
          started_at TEXT NOT NULL,
          heartbeat_at TEXT NOT NULL,
          lease_seconds INTEGER NOT NULL);
        CREATE TABLE mm_model_invocations(
          id INTEGER PRIMARY KEY,
          cost_usd REAL NOT NULL DEFAULT 0);
        """
    )
    d.execute(
        "INSERT INTO pipeline_items VALUES(1,'DISCOVERED',0,5,NULL,NULL,NULL,NULL,NULL,'2026-09-21T00:00:00+00:00')"
    )
    d.execute(
        "INSERT INTO pipeline_items VALUES(2,'PERMANENT_FAILURE',5,5,NULL,NULL,NULL,NULL,'fixture failure','2026-09-21T00:01:00+00:00')"
    )
    d.execute("INSERT INTO mm_metrics VALUES('pipeline.items.completed',7,'2026-09-21')")
    d.execute(
        "INSERT INTO worker_registry VALUES('worker-a','audit','fixture',123,'2026-09-21','2026-09-21',300)"
    )
    d.execute("INSERT INTO mm_model_invocations(cost_usd) VALUES(0)")
    d.commit()
    d.close()
    (root / "state" / "worker-logs" / "2026-09-21.jsonl").write_text(
        json.dumps({"at": "2026-09-21T00:00:00+00:00", "kind": "failure", "error": "fixture"}) + "\n"
    )
    return db


def rows(db):
    d = sqlite3.connect(db)
    result = d.execute(
        "SELECT business_id,state,attempts,last_error,updated_at FROM pipeline_items ORDER BY business_id"
    ).fetchall()
    d.close()
    return result


def test_observability_is_read_only_and_matches_v32_snapshots(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    db = seed(root)
    monkeypatch.setenv("MM_ROOT", str(root))
    before = rows(db)

    health = obs.health()
    metrics = obs.metrics()
    queue = obs.queue()
    dead = obs.dead_letter()
    errors = obs.errors()

    assert health["pipeline"]["states"]["DISCOVERED"] == 1
    assert metrics["metrics"]["pipeline.items.completed"] == 7
    assert metrics["model_cost_usd"] == 0
    assert queue["count"] == 2
    assert dead["count"] == 1
    assert dead["items"][0]["state"] == "PERMANENT_FAILURE"
    assert errors["count"] == 1

    paths = obs.write_snapshots()
    assert Path(paths["health"]).name == "health.json"
    assert Path(paths["metrics"]).name == "metrics.jsonl"
    assert Path(paths["errors"]).name == "errors.jsonl"
    assert Path(paths["dead_letter"]).name == "queue.json"
    assert Path(paths["worker_heartbeats"]).name == "worker-heartbeats"
    assert paths["worker_count"] == 1
    assert json.loads((root / "state" / "dead-letter" / "queue.json").read_text())["count"] == 1
    assert json.loads((root / "state" / "worker-heartbeats" / "worker-a.json").read_text())["kind"] == "audit"
    assert json.loads((root / "state" / "health.json").read_text())["paid_model_fallback"] is False
    assert len((root / "state" / "metrics.jsonl").read_text().splitlines()) == 1
    assert len((root / "state" / "errors.jsonl").read_text().splitlines()) == 1
    assert rows(db) == before
