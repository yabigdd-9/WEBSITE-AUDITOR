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


def test_prospect_snapshot_uses_discovery_payload_identity_evidence():
    d = _db()
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
    payload = {
        "legal_name": "Acme Plumbing Limited",
        "trading_name": "Acme Plumbing",
        "nzbn": "9429000000000",
        "discovery_quality": {
            "disposition": "ACCEPT",
            "classification": "BUSINESS_HOME",
        },
    }
    d.execute(
        "INSERT INTO pipeline_items VALUES(1,'IDENTITY_PENDING',?)",
        (json.dumps(payload),),
    )
    result = oi.prospect_snapshot(d, 1)
    signals = result["identity"]["supporting_signals"]
    assert "legal_or_trading_name_present" in signals
    assert "nzbn_present" in signals
    assert "discovery_quality_accept" in signals
    assert result["identity"]["status"] == "HIGH"


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


def test_counterfactual_explains_current_thresholds_without_auto_action():
    assessment = {
        "identity": {
            "status": "HIGH",
            "confidence": 0.9,
        },
        "evidence_completeness": {
            "missing": ["commercial_evidence"],
        },
    }
    result = oi.counterfactual_explanation(
        "REJECTED",
        assessment,
        {"commercial_score": 20, "technical_score": 35},
    )
    axes = {
        item.get("axis"): item
        for item in result["counterfactuals"]
        if item.get("kind") == "CURRENT_RULE_THRESHOLD"
    }
    assert axes["commercial"]["threshold"] == 30.0
    assert axes["commercial"]["gap"] == 10.0
    assert axes["technical"]["threshold"] == 40.0
    assert axes["technical"]["gap"] == 5.0
    assert any(
        item.get("field") == "commercial_evidence"
        for item in result["counterfactuals"]
    )
    assert result["automatic_action"] is False
    assert result["explanatory_only"] is True
    assert all(
        item["guarantees_decision_change"] is False
        for item in result["counterfactuals"]
    )


def test_counterfactual_keeps_unknown_technical_axis_unknown():
    assessment = {
        "identity": {
            "status": "HIGH",
            "confidence": 0.9,
        },
        "evidence_completeness": {
            "missing": ["audit"],
        },
    }
    result = oi.counterfactual_explanation(
        "REJECTED",
        assessment,
        {"commercial_score": 10, "technical_score": None},
    )
    assert any(
        item.get("kind") == "UNKNOWN_AXIS" and item.get("axis") == "technical"
        for item in result["counterfactuals"]
    )
    assert any(
        item.get("field") == "audit"
        for item in result["counterfactuals"]
    )


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
    assert result["counterfactual"]["automatic_action"] is False
    assert result["counterfactual"]["explanatory_only"] is True
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0


def test_numeric_commercial_score_alone_is_not_substantive_evidence():
    d = _db()
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
        "INSERT INTO pipeline_items VALUES(1,'QUALIFICATION_PENDING','{}')"
    )
    d.execute(
        "INSERT INTO pipeline_events VALUES(1,1,'IDENTITY_RESOLVED','AUDIT_PENDING','w','ok',?,?)",
        (json.dumps({"canonical_host": "acmeplumbing.co.nz"}), "2026-09-30T00:00:00+00:00"),
    )
    d.execute(
        "INSERT INTO pipeline_events VALUES(2,1,'AUDIT_PENDING','AUDITED','w','ok',?,?)",
        (json.dumps({"score": 25, "defect_count": 2}), "2026-09-30T00:01:00+00:00"),
    )
    d.execute(
        "INSERT INTO pipeline_events VALUES(3,1,'AUDITED','QUALIFICATION_PENDING','w','legacy',?,?)",
        (
            json.dumps({
                "commercial_score": 25,
                "technical_score": 25,
                "commercial_opportunity": None,
            }),
            "2026-09-30T00:02:00+00:00",
        ),
    )

    result = oi.prospect_snapshot(d, 1)

    assert "commercial_evidence" not in result["observed_evidence"]
    assert "commercial_evidence" in result["evidence_completeness"]["missing"]
    assert (
        result["next_best_evidence"]["action"]
        == "INSPECT_FIRST_PARTY_COMMERCIAL_PAGES"
    )


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
    assert q1["diagnostic"]["signal"] == "INSUFFICIENT_SAMPLE"
    assert q1["diagnostic"]["automatic_action"] is False
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0


def test_intelligence_summary_is_bounded_read_only_and_zero_cost():
    d = _db()
    d.executemany(
        "INSERT INTO businesses VALUES(?,?,?,?,?,?,?)",
        [
            (
                1, "Acme Plumbing", "https://acmeplumbing.co.nz",
                "Canterbury", "searxng-local:q1", "acmeplumbing.co.nz", 0,
            ),
            (
                2, "Beta Electrical", "https://betaelectrical.co.nz",
                "Canterbury", "import:manual", "betaelectrical.co.nz", 0,
            ),
        ],
    )
    d.executemany(
        "INSERT INTO pipeline_items VALUES(?,?,?)",
        [
            (1, "REJECTED", "{}"),
            (2, "QUALIFIED", "{}"),
        ],
    )

    result = oi.intelligence_summary(d, limit=10)

    assert result["prospects_assessed"] == 2
    assert result["truncated"] is False
    assert result["source_count"] == 2
    assert result["automatic_action"] is False
    assert result["shadow_only"] is True
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0
    assert sum(result["identity_status"].values()) == 2


def test_intelligence_summary_reports_true_truncation_only():
    d = _db()
    d.executemany(
        "INSERT INTO businesses VALUES(?,?,?,?,?,?,?)",
        [
            (
                1, "A", "https://a.co.nz", "Canterbury",
                "import:a", "a.co.nz", 0,
            ),
            (
                2, "B", "https://b.co.nz", "Canterbury",
                "import:b", "b.co.nz", 0,
            ),
        ],
    )
    first = oi.intelligence_summary(d, limit=1)
    all_rows = oi.intelligence_summary(d, limit=2)
    assert first["prospects_assessed"] == 1
    assert first["truncated"] is True
    assert all_rows["prospects_assessed"] == 2
    assert all_rows["truncated"] is False


def test_shadow_review_queue_is_read_only_and_surfaces_incomplete_rejection():
    d = _db()
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
        "INSERT INTO pipeline_items VALUES(1,'REJECTED','{}')"
    )
    d.execute(
        "INSERT INTO pipeline_events VALUES(1,1,'IDENTITY_PENDING','IDENTITY_RESOLVED','w','ok',?,?)",
        (json.dumps({"canonical_host": "acmeplumbing.co.nz"}), "2026-09-30T00:00:00+00:00"),
    )
    d.execute(
        "INSERT INTO pipeline_events VALUES(2,1,'AUDIT_PENDING','AUDITED','w','ok',?,?)",
        (json.dumps({"score": 35, "defect_count": 2}), "2026-09-30T00:01:00+00:00"),
    )
    before = d.execute(
        "SELECT state FROM pipeline_items WHERE business_id=1"
    ).fetchone()["state"]

    result = oi.shadow_review_queue(d, limit=10)

    after = d.execute(
        "SELECT state FROM pipeline_items WHERE business_id=1"
    ).fetchone()["state"]
    assert before == "REJECTED"
    assert after == "REJECTED"
    assert result["count"] == 1
    item = result["items"][0]
    assert item["business_id"] == 1
    assert item["state"] == "REJECTED"
    assert item["automatic_action"] is False
    snapshot = oi.prospect_snapshot(d, 1)
    assert snapshot["state"] == "REJECTED"
    assert snapshot["assessment_stage"] == "QUALIFICATION_PENDING"
    assert "commercial_evidence" in snapshot["evidence_completeness"]["missing"]
    assert any(
        reason.startswith("missing_required_evidence:")
        for reason in item["reasons"]
    )
    assert result["paid_calls"] == 0
    assert result["external_sends"] == 0


def test_terminal_snapshot_prefers_recorded_originating_stage():
    d = _db()
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
        "INSERT INTO pipeline_items VALUES(1,'REJECTED','{}')"
    )
    d.execute(
        "INSERT INTO pipeline_events VALUES(1,1,'QUALIFICATION_PENDING','REJECTED','w','no',?,?)",
        (
            json.dumps({
                "commercial_score": 20,
                "technical_score": 25,
                "commercial_opportunity": None,
            }),
            "2026-09-30T00:02:00+00:00",
        ),
    )

    result = oi.prospect_snapshot(d, 1)

    assert result["state"] == "REJECTED"
    assert result["assessment_stage"] == "QUALIFICATION_PENDING"
    assert result["evidence_completeness"]["stage"] == "QUALIFICATION_PENDING"


def test_shadow_review_queue_never_resurfaces_suppressed_prospect():
    d = _db()
    d.execute(
        "INSERT INTO businesses VALUES(1,?,?,?,?,?,0)",
        (
            "Suppressed Co",
            "https://suppressed.co.nz",
            "Canterbury",
            "import:manual",
            "suppressed.co.nz",
        ),
    )
    d.execute(
        "INSERT INTO pipeline_items VALUES(1,'SUPPRESSED','{}')"
    )

    result = oi.shadow_review_queue(d, limit=10)

    assert result["items"] == []
    assert result["count"] == 0
    assert result["automatic_action"] is False


def test_shadow_review_queue_ignores_active_qualified_prospect():
    d = _db()
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
        "INSERT INTO pipeline_items VALUES(1,'QUALIFIED','{}')"
    )
    result = oi.shadow_review_queue(d, limit=10)
    assert result["items"] == []
    assert result["automatic_action"] is False


def test_source_diagnostic_does_not_judge_small_samples():
    diagnostic = oi._source_diagnostic(
        total=3,
        qualification_yield=0.0,
        negative_terminal_rate=1.0,
        engagement_rate=0.0,
        won_rate=0.0,
    )
    assert diagnostic["signal"] == "INSUFFICIENT_SAMPLE"
    assert diagnostic["automatic_action"] is False


def test_source_diagnostic_flags_poor_yield_only_with_enough_evidence():
    diagnostic = oi._source_diagnostic(
        total=20,
        qualification_yield=0.05,
        negative_terminal_rate=0.8,
        engagement_rate=0.0,
        won_rate=0.0,
    )
    assert diagnostic["signal"] == "POOR_YIELD"
    assert diagnostic["sample_size"] == 20
    assert diagnostic["automatic_action"] is False


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
    nxt, reason, evidence = workers.identity_handler(
        d,
        {
            "business_id": 1,
            "payload": json.dumps({
                "legal_name": "Acme Plumbing Limited",
                "nzbn": "9429000000000",
                "discovery_quality": {
                    "disposition": "ACCEPT",
                    "classification": "BUSINESS_HOME",
                },
            }),
        },
        None,
    )
    assert nxt == "AUDIT_PENDING"
    assert reason == "identity resolved from declared website"
    assert evidence["canonical_host"] == "acmeplumbing.co.nz"
    assert evidence["shadow_intelligence"]["shadow_only"] is True
    identity = evidence["shadow_intelligence"]["identity"]
    assert identity["status"] == "HIGH"
    assert "nzbn_present" in identity["supporting_signals"]
    assert "discovery_quality_accept" in identity["supporting_signals"]


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
        d,
        {
            "business_id": 1,
            "payload": json.dumps({
                "canonical_host": "acmeplumbing.co.nz",
                "legal_name": "Acme Plumbing Limited",
                "nzbn": "9429000000000",
                "discovery_quality": {
                    "disposition": "ACCEPT",
                    "classification": "BUSINESS_HOME",
                },
            }),
        },
        None,
    )
    assert nxt == "REJECTED"
    assert reason.startswith("not qualified:")
    shadow = evidence["shadow_intelligence"]
    assert "commercial_evidence" in shadow["evidence_completeness"]["missing"]
    assert "nzbn_present" in shadow["identity"]["supporting_signals"]
    assert "discovery_quality_accept" in shadow["identity"]["supporting_signals"]
    assert (
        shadow["next_best_evidence"]["action"]
        == "INSPECT_FIRST_PARTY_COMMERCIAL_PAGES"
    )
    assert shadow["paid_calls"] == 0
    assert shadow["external_sends"] == 0
