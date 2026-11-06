"""Read-only CLI regression for the already-implemented freshness reporter."""

import json
import sqlite3

import mm_intelligence_ledger as ledger
import mm_operator as operator
import pytest


def _read_only_conn(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def test_freshness_cli_empty_database_has_no_side_effects(tmp_path, monkeypatch, capsys):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    monkeypatch.setattr(
        operator, "connect", lambda readonly=True: _read_only_conn(path)
    )

    assert operator.main(["intelligence-freshness"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["confirmed_examples"] == 0
    assert result["read_only"] is True
    assert result["automatic_label_expiry"] is False
    assert result["automatic_rule_change"] is False
    assert result["promotion_authorized"] is False
    assert result["paid_calls"] == result["external_sends"] == 0
    with _read_only_conn(path) as db:
        assert db.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


def test_freshness_cli_reports_stale_confirmation_without_mutating(tmp_path, monkeypatch, capsys):
    path = tmp_path / "confirmed.db"
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        ledger.append_decision(
            db,
            ledger.IntelligenceDecision(
                prospect_id=1,
                business_name="Fixture",
                domain="fixture.example",
                decision="QUALIFIED",
                confidence=0.9,
                stage="qualification",
            ),
        )
        ledger.append_decision(
            db,
            ledger.IntelligenceDecision(
                prospect_id=1,
                business_name="Fixture",
                domain="fixture.example",
                decision="QUALIFIED",
                disposition="OUTCOME_OBSERVED",
                confidence=0.9,
                stage="outcome",
                later_outcome="WON",
            ),
        )
        original_count = db.execute(
            "SELECT count(*) FROM intelligence_ledger"
        ).fetchone()[0]
    monkeypatch.setattr(
        operator, "connect", lambda readonly=True: _read_only_conn(path)
    )

    assert operator.main([
        "intelligence-freshness",
        "--as-of", "2030-01-01T00:00:00+00:00",
        "--min-confirmed", "1",
        "--stale-after-days", "1",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["reference_source"] == "explicit"
    assert result["confirmed_examples"] == 1
    assert result["status"] == "FRESHNESS_WARNINGS"
    assert "STALE_LABELS" in result["flags"]
    assert result["promotion_authorized"] is False
    assert result["automatic_rule_change"] is False
    assert result["external_sends"] == result["paid_calls"] == 0
    with _read_only_conn(path) as db:
        assert db.execute(
            "SELECT count(*) FROM intelligence_ledger"
        ).fetchone()[0] == original_count


def test_freshness_cli_rejects_invalid_reference_time(tmp_path, monkeypatch):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    monkeypatch.setattr(
        operator, "connect", lambda readonly=True: _read_only_conn(path)
    )
    with pytest.raises(ValueError, match="ISO-8601"):
        operator.main(["intelligence-freshness", "--as-of", "not-a-date"])
