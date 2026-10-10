"""Synthetic offline regressions for canonical captures and deterministic recovery."""
import datetime as dt
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import mm_core as core
import mm_evidence_bridge as bridge
import mm_operator as operator
import pytest

from auditor_toolkit.models import SCHEMA_VERSION


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    path = tmp_path / "database" / "money_machine.db"
    path.parent.mkdir()
    sqlite3.connect(path).close()
    d = core.connect(path)
    d.executescript("""
        CREATE TABLE businesses(id INTEGER PRIMARY KEY,name TEXT,public_website TEXT,
            is_dummy INTEGER DEFAULT 0,current_status TEXT,suppression_reason TEXT);
        CREATE TABLE pipeline_items(business_id INTEGER,state TEXT,payload TEXT);
        CREATE TABLE pipeline_events(id INTEGER PRIMARY KEY,business_id INTEGER,
            to_state TEXT,evidence TEXT,event_at TEXT);
        CREATE TABLE mm_deals(business_id INTEGER,stage TEXT);
        CREATE TABLE mm_holds(business_id INTEGER,reason TEXT);
        CREATE TABLE mm_evidence(id INTEGER PRIMARY KEY,business_id INTEGER,checked_at TEXT);
        CREATE TABLE mm_messages(id INTEGER PRIMARY KEY,business_id INTEGER,approved_hash TEXT);
        INSERT INTO businesses VALUES(1,'Fixture','https://fixture.example.co.nz',0,'audited',NULL);
        INSERT INTO pipeline_items VALUES(1,'NEEDS_REVIEW','{}');
        INSERT INTO mm_deals VALUES(1,'AUDITED');
        INSERT INTO mm_messages VALUES(1,1,'keep-approval');
    """)
    d.commit()
    yield d, tmp_path / "outputs" / "toolkit", path
    d.close()


def saved_report(root, run_id="fixture-run", **changes):
    folder = root / run_id
    folder.mkdir(parents=True, exist_ok=True)
    html = folder / "report.html"
    html.write_text("<html>Deterministic synthetic fixture</html>")
    path = folder / "report.json"
    report = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id,
        "url": "https://fixture.example.co.nz", "timestamp": core.now(),
        "status": "complete", "profile": "static", "defects": [],
        "checks": {name: {"required": True, "status": "ok"} for name in bridge.STATIC_CHECKS},
        "coverage": {"required": len(bridge.STATIC_CHECKS), "passed": len(bridge.STATIC_CHECKS)},
        "artifacts": {"json": str(path), "html": str(html)},
        "manifest": {"html": {"path": str(html), "size": html.stat().st_size,
                              "sha256": core.sha(html.read_bytes())}},
    }
    report.update(changes)
    report.setdefault("evidence", {"fetch": {"url": report["url"], "mode": "static",
                      "observed_at": report["timestamp"], "data": {"status_code": 200}}})
    path.write_text(json.dumps(report))
    return path, report


def audit_event(d, report, **changes):
    evidence = {"run_id": report["run_id"], "report_path": report["artifacts"]["json"],
                "audit_engine": "auditor_toolkit"}
    evidence.update(changes)
    d.execute("INSERT INTO pipeline_events(business_id,to_state,evidence,event_at) VALUES(1,'AUDITED',?,?)",
              (json.dumps(evidence), core.now()))
    d.commit()


def snapshot(d):
    tables = [row[0] for row in d.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {table: [tuple(row) for row in d.execute(f"SELECT * FROM {table}")] for table in tables}


def test_stage_signal_and_legacy_observation_do_not_invent_canonical_capture(case):
    d, root, _ = case
    d.execute("INSERT INTO mm_evidence VALUES(1,1,?)", (core.now(),))
    d.execute("INSERT INTO pipeline_events VALUES(1,1,'AUDITED','{\"score\":20}',?)", (core.now(),))
    result = bridge.audit_evidence_status(d, 1, root)
    assert result["stage_signal"]
    assert result["legacy_observations"] == 1
    assert result["status"] == "MISSING"
    assert not result["complete"]
    assert not root.exists()


def test_recovery_preview_is_readonly_and_apply_idempotent_preserves_stage_and_approval(case):
    d, root, db_path = case
    stamp = (dt.datetime.now(core.UTC) - dt.timedelta(days=2)).isoformat()
    path, report = saved_report(root, timestamp=stamp)
    audit_event(d, report)
    before = snapshot(d)
    db_hash = core.sha(db_path.read_bytes())
    with patch("socket.socket", side_effect=AssertionError("no network")), \
            patch("auditor_toolkit.pipeline.run_audit", side_effect=AssertionError("no scan")):
        with core.connect(db_path, readonly=True) as ro:
            preview = bridge.recover_evidence(ro, [1], toolkit_root=root)
        assert preview["results"][0]["status"] == "RECOVERABLE"
        assert preview["recorded"] == 0
        assert snapshot(d) == before
        assert core.sha(db_path.read_bytes()) == db_hash
        with d:
            applied = bridge.recover_evidence(d, [1], apply=True, toolkit_root=root)
        assert applied["recorded"] == 1
        assert applied["stage_changes"] == applied["claim_verifications"] == 0
        after = snapshot(d)
        assert {key: after[key] for key in before} == before
        row = d.execute("SELECT * FROM mm_audit_evidence").fetchone()
        assert row["captured_at"] == stamp
        assert row["report_hash"] == core.sha(path.read_bytes())
        with d:
            again = bridge.recover_evidence(d, [1, 1], apply=True, toolkit_root=root)
        assert again["recorded"] == 0
        assert snapshot(d) == after
    status = bridge.audit_evidence_status(d, 1, root)
    assert status["status"] == "CURRENT" and status["complete"]
    assert status["claim_status"] == "unverified"
    assert not status["independently_verified"]


@pytest.mark.parametrize("field,value,expected", [
    ("timestamp", "2000-01-01T00:00:00+00:00", "STALE"),
    ("timestamp", "2999-01-01T00:00:00+00:00", "INVALID"),
    ("timestamp", "broken", "INVALID"),
    ("status", "partial", "PARTIAL"),
    ("url", "https://fixture.example.co.nz.attacker.example", "INVALID"),
    ("url", "https://other.example.co.nz/?next=fixture.example.co.nz", "INVALID"),
    ("url", "https://fixture.example.co.nz/other", "INVALID"),
    ("url", "http://127.0.0.1", "INVALID"),
    ("checks", {}, "PARTIAL"),
    ("checks", {"fetch": None}, "INVALID"),
    ("schema_version", "future", "INVALID"),
    ("manifest", {}, "INVALID"),
    ("coverage", {"required": 0, "passed": 0}, "INVALID"),
    ("profile", "rendered", "INVALID"),
    ("run_id", "../escape", "INVALID"),
    ("defects", 5, "INVALID"),
    ("evidence", {}, "INVALID"),
])
def test_invalid_partial_or_stale_reports_cannot_be_recovered(case, field, value, expected):
    d, root, _ = case
    path, _ = saved_report(root, **{field: value})
    result = bridge.validate_report(d, 1, path, root)
    assert result["status"] == expected
    with pytest.raises(ValueError):
        bridge.register_audit(d, 1, path, root)
    assert not bridge._columns(d, "mm_audit_evidence")


@pytest.mark.parametrize("target", ["report", "html", "missing"])
def test_registered_artifact_tampering_blocks_current_status_and_recovery(case, target):
    d, root, _ = case
    path, report = saved_report(root)
    bridge.register_audit(d, 1, path, root)
    if target == "report":
        path.write_text(path.read_text() + " ")
    elif target == "html":
        Path(report["artifacts"]["html"]).write_text("tampered")
    else:
        path.unlink()
    before = snapshot(d)
    status = bridge.audit_evidence_status(d, 1, root)
    assert status["status"] in {"INVALID", "MISSING"}
    assert not status["complete"]
    recovered = bridge.recover_evidence(d, [1], apply=True, toolkit_root=root)
    assert recovered["recorded"] == 0
    assert snapshot(d) == before


@pytest.mark.parametrize("sql", [
    "UPDATE businesses SET suppression_reason='hold' WHERE id=1",
    "UPDATE businesses SET current_status='rejected' WHERE id=1",
    "UPDATE businesses SET is_dummy=1 WHERE id=1",
    "UPDATE pipeline_items SET state='REJECTED' WHERE business_id=1",
    "UPDATE pipeline_items SET state='SUPPRESSED' WHERE business_id=1",
    "UPDATE mm_deals SET stage='SUPPRESSED' WHERE business_id=1",
    "INSERT INTO mm_holds VALUES(1,'hold')",
])
def test_all_terminal_or_hold_sources_are_excluded_without_mutation(case, sql):
    d, root, _ = case
    path, report = saved_report(root)
    audit_event(d, report)
    d.execute(sql)
    d.commit()
    before = snapshot(d)
    with patch.object(bridge, "validate_report", side_effect=AssertionError("must guard before artifact read")):
        result = bridge.recover_evidence(d, [1], apply=True, toolkit_root=root, report_path=path)
    assert result["results"][0]["status"] == "EXCLUDED"
    assert result["recorded"] == 0
    assert snapshot(d) == before


def test_apply_requires_exact_ids_and_explicit_report_is_single_business(case):
    d, root, _ = case
    path, _ = saved_report(root)
    before = snapshot(d)
    for ids in (None, []):
        with pytest.raises(ValueError, match="explicit"):
            bridge.recover_evidence(d, ids, apply=True, toolkit_root=root)
    with pytest.raises(ValueError, match="exactly one"):
        bridge.recover_evidence(d, [1, 2], toolkit_root=root, report_path=path)
    assert snapshot(d) == before


def test_append_only_anchor_and_changed_same_run_cannot_replace_hash(case):
    d, root, _ = case
    path, _ = saved_report(root)
    bridge.register_audit(d, 1, path, root)
    before = snapshot(d)
    for sql in ("UPDATE mm_audit_evidence SET report_hash='new'", "DELETE FROM mm_audit_evidence"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            d.execute(sql)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        d.execute("INSERT OR REPLACE INTO mm_audit_evidence SELECT * FROM mm_audit_evidence")
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="changed"):
        bridge.register_audit(d, 1, path, root)
    assert snapshot(d) == before


def test_invalid_explicit_recovery_report_cannot_retain_current_complete_flag(case):
    d, root, _ = case
    path, _ = saved_report(root)
    bridge.register_audit(d, 1, path, root)
    wrong, _ = saved_report(root, run_id="wrong-site", url="https://other.example.co.nz")
    result = bridge.recover_evidence(d, [1], toolkit_root=root, report_path=wrong)
    assert result["results"][0]["status"] == "INVALID"
    assert not result["results"][0]["complete"]


def test_report_path_escape_and_symlink_rejected(case, tmp_path):
    d, root, _ = case
    path, report = saved_report(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    html = Path(report["artifacts"]["html"])
    html.unlink()
    (outside / "report.html").write_text("external")
    html.symlink_to(outside / "report.html")
    assert bridge.validate_report(d, 1, path, root)["status"] == "INVALID"
    assert bridge.validate_report(d, 1, outside / "report.json", root)["status"] == "INVALID"


def test_latest_new_event_supersedes_registered_capture_even_when_partial(case):
    d, root, _ = case
    path, _ = saved_report(root)
    bridge.register_audit(d, 1, path, root)
    _, newer = saved_report(root, run_id="new-run", status="partial")
    audit_event(d, newer)
    assert bridge.audit_evidence_status(d, 1, root)["status"] == "PARTIAL"
    assert bridge.recover_evidence(d, [1], apply=True, toolkit_root=root)["recorded"] == 0


def test_readonly_history_recovers_exact_site_without_new_stage_signal(case):
    d, root, _ = case
    _, report = saved_report(root)
    with sqlite3.connect(root / "history.sqlite3") as history:
        history.execute("CREATE TABLE runs(id TEXT,url TEXT,timestamp TEXT,report TEXT)")
        history.execute("INSERT INTO runs VALUES(?,?,?,?)",
                        (report["run_id"], report["url"], report["timestamp"], json.dumps(report)))
        history.execute("INSERT INTO runs VALUES('wrong','https://other.example.co.nz/?fixture.example.co.nz','2999','{}')")
    before = core.sha((root / "history.sqlite3").read_bytes())
    result = bridge.audit_evidence_status(d, 1, root)
    assert result["status"] == "RECOVERABLE"
    assert not result["stage_signal"]
    assert core.sha((root / "history.sqlite3").read_bytes()) == before
    assert not bridge._columns(d, "mm_audit_evidence")


def test_missing_latest_history_report_keeps_missing_status(case):
    d, root, _ = case
    path, report = saved_report(root)
    with sqlite3.connect(root / "history.sqlite3") as history:
        history.execute("CREATE TABLE runs(id TEXT,url TEXT,timestamp TEXT,report TEXT)")
        history.execute("INSERT INTO runs VALUES(?,?,?,?)",
                        (report["run_id"], report["url"], report["timestamp"], json.dumps(report)))
    path.unlink()
    result = bridge.audit_evidence_status(d, 1, root)
    assert result["status"] == "MISSING"
    assert not result["complete"]


def test_minimal_schema_and_summary_need_no_migrations(tmp_path):
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.execute("CREATE TABLE businesses(id INTEGER PRIMARY KEY,public_website TEXT)")
    d.execute("INSERT INTO businesses VALUES(1,'https://fixture.example.co.nz')")
    summary = bridge.audit_evidence_summary(d, tmp_path / "absent")
    assert summary["status_counts"] == {"MISSING": 1}
    assert summary["eligible_without_current_evidence"] == 1
    assert not (tmp_path / "absent").exists()
    d.close()


def test_cli_status_preview_apply_and_missing_ids(case, capsys):
    d, root, _ = case
    _, report = saved_report(root)
    audit_event(d, report)
    assert operator.main(["evidence-status", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "RECOVERABLE"
    assert operator.main(["evidence-recover", "--ids", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["recorded"] == 0
    with pytest.raises(SystemExit) as exc:
        operator.main(["evidence-recover", "--apply"])
    assert exc.value.code == 2
    capsys.readouterr()
    assert operator.main(["evidence-recover", "--ids", "1", "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["recorded"] == 1
    assert operator.main(["evidence-status"]) == 0
    assert json.loads(capsys.readouterr().out)["status_counts"] == {"CURRENT": 1}


def test_newer_partial_history_supersedes_older_registered_capture(case):
    d, root, _ = case
    path, older = saved_report(root, timestamp=(dt.datetime.now(core.UTC) - dt.timedelta(hours=1)).isoformat())
    bridge.register_audit(d, 1, path, root)
    _, newer = saved_report(root, run_id="new-partial", status="partial")
    with sqlite3.connect(root / "history.sqlite3") as history:
        history.execute("CREATE TABLE runs(id TEXT,url TEXT,timestamp TEXT,report TEXT)")
        for report in (older, newer):
            history.execute("INSERT INTO runs VALUES(?,?,?,?)",
                            (report["run_id"], report["url"], report["timestamp"], json.dumps(report)))
    assert bridge.audit_evidence_status(d, 1, root)["status"] == "PARTIAL"
    # Reusing the old audit later does not make its observations newer.
    audit_event(d, older)
    assert bridge.audit_evidence_status(d, 1, root)["status"] == "PARTIAL"
    assert bridge.recover_evidence(d, [1], apply=True, toolkit_root=root)["recorded"] == 0


def test_legacy_stage_event_does_not_hide_recoverable_history_or_new_anchor(case):
    d, root, _ = case
    path, report = saved_report(root)
    d.execute("INSERT INTO pipeline_events VALUES(1,1,'AUDITED','{\"score\":20}',NULL)")
    with sqlite3.connect(root / "history.sqlite3") as history:
        history.execute("CREATE TABLE runs(id TEXT,url TEXT,timestamp TEXT,report TEXT)")
        history.execute("INSERT INTO runs VALUES(?,?,?,?)",
                        (report["run_id"], report["url"], report["timestamp"], json.dumps(report)))
    assert bridge.audit_evidence_status(d, 1, root)["status"] == "RECOVERABLE"
    result = bridge.recover_evidence(d, [1], apply=True, toolkit_root=root, report_path=path)
    assert result["recorded"] == 1
    assert bridge.audit_evidence_status(d, 1, root)["status"] == "CURRENT"


def test_cached_old_observation_cannot_be_renewed_by_new_run_timestamp(case):
    d, root, _ = case
    evidence = {"fetch": {"mode": "static", "data": {"status_code": 200},
                          "observed_at": (dt.datetime.now(core.UTC) - dt.timedelta(days=8)).isoformat()}}
    path, _ = saved_report(root, evidence=evidence)
    assert bridge.validate_report(d, 1, path, root)["status"] == "STALE"
    with pytest.raises(ValueError, match="STALE"):
        bridge.register_audit(d, 1, path, root)


def test_real_toolkit_report_with_observation_after_run_start_registers_offline(case):
    import httpx

    from auditor_toolkit.pipeline import AuditOptions, run_audit

    d, root, _ = case
    class FixtureFetcher:
        def get(self, url):
            return httpx.Response(200, text='<html><head><title>Fixture</title></head><body>Fixture service</body></html>',
                                  headers={"content-type": "text/html"}, request=httpx.Request("GET", url),
                                  extensions={"observed_at": core.now()})

    with patch("auditor_toolkit.pipeline.validate_url", return_value="https://fixture.example.co.nz"), \
            patch("socket.socket", side_effect=AssertionError("no network")):
        report = run_audit("https://fixture.example.co.nz", AuditOptions(output_root=root, tls=False),
                           fetcher=FixtureFetcher())
        assert report["status"] == "complete"
        assert core.timestamp(report["evidence"]["fetch"]["observed_at"]) > core.timestamp(report["timestamp"])
        result = bridge.register_audit(d, 1, report["artifacts"]["json"], root)
    assert result["recorded"]
    assert bridge.audit_evidence_status(d, 1, root)["status"] == "CURRENT"


@pytest.mark.parametrize("sql", [
    "CREATE TABLE contacts(business_id INTEGER,address_or_channel TEXT,do_not_contact INTEGER); INSERT INTO contacts VALUES(1,'blocked@example.invalid',1)",
    "CREATE TABLE mm_contact_evidence(business_id INTEGER,recipient TEXT,unsubscribe_state TEXT); INSERT INTO mm_contact_evidence VALUES(1,'blocked@example.invalid','unsubscribed')",
    "CREATE TABLE contacts(business_id INTEGER,address_or_channel TEXT); INSERT INTO contacts VALUES(1,'blocked@example.invalid'); CREATE TABLE mm_suppression(address TEXT); INSERT INTO mm_suppression VALUES('blocked@example.invalid')",
])
def test_contact_suppression_excludes_recovery_before_any_write(case, sql):
    d, root, _ = case
    path, _ = saved_report(root)
    d.executescript(sql)
    before = snapshot(d)
    result = bridge.recover_evidence(d, [1], apply=True, toolkit_root=root, report_path=path)
    assert result["results"][0]["status"] == "EXCLUDED"
    assert snapshot(d) == before


def test_operator_metrics_and_dashboard_keep_canonical_and_legacy_counts_separate():
    from test_evidence_ops import EvidenceOps

    fixture = EvidenceOps()
    fixture.setUp()
    try:
        root = fixture.r / "outputs" / "toolkit"
        path, _ = saved_report(root)
        # The real schema fixture's website matches the saved canonical run.
        bridge.register_audit(fixture.d, fixture.bid, path, root)
        excluded = fixture._extra_business()
        fixture.d.execute("UPDATE businesses SET suppression_reason='fixture suppression' WHERE id=?", (excluded,))
        fixture.d.commit()
        doc = operator.run_day(fixture.d, write=True)
        assert doc["metrics"]["prospects_without_legacy_observations"] == 1
        assert doc["metrics"]["eligible_without_current_audit_evidence"] == 0
        assert doc["audit_evidence"]["status_counts"] == {"CURRENT": 1, "EXCLUDED": 1}
        dashboard = fixture.r / "reports" / "daily-operator" / "index.html"
        assert "Canonical audit captures" in dashboard.read_text()
        assert "evidence-recover --ids ID" in dashboard.read_text()
    finally:
        fixture.tearDown()


@pytest.mark.parametrize("anchored", [False, True])
@pytest.mark.parametrize("newer_status", ["PARTIAL", "MISSING"])
def test_delayed_old_event_cannot_hide_newer_failed_event_without_history(case, anchored, newer_status):
    d, root, _ = case
    old_path, older = saved_report(
        root, timestamp=(dt.datetime.now(core.UTC) - dt.timedelta(hours=1)).isoformat(),
    )
    if anchored:
        bridge.register_audit(d, 1, old_path, root)
    newer_path, newer = saved_report(root, run_id="newer-event", status="partial")
    audit_event(d, newer)
    if newer_status == "MISSING":
        newer_path.unlink()
    assert bridge.audit_evidence_status(d, 1, root)["status"] == newer_status
    audit_event(d, older)
    before = snapshot(d)
    status = bridge.audit_evidence_status(d, 1, root)
    assert status["status"] == newer_status
    assert status["stage_signal"] and not status["complete"]
    result = bridge.recover_evidence(d, [1], apply=True, toolkit_root=root)
    assert result["results"][0]["status"] == newer_status
    assert result["recorded"] == 0
    assert snapshot(d) == before


def test_history_site_lookup_is_not_limited_by_unrelated_newer_runs(case):
    d, root, _ = case
    path, older = saved_report(
        root, timestamp=(dt.datetime.now(core.UTC) - dt.timedelta(hours=2)).isoformat(),
    )
    bridge.register_audit(d, 1, path, root)
    _, newer = saved_report(
        root, run_id="buried-new-partial", status="partial",
        timestamp=(dt.datetime.now(core.UTC) - dt.timedelta(hours=1)).isoformat(),
    )
    history_path = root / "history.sqlite3"
    with sqlite3.connect(history_path) as history:
        history.execute("CREATE TABLE runs(id TEXT,url TEXT,timestamp TEXT,report TEXT)")
        history.execute("INSERT INTO runs VALUES(?,?,?,?)", (
            newer["run_id"], "https://www.fixture.example.co.nz/", newer["timestamp"], json.dumps(newer),
        ))
        history.executemany("INSERT INTO runs VALUES(?,?,?,?)", [
            (f"unrelated-{index}", "https://unrelated.example.co.nz", core.now(), "{}")
            for index in range(2001)
        ])
    before = core.sha(history_path.read_bytes())
    assert bridge.audit_evidence_status(d, 1, root)["status"] == "PARTIAL"
    assert bridge.recover_evidence(d, [1], apply=True, toolkit_root=root)["recorded"] == 0
    assert core.sha(history_path.read_bytes()) == before


def test_explicit_preview_checks_registered_hash_and_matches_apply_without_writes(case):
    d, root, _ = case
    path, _ = saved_report(root)
    bridge.register_audit(d, 1, path, root)
    path.write_text(path.read_text() + " ")
    before = snapshot(d)
    preview = bridge.recover_evidence(d, [1], toolkit_root=root, report_path=path)
    applied = bridge.recover_evidence(d, [1], apply=True, toolkit_root=root, report_path=path)
    assert preview["results"][0]["status"] == applied["results"][0]["status"] == "INVALID"
    assert "changed" in preview["results"][0]["reason"]
    assert preview["recorded"] == applied["recorded"] == 0
    assert snapshot(d) == before


def test_explicit_unchanged_older_anchor_keeps_newer_failed_status_in_both_modes(case):
    d, root, _ = case
    path, _ = saved_report(
        root, timestamp=(dt.datetime.now(core.UTC) - dt.timedelta(hours=1)).isoformat(),
    )
    bridge.register_audit(d, 1, path, root)
    _, newer = saved_report(root, run_id="newer-partial", status="partial")
    audit_event(d, newer)
    before = snapshot(d)
    for apply in (False, True):
        result = bridge.recover_evidence(d, [1], apply=apply, toolkit_root=root, report_path=path)
        assert result["results"][0]["status"] == "PARTIAL"
        assert result["recorded"] == 0
    assert snapshot(d) == before


def test_legitimate_legacy_event_schema_remains_readable_without_migration(case):
    d, root, _ = case
    path, _ = saved_report(root)
    d.execute("DROP TABLE pipeline_events")
    d.execute("CREATE TABLE pipeline_events(id INTEGER PRIMARY KEY,business_id INTEGER,stage TEXT,event_at TEXT,detail TEXT)")
    d.execute("INSERT INTO pipeline_events VALUES(1,1,'AUDITED',?,'legacy observation')", (core.now(),))
    d.commit()
    before = snapshot(d)
    assert bridge.audit_evidence_status(d, 1, root)["status"] == "MISSING"
    bridge.register_audit(d, 1, path, root)
    assert bridge.audit_evidence_status(d, 1, root)["status"] == "CURRENT"
    assert not bridge.audit_evidence_status(d, 1, root)["stage_signal"]
    after = snapshot(d)
    assert {table: after[table] for table in before} == before


@pytest.mark.parametrize("table,columns", [
    ("pipeline_items", "state TEXT"),
    ("mm_deals", "business_id INTEGER"),
    ("mm_holds", "reason TEXT"),
    ("mm_evidence", "checked_at TEXT"),
    ("pipeline_events", "business_id INTEGER,to_state TEXT,evidence TEXT"),
    ("mm_audit_evidence", "report_hash TEXT"),
    ("contacts", "do_not_contact INTEGER"),
    ("mm_contact_evidence", "recipient TEXT"),
    ("mm_suppression", "reason TEXT"),
])
def test_incompatible_optional_schema_fails_closed_without_artifact_reads_or_writes(case, table, columns):
    d, root, _ = case
    path, _ = saved_report(root)
    d.execute(f"DROP TABLE IF EXISTS {table}")
    d.execute(f"CREATE TABLE {table}({columns})")
    d.commit()
    before = snapshot(d)
    with patch.object(bridge, "validate_report", side_effect=AssertionError("invalid schema must guard artifact reads")):
        status = bridge.audit_evidence_status(d, 1, root)
        assert status["status"] == "INVALID" and status["schema_valid"] is False
        assert table in status["reason"]
        for apply in (False, True):
            result = bridge.recover_evidence(d, [1], apply=apply, toolkit_root=root, report_path=path)
            assert result["results"][0]["status"] == "INVALID"
            assert result["recorded"] == 0
        with pytest.raises(bridge.EvidenceSchemaError, match=table):
            bridge.register_audit(d, 1, path, root)
    assert snapshot(d) == before


@pytest.mark.parametrize("schema", ["missing", "incompatible", "unsupported", "corrupt"])
def test_unreadable_history_cannot_fall_back_to_current_anchor(case, schema):
    d, root, _ = case
    path, _ = saved_report(root)
    bridge.register_audit(d, 1, path, root)
    history_path = root / "history.sqlite3"
    if schema == "corrupt":
        history_path.write_bytes(b"invalid SQLite history")
    else:
        with sqlite3.connect(history_path) as history:
            if schema == "incompatible":
                history.execute("CREATE TABLE runs(id TEXT,url TEXT)")
            elif schema == "unsupported":
                history.execute("CREATE TABLE runs(id TEXT,url TEXT,timestamp TEXT)")
                history.execute("PRAGMA user_version=2")
    before = snapshot(d)
    history_hash = core.sha(history_path.read_bytes())
    status = bridge.audit_evidence_status(d, 1, root)
    assert status["status"] == "INVALID" and status["schema_valid"] is False
    assert not status["complete"]
    assert bridge.recover_evidence(d, [1], apply=True, toolkit_root=root)["recorded"] == 0
    assert snapshot(d) == before
    assert core.sha(history_path.read_bytes()) == history_hash


def test_unorderable_exact_site_history_timestamp_cannot_hide_behind_current_anchor(case):
    from auditor_toolkit.storage import History

    d, root, _ = case
    path, older = saved_report(
        root, run_id="older-valid", timestamp=(dt.datetime.now(core.UTC) - dt.timedelta(hours=1)).isoformat(),
    )
    newer_path, newer = saved_report(root, run_id="newer-invalid", timestamp="broken")
    history = History(root)
    history.save(older)
    history.save(newer)
    bridge.register_audit(d, 1, path, root)
    before = snapshot(d)
    history_hash = core.sha(history.path.read_bytes())
    assert bridge.validate_report(d, 1, newer_path, root)["status"] == "INVALID"
    status = bridge.audit_evidence_status(d, 1, root)
    assert status["status"] == "INVALID" and not status["complete"]
    assert "timestamp" in status["reason"]
    assert bridge.recover_evidence(d, [1], apply=True, toolkit_root=root)["recorded"] == 0
    assert snapshot(d) == before
    assert core.sha(history.path.read_bytes()) == history_hash


def test_history_orders_mixed_timezone_timestamps_by_capture_time_and_ignores_other_sites(case):
    d, root, _ = case
    older_stamp = (dt.datetime.now(core.UTC) - dt.timedelta(hours=1)).astimezone(
        dt.timezone(dt.timedelta(hours=13)),
    ).isoformat()
    path, older = saved_report(root, run_id="older-offset", timestamp=older_stamp)
    bridge.register_audit(d, 1, path, root)
    newer_stamp = (dt.datetime.now(core.UTC) - dt.timedelta(minutes=30)).astimezone(
        dt.timezone(dt.timedelta(hours=-4)),
    ).isoformat()
    _, newer = saved_report(root, run_id="newer-offset", timestamp=newer_stamp, status="partial")
    with sqlite3.connect(root / "history.sqlite3") as history:
        history.execute("CREATE TABLE runs(id TEXT,url TEXT,timestamp TEXT,report TEXT)")
        for report in (older, newer):
            history.execute("INSERT INTO runs VALUES(?,?,?,?)", (
                report["run_id"], report["url"], report["timestamp"], json.dumps(report),
            ))
        history.execute("INSERT INTO runs VALUES('unrelated-invalid','https://other.example.co.nz','broken','{}')")
    status = bridge.audit_evidence_status(d, 1, root)
    assert status["status"] == "PARTIAL" and status["run_id"] == newer["run_id"]


@pytest.mark.parametrize("column,value", [("suppression_reason", "late suppression"), ("current_status", "REJECTED")])
def test_concurrent_exclusion_during_validation_prevents_schema_and_anchor_write(case, column, value):
    d, root, db_path = case
    path, _ = saved_report(root)
    validate = bridge.validate_report
    def validate_then_exclude(*args, **kwargs):
        checked = validate(*args, **kwargs)
        with sqlite3.connect(db_path) as concurrent:
            concurrent.execute(f"UPDATE businesses SET {column}=? WHERE id=1", (value,))
        return checked
    with patch.object(bridge, "validate_report", side_effect=validate_then_exclude):
        with pytest.raises(ValueError, match="suppressed|rejected"):
            bridge.register_audit(d, 1, path, root)
    assert not bridge._columns(d, "mm_audit_evidence")
    assert not d.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'mm_audit_evidence_%'").fetchone()
    assert d.execute(f"SELECT {column} FROM businesses WHERE id=1").fetchone()[0] == value
