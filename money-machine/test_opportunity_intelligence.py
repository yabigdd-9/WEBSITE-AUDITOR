"""Tests for v45 shadow opportunity intelligence.

Synthetic/local only: no network, no model calls, no external sends.
"""
import json
import sqlite3

import mm_opportunity_intelligence as oi
import mm_workers as workers


def test_identity_confidence_high_with_aligned_first_party_signals():
    result = oi.identity_confidence({
        "name": "Acme Plumbing",
        "public_website": "https://acmeplumbing.co.nz",
        "region": "Canterbury",
        "source": "searxng-local:abc123",
    })
    assert result["status"] == "HIGH"
    assert result["confidence"] >= 0.75
    assert result["requires_review"] is False
    assert "public_host_present" in result["supporting_signals"]


def test_weak_name_domain_match_is_unknown_not_conflict():
    result = oi.identity_confidence({
        "name": "Acme Plumbing",
        "public_website": "https://example-services.co.nz",
        "region": "Canterbury",
        "source": "searxng-local:abc123",
    })
    assert result["status"] != "CONFLICTED"
    assert "name_domain_alignment" in result["missing_signals"]
    assert result["contradicting_signals"] == []


def test_identity_confidence_low_when_identity_is_missing():
    result = oi.identity_confidence({
        "name": "Unknown Business",
        "public_website": "",
        "region": "",
        "source": "",
    })
    assert result["status"] == "LOW"
    assert result["requires_review"] is True
    assert "canonical_host" in result["missing_signals"]


def test_identity_conflict_for_discovery_reject():
    result = oi.identity_confidence(
        {
            "name": "Acme Plumbing",
            "public_website": "https://acmeplumbing.co.nz",
            "region": "Canterbury",
            "source": "searxng-local:abc123",
        },
        evidence={
            "discovery_quality": {
                "disposition": "REJECT",
                "classification": "DIRECTORY",
            }
        },
    )
    assert result["status"] == "CONFLICTED"
    assert result["requires_review"] is True
    assert any(x.startswith("discovery_quality_reject:") for x in result["contradicting_signals"])


def test_missing_evidence_is_unknown_not_negative():
    result = oi.evidence_completeness(
        "QUALIFICATION_PENDING",
        {"business_name", "canonical_host", "audit"},
    )
    assert result["status"] == "INCOMPLETE"
    assert "commercial_evidence" in result["missing"]
    assert "unknown" in result["interpretation"].lower()
    assert result["completeness"] == 0.75


def test_next_best_evidence_prefers_commercial_evidence_when_identity_is_strong():
    identity = {
        "confidence": 0.9,
        "contradicting_signals": [],
        "missing_signals": [],
    }
    completeness = {
        "missing": ["commercial_evidence"],
    }
    plan = oi.next_best_evidence(identity, completeness)
    assert plan["action"] == "INSPECT_FIRST_PARTY_COMMERCIAL_PAGES"
    assert plan["execute"] is False
    assert plan["information_gain"] >= 0.9


def test_next_best_evidence_conflict_requires_human_review():
    plan = oi.next_best_evidence(
        {
            "confidence": 0.8,
            "contradicting_signals": ["name_domain_conflict"],
            "missing_signals": [],
        },
        {"missing": []},
    )
    assert plan["action"] == "HUMAN_IDENTITY_REVIEW"
    assert plan["execute"] is False


def _db():
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
          canonical_host TEXT,
          is_dummy INTEGER DEFAULT 0
        );
        CREATE TABLE pipeline_items(
          business_id INTEGER PRIMARY KEY,
          state TEXT,
          payload TEXT
        );
        CREATE TABLE pipeline_events(
          id INTEGER PRIMARY KEY,
          business_id INTEGER,
          from_state TEXT,
          to_state TEXT,
          actor TEXT,
          reason TEXT,
          evidence TEXT,
          event_at TEXT
        );
        CREATE TABLE prospect_outcomes(
          id INTEGER PRIMARY KEY,
          business_id INTEGER,
          outcome TEXT
        );
        """
    )
    return d


def test_prospect_snapshot_exposes_identity_completeness_and_planner():
    d = _db()
    d.execute(
        "INSERT INTO businesses VALUES(1,?,?,?,?,?,0)",
        (
            "Acme Plumbing",
            "https://acmeplumbing.co.nz",
            "Canterbury",
            "searxng-local:abc123",
            "acmeplumbing.co.nz",
        ),
    )
    d.execute(
        "INSERT INTO pipeline_items VALUES(1,'QUALIFICATION_PENDING','{}')"
    )
    d.execute(
        "INSERT INTO pipeline_events VALUES(1,1,'AUDIT_PENDING','AUDITED','worker','ok',?,?)",
        (json.dumps({"score": 50, "defect_count": 3}), "2026-09-30T00:00:00+00:00"),
    )
    result = oi.prospect_snapshot(d, 1)
    assert result["business_id"] == 1
    assert result["identity"]["status"] == "HIGH"
    assert "audit" in result["observed_evidence"]
    assert result["evidence_completeness"]["status"] == "INCOMPLETE"
    assert "commercial_evidence" in result["evidence_completeness"]["missing"]
    assert result["next_best_evidence"]["action"] == "INSPECT_FIRST_PARTY_COMMERCIAL_PAGES"
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0


def test_source_query_summary_tracks_yield_rejection_and_outcomes():
    d = _db()
    businesses = [
        (1, "A", "https://a.co.nz", "Canterbury", "searxng-local:q1", "a.co.nz", 0),
        (2, "B", "https://b.co.nz", "Canterbury", "searxng-local:q1", "b.co.nz", 0),
        (3, "C", "https://c.co.nz", "Canterbury", "import:nzbn", "c.co.nz", 0),
        (4, "Dummy", "https://dummy.co.nz", "Canterbury", "searxng-local:q1", "dummy.co.nz", 1),
    ]
    d.executemany("INSERT INTO businesses VALUES(?,?,?,?,?,?,?)", businesses)
    d.executemany(
        "INSERT INTO pipeline_items VALUES(?,?,?)",
        [
            (1, "QUALIFIED", "{}"),
            (2, "REJECTED", "{}"),
            (3, "CONTACT_PENDING", "{}"),
            (4, "QUALIFIED", "{}"),
        ],
    )
    d.executemany(
        "INSERT INTO prospect_outcomes(id,business_id,outcome) VALUES(?,?,?)",
        [
            (1, 1, "REPLIED"),
            (2, 1, "WON"),
            (3, 3, "REPLIED"),
        ],
    )

    result = oi.source_query_summary(d)
    assert result["business_count"] == 3
    assert result["source_count"] == 2
    q1 = next(x for x in result["sources"] if x["source"] == "searxng-local:q1")
    assert q1["query_fingerprint"] == "q1"
    assert q1["total"] == 2
    assert q1["qualified_businesses"] == 1
    assert q1["negative_terminal_businesses"] == 1
    assert q1["won_businesses"] == 1
    assert q1["qualification_yield"] == 0.5
    assert q1["negative_terminal_rate"] == 0.5
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0


def test_source_query_summary_works_without_optional_tables():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.execute(
        "CREATE TABLE businesses(id INTEGER PRIMARY KEY,name TEXT,source TEXT,is_dummy INTEGER DEFAULT 0)"
    )
    d.execute("INSERT INTO businesses VALUES(1,'A','import:manual',0)")
    result = oi.source_query_summary(d)
    assert result["business_count"] == 1
    assert result["sources"][0]["states"] == {"UNTRACKED": 1}


def test_identity_worker_adds_shadow_without_changing_transition():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.execute(
        """CREATE TABLE businesses(
        id INTEGER PRIMARY KEY,name TEXT,public_website TEXT,region TEXT,
        source TEXT,canonical_host TEXT,is_dummy INTEGER DEFAULT 0)"""
    )
    d.execute(
        "INSERT INTO businesses VALUES(1,?,?,?,?,?,0)",
        (
            "Acme Plumbing",
            "https://acmeplumbing.co.nz",
            "Canterbury",
            "searxng-local:q1",
            None,
        ),
    )
    nxt, reason, evidence = workers.identity_handler(d, {"business_id": 1}, None)
    assert nxt == "AUDIT_PENDING"
    assert reason == "identity resolved from declared website"
    assert evidence["canonical_host"] == "acmeplumbing.co.nz"
    assert evidence["shadow_intelligence"]["shadow_only"] is True
    assert evidence["shadow_intelligence"]["identity"]["status"] == "HIGH"


def test_qualification_shadow_marks_commercial_gap_without_changing_verdict(monkeypatch):
    import mm_lead_qualifier as lq

    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.executescript(
        """CREATE TABLE businesses(
        id INTEGER PRIMARY KEY,name TEXT,public_website TEXT,region TEXT,
        source TEXT,canonical_host TEXT,is_dummy INTEGER DEFAULT 0);
        CREATE TABLE pipeline_events(
        id INTEGER PRIMARY KEY,business_id INTEGER,from_state TEXT,to_state TEXT,
        actor TEXT,reason TEXT,evidence TEXT,event_at TEXT);"""
    )
    d.execute(
        "INSERT INTO businesses VALUES(1,?,?,?,?,?,0)",
        (
            "Acme Plumbing",
            "https://acmeplumbing.co.nz",
            "Canterbury",
            "searxng-local:q1",
            "acmeplumbing.co.nz",
        ),
    )
    d.execute(
        "INSERT INTO pipeline_events VALUES(1,1,'IDENTITY_PENDING','IDENTITY_RESOLVED','w','ok',?,?)",
        (json.dumps({"canonical_host": "acmeplumbing.co.nz"}), "2026-09-30T00:00:00+00:00"),
    )
    d.execute(
        "INSERT INTO pipeline_events VALUES(2,1,'AUDIT_PENDING','AUDITED','w','ok',?,?)",
        (json.dumps({"score": 10, "defect_count": 1}), "2026-09-30T00:01:00+00:00"),
    )
    monkeypatch.setattr(
        lq,
        "qualify_lead",
        lambda text, industry="": {
            "qualification_score": 0,
            "tier": "COLD",
            "reasons": ["synthetic no commercial evidence"],
        },
    )
    nxt, reason, evidence = workers.qualification_handler(
        d, {"business_id": 1}, None
    )
    assert nxt == "REJECTED"
    assert reason.startswith("not qualified:")
    shadow = evidence["shadow_intelligence"]
    assert "commercial_evidence" in shadow["evidence_completeness"]["missing"]
    assert (
        shadow["next_best_evidence"]["action"]
        == "INSPECT_FIRST_PARTY_COMMERCIAL_PAGES"
    )
    assert shadow["paid_calls"] == 0
    assert shadow["external_sends"] == 0
