"""Tests for the read-only v45 intelligence evidence graph."""
import json
import sqlite3

import mm_intelligence_graph as graph


def fresh_db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.executescript(
        """
        CREATE TABLE businesses(
          id INTEGER PRIMARY KEY,
          name TEXT,
          public_website TEXT,
          region TEXT,
          source TEXT,
          current_status TEXT,
          is_dummy INTEGER DEFAULT 0
        );
        CREATE TABLE pipeline_events(
          id INTEGER PRIMARY KEY,
          business_id INTEGER NOT NULL,
          from_state TEXT,
          to_state TEXT NOT NULL,
          actor TEXT NOT NULL,
          reason TEXT NOT NULL,
          evidence TEXT,
          event_at TEXT NOT NULL
        );
        CREATE TABLE intelligence_ledger(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          prospect_id INTEGER NOT NULL,
          business_name TEXT NOT NULL,
          domain TEXT NOT NULL,
          candidate_url TEXT,
          source TEXT,
          query_fingerprint TEXT,
          industry TEXT,
          region TEXT,
          raw_evidence_refs TEXT,
          derived_evidence TEXT,
          decision TEXT NOT NULL,
          disposition TEXT,
          primary_reason TEXT,
          secondary_reasons TEXT,
          confidence REAL,
          rule_version TEXT NOT NULL,
          stage TEXT,
          processing_cost REAL DEFAULT 0,
          latency_seconds REAL DEFAULT 0,
          errors TEXT,
          human_correction TEXT,
          later_outcome TEXT,
          recorded_at TEXT NOT NULL
        );
        CREATE TABLE intelligence_rejections(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          prospect_id INTEGER NOT NULL,
          business_name TEXT NOT NULL,
          domain TEXT NOT NULL,
          primary_reason TEXT NOT NULL,
          secondary_reasons TEXT,
          stage TEXT,
          disposition TEXT,
          supporting_evidence TEXT,
          contradicting_evidence TEXT,
          missing_evidence TEXT,
          confidence REAL,
          rule_version TEXT NOT NULL,
          retryable INTEGER NOT NULL DEFAULT 0,
          decision_detail TEXT,
          recorded_at TEXT NOT NULL
        );
        CREATE TABLE prospect_outcomes(
          id INTEGER PRIMARY KEY,
          business_id INTEGER NOT NULL,
          outcome TEXT NOT NULL,
          observed_at TEXT NOT NULL,
          actor TEXT NOT NULL,
          evidence_path TEXT NOT NULL,
          evidence_hash TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        );
        """
    )
    d.execute(
        "INSERT INTO businesses VALUES(1,?,?,?,?,?,0)",
        (
            "Acme Plumbing",
            "https://acmeplumbing.co.nz",
            "Canterbury",
            "searxng-local:q1",
            "qualified",
        ),
    )
    return d


def test_graph_requires_existing_business():
    d = fresh_db()
    try:
        graph.prospect_graph(d, 999)
    except ValueError as exc:
        assert "Business not found" in str(exc)
    else:
        raise AssertionError("Expected missing business to fail closed")


def test_minimal_graph_has_source_and_business_without_mutation():
    d = fresh_db()
    before = d.total_changes

    result = graph.prospect_graph(d, 1)

    assert result["node_count"] == 2
    assert result["node_counts"] == {"business": 1, "source": 1}
    assert result["read_only"] is True
    assert result["raw_payloads_included"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
    assert d.total_changes == before
    assert {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    } == {
        ("source:searxng-local:q1", "business:1", "DISCOVERED")
    }


def test_pipeline_events_are_ordered_and_raw_secrets_are_not_copied():
    d = fresh_db()
    evidence_one = {
        "canonical_host": "acmeplumbing.co.nz",
        "token": "DO-NOT-COPY",
        "api_key": "DO-NOT-COPY",
    }
    evidence_two = {
        "score": 72,
        "defect_count": 4,
        "recipient": "private@example.com",
        "external_sends": 0,
    }
    d.executemany(
        "INSERT INTO pipeline_events VALUES(?,?,?,?,?,?,?,?)",
        [
            (
                10, 1, "DISCOVERED", "IDENTITY_RESOLVED", "identity-worker",
                "identity resolved", json.dumps(evidence_one),
                "2026-09-30T00:00:00Z",
            ),
            (
                11, 1, "AUDIT_PENDING", "AUDITED", "audit-worker",
                "audit complete", json.dumps(evidence_two),
                "2026-09-30T00:01:00Z",
            ),
        ],
    )

    result = graph.prospect_graph(d, 1)
    events = [node for node in result["nodes"] if node["kind"] == "pipeline_event"]

    assert [node["data"]["event_id"] for node in events] == [10, 11]
    assert events[0]["data"]["evidence"] == {
        "canonical_host": "acmeplumbing.co.nz"
    }
    assert events[1]["data"]["evidence"] == {
        "defect_count": 4,
        "external_sends": 0,
        "score": 72,
    }
    serialized = json.dumps(result)
    assert "DO-NOT-COPY" not in serialized
    assert "private@example.com" not in serialized
    assert {
        "source": "pipeline_event:10",
        "target": "pipeline_event:11",
        "relation": "NEXT_PIPELINE_EVENT",
    } in result["edges"]


def test_graph_connects_decisions_rejections_and_outcomes():
    d = fresh_db()
    d.execute(
        """INSERT INTO intelligence_ledger(
        prospect_id,business_name,domain,raw_evidence_refs,derived_evidence,
        decision,disposition,primary_reason,secondary_reasons,confidence,
        rule_version,stage,processing_cost,latency_seconds,errors,recorded_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            1, "Acme Plumbing", "acmeplumbing.co.nz", "[]",
            json.dumps({
                "technical_score": 80,
                "commercial_score": 35,
                "secret": "DO-NOT-COPY",
            }),
            "QUALIFIED", "ACCEPTED", "", "[]", 0.85, "v45.2",
            "qualification", 0, 0, "[]", "2026-09-30T00:02:00Z",
        ),
    )
    d.execute(
        """INSERT INTO intelligence_rejections(
        prospect_id,business_name,domain,primary_reason,secondary_reasons,
        stage,disposition,supporting_evidence,contradicting_evidence,
        missing_evidence,confidence,rule_version,retryable,decision_detail,
        recorded_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            1, "Acme Plumbing", "acmeplumbing.co.nz",
            "INSUFFICIENT_COMMERCIAL_EVIDENCE", "[]", "qualification",
            "REVIEW", "[]", "[]", "[]", 0.3, "v45.1", 1,
            "raw detail not copied", "2026-09-30T00:01:30Z",
        ),
    )
    d.execute(
        "INSERT INTO prospect_outcomes VALUES(1,?,?,?,?,?,?,?,?)",
        (
            1, "REPLIED", "2026-09-30T00:03:00Z", "human",
            "/private/workspace/evidence.txt", "abc123", "private note",
            "2026-09-30T00:03:01Z",
        ),
    )

    result = graph.prospect_graph(d, 1)

    assert result["node_counts"]["decision"] == 1
    assert result["node_counts"]["rejection"] == 1
    assert result["node_counts"]["outcome"] == 1

    decision = next(node for node in result["nodes"] if node["kind"] == "decision")
    assert decision["data"]["derived_evidence"] == {
        "commercial_score": 35,
        "technical_score": 80,
    }

    outcome = next(node for node in result["nodes"] if node["kind"] == "outcome")
    assert outcome["data"]["evidence_ref"] == "outcome-evidence:1"
    assert outcome["data"]["evidence_hash_present"] is True
    assert outcome["data"]["note_present"] is True

    serialized = json.dumps(result)
    assert "/private/workspace/evidence.txt" not in serialized
    assert "private note" not in serialized
    assert "raw detail not copied" not in serialized
    assert "DO-NOT-COPY" not in serialized


def test_correction_and_outcome_observation_have_distinct_node_types():
    d = fresh_db()
    rows = [
        (
            1, "Acme Plumbing", "acmeplumbing.co.nz", "[]", "{}",
            "REJECTED", "", "INSUFFICIENT_COMMERCIAL_EVIDENCE", "[]",
            0.8, "v45.1", "qualification", 0, 0, "[]", None, None,
            "2026-09-30T00:00:00Z",
        ),
        (
            1, "Acme Plumbing", "acmeplumbing.co.nz", "[]", "{}",
            "QUALIFIED", "HUMAN_CORRECTED", "human_correction", "[]",
            0.95, "v45.1", "qualification", 0, 0, "[]",
            "manual correction", None, "2026-09-30T00:01:00Z",
        ),
        (
            1, "Acme Plumbing", "acmeplumbing.co.nz", "[]", "{}",
            "QUALIFIED", "OUTCOME_OBSERVED", "", "[]",
            0.5, "v45.1", "outcome", 0, 0, "[]",
            None, "WON", "2026-09-30T00:02:00Z",
        ),
    ]
    d.executemany(
        """INSERT INTO intelligence_ledger(
        prospect_id,business_name,domain,raw_evidence_refs,derived_evidence,
        decision,disposition,primary_reason,secondary_reasons,confidence,
        rule_version,stage,processing_cost,latency_seconds,errors,
        human_correction,later_outcome,recorded_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )

    result = graph.prospect_graph(d, 1)
    kinds = [node["kind"] for node in result["nodes"]]

    assert "decision" in kinds
    assert "correction" in kinds
    assert "outcome_observation" in kinds
    assert {
        "source": "decision:1",
        "target": "decision:2",
        "relation": "NEXT_DECISION_OBSERVATION",
    } in result["edges"]


def test_graph_works_when_optional_intelligence_tables_are_absent():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.execute(
        """CREATE TABLE businesses(
        id INTEGER PRIMARY KEY,name TEXT,public_website TEXT,region TEXT,
        source TEXT,current_status TEXT,is_dummy INTEGER DEFAULT 0)"""
    )
    d.execute(
        "INSERT INTO businesses VALUES(1,'A','https://a.co.nz','NZ','import','new',0)"
    )

    result = graph.prospect_graph(d, 1)

    assert result["node_counts"] == {"business": 1, "source": 1}
    assert result["node_count"] == 2
