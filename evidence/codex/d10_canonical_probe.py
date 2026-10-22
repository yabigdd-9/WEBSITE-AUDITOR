"""Restore the observed schema with synthetic durable work; never open live data."""

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    fixture = root / "work/codex-r00/canonical-schema"
    path = fixture / "database/money_machine.db"
    if (fixture / "backups").exists():
        raise SystemExit("Drill already ran; preserve its evidence")
    spec = importlib.util.spec_from_file_location("fixture_core", root / "money-machine/mm_core.py")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    start = datetime.now(timezone.utc).isoformat()
    timer = time.monotonic()
    source = core.connect(path)
    source.execute("PRAGMA journal_mode=WAL")
    source.execute("PRAGMA wal_autocheckpoint=0")
    source.execute("INSERT INTO businesses(id,name,source,discovered_at,current_status,is_dummy) "
                   "VALUES(1,'Synthetic restore fixture','fixture',?,'discovered',1)", (start,))
    source.execute("INSERT INTO mm_suppression(address,reason,created_at) VALUES(?,?,?)",
                   ("fixture@example.invalid", "synthetic operator stop", start))
    for number, status in enumerate(["planned", "quarantined"]):
        source.execute("INSERT INTO outreach_send_ledger(idempotency_key,business_id,recipient,"
                       "content_hash,campaign,status,created_at,updated_at) VALUES(?,1,?,?,?,?,?,?)",
                       (str(number), "fixture@example.invalid", "f" * 64,
                        "synthetic-only", status, start, start))
    source.commit()
    before = list(source.iterdump())
    backup = core.backup(fixture)
    saved = backup / "money_machine.db"
    saved_hash = hashlib.sha256(saved.read_bytes()).hexdigest()
    target = fixture / "restored/money_machine.db"
    target.parent.mkdir()
    with sqlite3.connect(saved.as_uri() + "?mode=ro", uri=True) as snapshot:
        with sqlite3.connect(target) as restored:
            snapshot.backup(restored)
            assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert not restored.execute("PRAGMA foreign_key_check").fetchall()
            assert list(restored.iterdump()) == before
            assert restored.execute("SELECT status,count(*) FROM outreach_send_ledger GROUP BY status").fetchall() == [("planned", 1), ("quarantined", 1)]
            assert restored.execute("SELECT count(*) FROM mm_suppression").fetchone() == (1,)
    partial = fixture / "restored/interrupted.db"
    crash = (
        "import sqlite3,os,sys;"
        "src=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);"
        "dst=sqlite3.connect(sys.argv[2]);"
        "src.backup(dst,pages=1,progress=lambda *args:os._exit(17))"
    )
    child = subprocess.run([sys.executable, "-B", "-c", crash, str(saved), str(partial)],
                           capture_output=True, text=True, timeout=10)
    assert child.returncode == 17
    try:
        with sqlite3.connect(partial.as_uri() + "?mode=ro", uri=True) as interrupted:
            partial_matches = list(interrupted.iterdump()) == before
    except sqlite3.DatabaseError:
        partial_matches = False
    assert not partial_matches
    assert hashlib.sha256(saved.read_bytes()).hexdigest() == saved_hash
    assert list(source.iterdump()) == before
    source.close()
    receipt = {
        "status": "PASS_CANONICAL_SCHEMA_SYNTHETIC_DATA",
        "started_at_utc": start,
        "duration_seconds": round(time.monotonic() - timer, 3),
        "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_fixture": str(path),
        "backup_hash": saved_hash,
        "restored_dump_matches_source": True,
        "integrity_check": "ok",
        "foreign_key_violations": 0,
        "planned_and_quarantined_records_preserved": True,
        "suppression_preserved": True,
        "interrupted_restore_exit": child.returncode,
        "interrupted_restore_not_promoted": True,
        "backup_and_source_preserved": True,
        "production_records_copied": 0,
        "limitations": ["No production restore or deployment", "Not independent peer acceptance", "Does not establish an RPO/RTO service guarantee"],
    }
    (root / "evidence/codex/d10-canonical-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
