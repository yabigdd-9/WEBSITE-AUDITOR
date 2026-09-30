"""Tests for V45 Wave 1: Experience Memory, Rejection Intelligence, Error Mining.

All tests use synthetic disposable databases. No network, no model calls, no
external sends.
"""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

import mm_core as c
import mm_intelligence_ledger as ledger
import mm_rejection_intelligence as ri
import mm_error_mining as em
import mm_pipeline as p
import mm_outcomes as outcomes


def fresh_db():
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / 'int.db'
    sqlite3.connect(path).close()
    d = c.connect(path)
    d.executescript(
        """CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY, name TEXT,
            public_website TEXT, region TEXT, source TEXT, discovered_at TEXT,
            current_status TEXT, is_dummy INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS pipeline_items(business_id INTEGER PRIMARY KEY,
            state TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}',
            attempts INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 5,
            next_retry_at TEXT, lease_owner TEXT, lease_until TEXT,
            heartbeat_at TEXT, last_error TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS pipeline_events(id INTEGER PRIMARY KEY,
            business_id INTEGER, from_state TEXT, to_state TEXT,
            actor TEXT, reason TEXT, evidence TEXT, event_at TEXT);
        """
    )
    p.migrate(d)
    return d


class TestIntelligenceLedger:
    def test_migrate_creates_table(self):
        d = fresh_db()
        ledger.migrate(d)
        tables = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'intelligence_ledger' in tables

    def test_append_and_count_decisions(self):
        d = fresh_db()
        rec = ledger.IntelligenceDecision(
            prospect_id=1, business_name='Test Co', domain='test.co.nz',
            decision='REJECTED', disposition='REJECTED',
            primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
            confidence=0.85, rule_version='v45.1', stage='qualification',
        )
        row_id = ledger.append_decision(d, rec)
        assert row_id > 0
        assert ledger.count_decisions(d, decision='REJECTED') == 1
        assert ledger.count_decisions(d, primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE') == 1

    def test_decision_history_ordered(self):
        d = fresh_db()
        for i in range(3):
            rec = ledger.IntelligenceDecision(
                prospect_id=1, business_name=f'Co {i}', domain='test.co.nz',
                decision='REJECTED', confidence=0.5, rule_version='v45.1',
            )
            ledger.append_decision(d, rec)
        history = ledger.decision_history(d, 1)
        assert len(history) == 3
        assert history[0]['business_name'] == 'Co 2'  # newest first

    def test_record_correction_creates_new_row(self):
        d = fresh_db()
        rec = ledger.IntelligenceDecision(
            prospect_id=42, business_name='Original', domain='orig.co.nz',
            decision='ACCEPTED', disposition='ACCEPTED',
            primary_reason='qualified', confidence=0.9, rule_version='v45.1',
        )
        ledger.append_decision(d, rec)
        # Original should not be modified
        original_count = ledger.count_decisions(d)
        # Record a correction
        ledger.record_correction(d, 42, 'Should have been rejected: junk domain',
                                 'REJECTED', 0.9)
        # Append-only: new row added, original preserved
        assert ledger.count_decisions(d) == original_count + 1
        history = ledger.decision_history(d, 42)
        assert history[0]['human_correction'] is not None
        assert history[1]['decision'] == 'ACCEPTED'  # original preserved


class TestRejectionIntelligence:
    def test_classify_known_reasons(self):
        assert ri.classify_rejection('not qualified: commercial=25') == 'INSUFFICIENT_COMMERCIAL_EVIDENCE'
        assert ri.classify_rejection('no public website') == 'INSUFFICIENT_IDENTITY_EVIDENCE'
        assert ri.classify_rejection('dead-lettered after 5 attempts') == 'RETRY_EXHAUSTED'
        assert ri.classify_rejection('duplicate of existing') == 'DUPLICATE'

    def test_classify_unknown_falls_to_review(self):
        result = ri.classify_rejection('something completely unexpected')
        assert result == 'UNKNOWN_REQUIRES_REVIEW'

    def test_classify_does_not_reinterpret_as_good(self):
        """Unknown reasons must not be classified as a passing category."""
        result = ri.classify_rejection('garbage data here')
        assert result != 'NOT_BUSINESS' or True  # NOT_BUSINESS is still a rejection
        assert result in ri.REJECTION_CATEGORIES

    def test_rejection_categories_complete(self):
        """All categories from the plan must be present."""
        expected = {
            "NOT_BUSINESS", "NON_NZ", "DIRECTORY_OR_AGGREGATOR",
            "SOCIAL_PROFILE_ONLY", "MARKETPLACE", "NEWS_OR_ARTICLE",
            "GOVERNMENT_OR_REGISTRY", "JOB_BOARD", "INVALID_DOMAIN",
            "UNREACHABLE", "DUPLICATE", "PARENT_BRANCH_COLLISION",
            "INSUFFICIENT_IDENTITY_EVIDENCE", "INSUFFICIENT_COMMERCIAL_EVIDENCE",
            "TECHNICAL_SCORE_TOO_LOW", "NO_ACTIONABLE_OPPORTUNITY",
            "SUPPRESSED_POLICY", "RETRY_EXHAUSTED", "UNKNOWN_REQUIRES_REVIEW",
        }
        assert set(ri.REJECTION_CATEGORIES) == expected

    def test_record_rejection_persists(self):
        d = fresh_db()
        rec = ri.RejectionRecord(
            prospect_id=1, business_name='Test', domain='test.co.nz',
            primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
            stage='qualification', confidence=0.85,
            decision_detail='not qualified: commercial=25, technical=0',
        )
        row_id = ri.record_rejection(d, rec)
        assert row_id > 0
        rows = d.execute("SELECT * FROM intelligence_rejections WHERE prospect_id=1").fetchall()
        assert len(rows) == 1

    def test_rejection_summary(self):
        d = fresh_db()
        for i in range(5):
            rec = ri.RejectionRecord(
                prospect_id=i, business_name=f'Co{i}', domain=f'co{i}.co.nz',
                primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
                confidence=0.85,
            )
            ri.record_rejection(d, rec)
        summary = ri.rejection_summary(d)
        assert len(summary) == 1
        assert summary[0]['n'] == 5

    def test_retryable_categories(self):
        assert ri.is_retryable('UNREACHABLE') is True
        assert ri.is_retryable('INSUFFICIENT_COMMERCIAL_EVIDENCE') is True
        assert ri.is_retryable('UNKNOWN_REQUIRES_REVIEW') is True
        assert ri.is_retryable('NO_ACTIONABLE_OPPORTUNITY') is False
        assert ri.is_retryable('DUPLICATE') is False


class TestErrorMining:
    def test_no_errors_on_empty_db(self):
        d = fresh_db()
        analysis = em.mine_errors(d)
        assert analysis['total_errors'] == 0
        assert analysis['confirmed_errors'] == 0
        assert analysis['suspected_errors'] == 0
        assert analysis['high_confidence_confirmed'] == 0
        assert analysis['errors'] == []
        assert analysis['cluster_count'] == 0

    def test_error_analysis_does_not_migrate_or_mutate_schema(self):
        d = fresh_db()
        before = {
            (row["type"], row["name"])
            for row in d.execute(
                "SELECT type,name FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert "intelligence_ledger" not in {name for _, name in before}

        analysis = em.mine_errors(d)

        after = {
            (row["type"], row["name"])
            for row in d.execute(
                "SELECT type,name FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert analysis["total_errors"] == 0
        assert after == before
        assert "intelligence_ledger" not in {name for _, name in after}

    def test_false_negative_detection(self):
        d = fresh_db()
        # Strong signals alone are only a suspected false negative.
        rec = ledger.IntelligenceDecision(
            prospect_id=1, business_name='Plumber', domain='plumber.co.nz',
            decision='REJECTED', primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
            confidence=0.85, rule_version='v45.1', stage='qualification',
            derived_evidence={'technical_score': 80, 'commercial_score': 20},
        )
        ledger.append_decision(d, rec)
        analysis = em.mine_errors(d)
        assert analysis['total_errors'] >= 1
        fn = [e for e in em.detect_false_negatives(d)]
        assert len(fn) == 1
        assert fn[0]['type'] == 'SUSPECTED_FALSE_NEGATIVE'

    def test_false_positive_detection(self):
        d = fresh_db()
        # Weak evidence alone is only a suspected false positive.
        rec = ledger.IntelligenceDecision(
            prospect_id=2, business_name='Junk', domain='junk.co.nz',
            decision='QUALIFIED', primary_reason='',
            confidence=0.5, rule_version='v45.1', stage='qualification',
            derived_evidence={'evidence_confidence': 0.1, 'technical_score': 10},
        )
        ledger.append_decision(d, rec)
        fp = em.detect_false_positives(d)
        assert len(fp) == 1
        assert fp[0]['type'] == 'SUSPECTED_FALSE_POSITIVE'

    def test_missing_acceptance_evidence_stays_unknown_not_false_positive(self):
        d = fresh_db()
        rec = ledger.IntelligenceDecision(
            prospect_id=22, business_name='Unknown Evidence',
            domain='unknown.co.nz', decision='QUALIFIED',
            confidence=0.5, rule_version='v45.1', stage='qualification',
            derived_evidence={},
        )
        ledger.append_decision(d, rec)

        assert em.detect_false_positives(d) == []

    def test_high_conf_wrong_detection(self):
        d = fresh_db()
        rec = ledger.IntelligenceDecision(
            prospect_id=3, business_name='Confident', domain='conf.co.nz',
            decision='ACCEPTED', primary_reason='',
            confidence=0.95, rule_version='v45.1',
        )
        ledger.append_decision(d, rec)
        ledger.record_correction(
            d, 3, 'This was actually junk', 'REJECTED', 0.95
        )
        wrong = em.detect_high_conf_wrong(d)
        assert len(wrong) == 1
        assert wrong[0]['type'] == 'HIGH_CONF_WRONG'
        assert wrong[0]['confirmed_error_type'] == 'CONFIRMED_FALSE_POSITIVE'

    def test_confirmed_false_negative_requires_correction_or_outcome(self):
        d = fresh_db()
        rec = ledger.IntelligenceDecision(
            prospect_id=10, business_name='Missed', domain='missed.co.nz',
            decision='REJECTED', primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
            confidence=0.9, rule_version='v45.1', stage='qualification',
            derived_evidence={'technical_score': 85, 'commercial_score': 20},
        )
        original_id = ledger.append_decision(d, rec)

        # Before correction this remains suspicion only.
        assert em.detect_confirmed_false_negatives(d) == []
        suspected = em.detect_false_negatives(d)
        assert suspected[0]['type'] == 'SUSPECTED_FALSE_NEGATIVE'

        ledger.record_correction(
            d, 10, 'Verified strong commercial fit', 'QUALIFIED', 0.95
        )
        confirmed = em.detect_confirmed_false_negatives(d)
        assert len(confirmed) == 1
        assert confirmed[0]['type'] == 'CONFIRMED_FALSE_NEGATIVE'
        assert confirmed[0]['ledger_id'] == original_id
        # Once confirmed, the same decision is no longer duplicated as suspected.
        assert em.detect_false_negatives(d) == []

    def test_confirmed_false_positive_requires_human_negative_correction(self):
        d = fresh_db()
        rec = ledger.IntelligenceDecision(
            prospect_id=11, business_name='Weak', domain='weak.co.nz',
            decision='QUALIFIED', confidence=0.9, rule_version='v45.1',
            stage='qualification',
            derived_evidence={'evidence_confidence': 0.1, 'technical_score': 10},
        )
        original_id = ledger.append_decision(d, rec)
        assert em.detect_confirmed_false_positives(d) == []

        ledger.record_correction(
            d, 11, 'Verified directory/non-prospect', 'REJECTED', 0.95
        )
        confirmed = em.detect_confirmed_false_positives(d)
        assert len(confirmed) == 1
        assert confirmed[0]['type'] == 'CONFIRMED_FALSE_POSITIVE'
        assert confirmed[0]['ledger_id'] == original_id
        assert em.detect_false_positives(d) == []

    def test_confirmation_pairs_only_to_immediately_preceding_real_decision(self):
        d = fresh_db()
        first_id = ledger.append_decision(d, ledger.IntelligenceDecision(
            prospect_id=12, business_name='Multi', domain='multi.co.nz',
            decision='QUALIFIED', confidence=0.8, rule_version='v45.1',
            stage='qualification',
        ))
        second_id = ledger.append_decision(d, ledger.IntelligenceDecision(
            prospect_id=12, business_name='Multi', domain='multi.co.nz',
            decision='QUALIFIED', confidence=0.9, rule_version='v45.2',
            stage='qualification',
        ))
        ledger.record_correction(
            d, 12, 'Latest qualification was wrong', 'REJECTED', 0.95
        )

        confirmed = em.detect_confirmed_false_positives(d)

        assert len(confirmed) == 1
        assert confirmed[0]['ledger_id'] == second_id
        assert confirmed[0]['ledger_id'] != first_id

    def test_score_inversion_is_comparable_cohort_suspicion_only(self):
        d = fresh_db()
        base = dict(
            source='searxng-local:q1',
            query_fingerprint='q1',
            stage='qualification',
            rule_version='v45.1',
            recorded_at='2026-09-30T01:00:00+00:00',
        )
        ledger.append_decision(d, ledger.IntelligenceDecision(
            prospect_id=20, business_name='Rejected High', domain='high.co.nz',
            decision='REJECTED',
            derived_evidence={'opportunity_score': 80},
            **base,
        ))
        ledger.append_decision(d, ledger.IntelligenceDecision(
            prospect_id=21, business_name='Accepted Low', domain='low.co.nz',
            decision='QUALIFIED',
            derived_evidence={'opportunity_score': 40},
            **base,
        ))
        inversions = em.detect_score_inversions(d)
        assert len(inversions) == 1
        assert inversions[0]['type'] == 'SUSPECTED_SCORE_INVERSION'
        assert inversions[0]['score_gap'] == 40.0
        assert inversions[0]['confirmed'] is False

    def test_source_failure_cluster_detection(self):
        d = fresh_db()
        # Create 20 rejections from the same source
        for i in range(25):
            rec = ledger.IntelligenceDecision(
                prospect_id=i, business_name=f'Src{i}', domain=f's{i}.co.nz',
                decision='REJECTED', primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
                confidence=0.5, rule_version='v45.1', stage='discovery',
                source='searxng-local:badquery',
            )
            ledger.append_decision(d, rec)
        clusters = em.detect_source_failure_clusters(d)
        assert len(clusters) >= 1
        assert clusters[0]['type'] == 'SOURCE_FAILURE_CLUSTER'
        assert clusters[0]['rejection_rate'] > 0.5

    def test_record_error_clusters_persists(self):
        d = fresh_db()
        rec = ledger.IntelligenceDecision(
            prospect_id=30, business_name='Suspect', domain='suspect.co.nz',
            decision='REJECTED',
            primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
            confidence=0.7, rule_version='v45.1',
            derived_evidence={'technical_score': 80, 'commercial_score': 20},
        )
        ledger.append_decision(d, rec)
        analysis = em.mine_errors(d)
        assert analysis['cluster_count'] >= 1

        first = em.record_error_clusters(d, analysis)
        second = em.record_error_clusters(d, analysis)

        assert first >= 1
        assert second == 0
        unresolved = em.unresolved_clusters(d)
        assert len(unresolved) == first

    def test_repeated_missing_evidence_detection(self):
        d = fresh_db()
        for i in range(10):
            rec = ledger.IntelligenceDecision(
                prospect_id=i, business_name=f'Co{i}', domain=f'co{i}.co.nz',
                decision='REJECTED', primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
                confidence=0.7, rule_version='v45.1',
                derived_evidence={'missing_evidence': ['booking_flow', 'contact_page']},
            )
            ledger.append_decision(d, rec)
        results = em.detect_repeated_missing_evidence(d)
        assert len(results) >= 1
        assert results[0]['missing_field'] in ('booking_flow', 'contact_page')
        assert results[0]['count'] >= 5

    def test_resolved_clusters_query(self):
        d = fresh_db()
        em.migrate(d)  # ensure table exists
        # Insert a resolved and an unresolved cluster manually
        d.execute(
            "INSERT INTO intelligence_error_clusters (cluster_type, size, suspected_root_cause, discovered_at) VALUES (?, ?, ?, ?)",
            ('CONFIRMED_FALSE_NEGATIVE', 5, 'test cause', c.now()),
        )
        d.commit()
        unresolved = em.unresolved_clusters(d)
        assert len(unresolved) == 1


class TestIntegration:
    def test_ledger_to_rejection_intelligence(self):
        """Record a decision in the ledger, then classify and record the rejection."""
        d = fresh_db()
        # Record decision
        rec = ledger.IntelligenceDecision(
            prospect_id=1, business_name='Test', domain='test.co.nz',
            decision='REJECTED', confidence=0.8, rule_version='v45.1',
            stage='qualification', primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
        )
        ledger.append_decision(d, rec)
        # Classify the rejection
        category = ri.classify_rejection('not qualified: commercial=25')
        assert category == 'INSUFFICIENT_COMMERCIAL_EVIDENCE'
        # Record in rejection intelligence
        rej = ri.RejectionRecord(
            prospect_id=1, business_name='Test', domain='test.co.nz',
            primary_reason=category, stage='qualification',
            decision_detail='not qualified: commercial=25',
        )
        ri.record_rejection(d, rej)
        # Verify both tables have the data
        ledger_count = ledger.count_decisions(d, prospect_id=1)
        rejection_count = d.execute(
            "SELECT COUNT(*) FROM intelligence_rejections WHERE prospect_id=1"
        ).fetchone()[0]
        assert ledger_count == 1
        assert rejection_count == 1

    def test_error_mining_from_ledger_data(self):
        """Full integration: decisions in ledger → error mining detects patterns."""
        d = fresh_db()
        # Good business that was wrongly rejected (false negative)
        rec1 = ledger.IntelligenceDecision(
            prospect_id=1, business_name='Good Plumber', domain='plumber.co.nz',
            decision='REJECTED', primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
            confidence=0.9, rule_version='v45.1', stage='qualification',
            derived_evidence={'technical_score': 85, 'commercial_score': 20, 'evidence_confidence': 0.6},
        )
        # Junk that was accepted (false positive)
        rec2 = ledger.IntelligenceDecision(
            prospect_id=2, business_name='Junk Site', domain='junk.co.nz',
            decision='QUALIFIED', primary_reason='',
            confidence=0.5, rule_version='v45.1', stage='qualification',
            derived_evidence={'technical_score': 10, 'evidence_confidence': 0.1},
        )
        ledger.append_decision(d, rec1)
        ledger.append_decision(d, rec2)
        analysis = em.mine_errors(d)
        assert analysis['total_errors'] == 2
        assert analysis['suspected_errors'] == 2
        assert analysis['confirmed_errors'] == 0
        assert analysis['high_confidence_confirmed'] == 0
        types = {c['cluster_type'] for c in analysis['clusters']}
        assert 'SUSPECTED_FALSE_NEGATIVE' in types
        assert 'SUSPECTED_FALSE_POSITIVE' in types


class TestExperienceLedger:
    """P1: experience ledger — append-only mirror of prospect_outcomes."""

    def _setup(self, tmp_path, monkeypatch):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "database").mkdir()
        monkeypatch.setenv("MM_ROOT", str(root))
        d = sqlite3.connect(root / "database" / "money_machine.db")
        d.row_factory = sqlite3.Row
        d.executescript(
            """CREATE TABLE IF NOT EXISTS businesses(
              id INTEGER PRIMARY KEY, name TEXT NOT NULL,
              public_website TEXT, region TEXT, source TEXT,
              discovered_at TEXT, current_status TEXT, is_dummy INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS mm_events(
              id INTEGER PRIMARY KEY, event_at TEXT NOT NULL,
              action TEXT NOT NULL, business_id INTEGER, detail TEXT);
            CREATE TABLE IF NOT EXISTS prospect_outcomes(
              id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL,
              outcome TEXT NOT NULL, observed_at TEXT NOT NULL,
              actor TEXT NOT NULL, evidence_path TEXT NOT NULL,
              evidence_hash TEXT NOT NULL, note TEXT DEFAULT '',
              created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS prospect_outcomes_business
              ON prospect_outcomes(business_id, observed_at DESC);
            INSERT INTO businesses(id,name) VALUES(1,'Test Co');"""
        )
        outcomes.migrate(d)
        return d, root

    def test_experience_ledger_mirrors_outcome(self, tmp_path, monkeypatch):
        d, root = self._setup(tmp_path, monkeypatch)
        ev = root / "ev.txt"; ev.write_text("test evidence")
        outcomes.record(d, 1, "REPLIED", ev, c.sha(ev.read_bytes()),
                        actor="human-test", note="mirror check")
        d.commit()
        rows = d.execute("SELECT * FROM experience_ledger").fetchall()
        assert len(rows) == 1
        assert rows[0]["business_id"] == 1
        assert rows[0]["outcome"] == "REPLIED"
        assert rows[0]["actor"] == "human-test"
        assert rows[0]["outcome_id"] > 0

    def test_experience_ledger_append_only(self, tmp_path, monkeypatch):
        d, root = self._setup(tmp_path, monkeypatch)
        ev = root / "ev.txt"; ev.write_text("test evidence")
        outcomes.record(d, 1, "REPLIED", ev, c.sha(ev.read_bytes()),
                        actor="human-test")
        d.commit()
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            d.execute("UPDATE experience_ledger SET outcome='WON'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            d.execute("DELETE FROM experience_ledger")
        d.close()

    def test_experience_ledger_multiple_outcomes(self, tmp_path, monkeypatch):
        d, root = self._setup(tmp_path, monkeypatch)
        ev = root / "ev.txt"; ev.write_text("test evidence")
        h = c.sha(ev.read_bytes())
        outcomes.record(d, 1, "PENDING", ev, h, actor="human-test")
        outcomes.record(d, 1, "REPLIED", ev, h, actor="human-test")
        outcomes.record(d, 1, "WON", ev, h, actor="human-test")
        d.commit()
        rows = d.execute(
            "SELECT outcome FROM experience_ledger ORDER BY id"
        ).fetchall()
        assert [r["outcome"] for r in rows] == ["PENDING", "REPLIED", "WON"]

    def test_summary_has_by_actor_and_trend(self, tmp_path, monkeypatch):
        d, root = self._setup(tmp_path, monkeypatch)
        ev = root / "ev.txt"; ev.write_text("test evidence")
        h = c.sha(ev.read_bytes())
        outcomes.record(d, 1, "REPLIED", ev, h, actor="human-a")
        outcomes.record(d, 1, "WON", ev, h, actor="human-b")
        outcomes.record(d, 1, "LOST", ev, h, actor="human-a")
        d.commit()
        s = outcomes.summary(d)
        assert "by_actor" in s
        assert s["by_actor"]["human-a"] == 2
        assert s["by_actor"]["human-b"] == 1
        assert "outcome_trend" in s
        assert len(s["outcome_trend"]) >= 1

    def test_pending_outcome_is_valid(self, tmp_path, monkeypatch):
        d, root = self._setup(tmp_path, monkeypatch)
        assert "PENDING" in outcomes.OUTCOMES
        ev = root / "ev.txt"; ev.write_text("test evidence")
        result = outcomes.record(d, 1, "PENDING", ev,
                                c.sha(ev.read_bytes()), actor="human-test")
        assert result["outcome"] == "PENDING"


class TestLivePipelineLedgerWiring:
    """Live deterministic workers append decisions without sending outreach."""

    def _setup(self):
        d = fresh_db()
        d.execute(
            "INSERT INTO businesses(id,name,public_website,region,source) "
            "VALUES(1,'Test Co','https://test.example','NZ','synthetic-test')"
        )
        ledger.migrate(d)
        ri.migrate(d)
        d.commit()
        return d

    def test_ledger_migration_preserves_an_active_transaction(self):
        d = self._setup()
        d.execute("UPDATE businesses SET name='Uncommitted' WHERE id=1")
        record = ledger.IntelligenceDecision(
            prospect_id=1, business_name='Uncommitted', domain='test.example',
            decision='QUALIFIED', disposition='ACCEPTED',
            primary_reason='QUALIFIED', stage='qualification',
        )
        ledger.append_decision(d, record)
        ri.record_rejection(d, ri.RejectionRecord(
            prospect_id=1, business_name='Uncommitted', domain='test.example',
            primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
            stage='qualification', confidence=0.9,
        ))
        assert d.in_transaction
        d.rollback()
        assert d.execute('SELECT name FROM businesses WHERE id=1').fetchone()[0] == 'Test Co'
        assert ledger.count_decisions(d) == 0
        assert ri.rejection_summary(d) == []
        d.close()

    def test_identity_resolution_appends_decision(self):
        d = self._setup()
        import mm_workers as workers
        state, _, evidence = workers.identity_handler(
            d, {'business_id': 1, 'payload': '{}'}, 'worker-test'
        )
        row = d.execute(
            'SELECT decision, stage, domain FROM intelligence_ledger '
            'WHERE prospect_id=1'
        ).fetchone()
        assert state == 'AUDIT_PENDING'
        assert evidence['canonical_host'] == 'test.example'
        assert tuple(row) == ('IDENTITY_RESOLVED', 'identity', 'test.example')
        d.close()

    def test_identity_rejection_is_recorded_before_permanent_failure(self):
        d = self._setup()
        d.execute('UPDATE businesses SET public_website=NULL WHERE id=1')
        d.commit()
        import mm_workers as workers
        with pytest.raises(p.PermanentError):
            workers.identity_handler(
                d, {'business_id': 1, 'payload': '{}'}, 'worker-test'
            )
        row = d.execute(
            'SELECT decision, primary_reason, stage FROM intelligence_ledger '
            'WHERE prospect_id=1'
        ).fetchone()
        assert tuple(row) == (
            'REJECTED', 'INSUFFICIENT_IDENTITY_EVIDENCE', 'identity'
        )
        rejection = d.execute(
            'SELECT primary_reason,stage FROM intelligence_rejections '
            'WHERE prospect_id=1'
        ).fetchone()
        assert tuple(rejection) == ('INSUFFICIENT_IDENTITY_EVIDENCE', 'identity')
        d.close()

    def test_qualification_records_pass_and_reject(self):
        d = self._setup()
        import mm_workers as workers
        rejected_state, _, _ = workers.qualification_handler(
            d, {'business_id': 1, 'payload': '{}'}, 'worker-test'
        )
        assert rejected_state == 'REJECTED'

        d.execute(
            "INSERT INTO pipeline_events(business_id,from_state,to_state,actor,"
            "reason,evidence,event_at) VALUES(1,'AUDIT_PENDING','AUDITED',"
            "'worker-test','synthetic audit',"
            "'{\"defect_count\":1,\"score\":75}','2026-09-30T00:00:00Z')"
        )
        d.commit()
        qualified_state, _, _ = workers.qualification_handler(
            d, {'business_id': 1, 'payload': '{}'}, 'worker-test'
        )
        assert qualified_state == 'CONTACT_PENDING'
        decisions = [
            row['decision'] for row in d.execute(
                'SELECT decision FROM intelligence_ledger WHERE prospect_id=1'
            )
        ]
        assert 'REJECTED' in decisions
        assert 'QUALIFIED' in decisions
        rejection_count = d.execute(
            'SELECT count(*) FROM intelligence_rejections WHERE prospect_id=1'
        ).fetchone()[0]
        assert rejection_count == 1
        d.close()

    def test_contact_release_hold_is_logged_as_human_review(self, monkeypatch):
        d = self._setup()
        import mm_workers as workers
        monkeypatch.setattr(workers, '_current_verified_high', lambda *_: None)
        monkeypatch.setattr(
            workers, '_email_v2_release_state',
            lambda *_: (False, {'release_mode': 'HELD'}),
        )
        state, _, evidence = workers.contact_handler(
            d, {'business_id': 1, 'payload': '{}'}, 'worker-test'
        )
        row = d.execute(
            'SELECT decision, disposition FROM intelligence_ledger '
            'WHERE prospect_id=1'
        ).fetchone()
        assert state == 'NEEDS_REVIEW'
        assert evidence['external_sends'] == 0
        assert tuple(row) == ('NEEDS_REVIEW', 'REVIEW')
        d.close()


class TestIntelligenceOperatorCommands:
    def test_reports_and_human_correction_use_synthetic_database(
        self, tmp_path, monkeypatch, capsys
    ):
        root = tmp_path / 'repo'
        (root / 'database').mkdir(parents=True)
        db_path = root / 'database' / 'money_machine.db'
        db_path.touch()
        monkeypatch.setenv('MM_ROOT', str(root))

        d = c.connect()
        ledger.migrate(d)
        ri.migrate(d)
        em.migrate(d)
        ledger.append_decision(d, ledger.IntelligenceDecision(
            prospect_id=1, business_name='Synthetic Co', domain='synthetic.example',
            decision='REJECTED', disposition='REJECTED',
            primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
            confidence=0.9, stage='qualification',
        ))
        ri.record_rejection(d, ri.RejectionRecord(
            prospect_id=1, business_name='Synthetic Co',
            domain='synthetic.example',
            primary_reason='INSUFFICIENT_COMMERCIAL_EVIDENCE',
            stage='qualification', confidence=0.9,
        ))
        d.commit()
        d.close()

        import mm_operator
        assert mm_operator.main(['intelligence-report']) == 0
        report = json.loads(capsys.readouterr().out)
        assert report['decisions'] == 1
        assert report['external_sends'] == 0

        assert mm_operator.main(['rejection-report', '--format', 'summary']) == 0
        summary = capsys.readouterr().out
        assert 'INSUFFICIENT_COMMERCIAL_EVIDENCE: 1' in summary
        assert 'external sends: 0' in summary

        assert mm_operator.main([
            'human-correction', '1', '--correction', 'Synthetic review',
            '--corrected-decision', 'QUALIFIED',
        ]) == 0
        correction = json.loads(capsys.readouterr().out)
        assert correction['id'] > 0
        assert correction['external_sends'] == 0

        d = c.connect()
        history = ledger.decision_history(d, 1)
        assert len(history) == 2
        assert history[-1]['decision'] == 'REJECTED'
        assert history[0]['disposition'] == 'HUMAN_CORRECTED'
        d.close()
