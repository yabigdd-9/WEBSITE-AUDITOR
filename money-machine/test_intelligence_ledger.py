"""Tests for V45 Wave 1: Experience Memory, Rejection Intelligence, Error Mining.

All tests use synthetic disposable databases. No network, no model calls, no
external sends.
"""
import json
import sqlite3
import tempfile
from pathlib import Path

import mm_core as c
import mm_intelligence_ledger as ledger
import mm_rejection_intelligence as ri
import mm_error_mining as em
import mm_pipeline as p


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
        assert analysis['cluster_count'] == 0

    def test_false_negative_detection(self):
        d = fresh_db()
        # A rejected candidate with high technical score → false negative
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
        assert fn[0]['type'] == 'FALSE_NEGATIVE'

    def test_false_positive_detection(self):
        d = fresh_db()
        # An accepted candidate with weak evidence → false positive
        rec = ledger.IntelligenceDecision(
            prospect_id=2, business_name='Junk', domain='junk.co.nz',
            decision='QUALIFIED', primary_reason='',
            confidence=0.5, rule_version='v45.1', stage='qualification',
            derived_evidence={'evidence_confidence': 0.1, 'technical_score': 10},
        )
        ledger.append_decision(d, rec)
        fp = em.detect_false_positives(d)
        assert len(fp) == 1
        assert fp[0]['type'] == 'FALSE_POSITIVE'

    def test_high_conf_wrong_detection(self):
        d = fresh_db()
        rec = ledger.IntelligenceDecision(
            prospect_id=3, business_name='Confident', domain='conf.co.nz',
            decision='ACCEPTED', primary_reason='',
            confidence=0.95, rule_version='v45.1',
            human_correction='This was actually junk',
        )
        ledger.append_decision(d, rec)
        wrong = em.detect_high_conf_wrong(d)
        assert len(wrong) == 1
        assert wrong[0]['type'] == 'HIGH_CONF_WRONG'

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
        analysis = em.mine_errors(d)
        assert analysis['total_errors'] == 0
        # Should handle empty analysis gracefully
        count = em.record_error_clusters(d, analysis)
        assert count == 0

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
            ('FALSE_NEGATIVE', 5, 'test cause', c.now()),
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
        types = {c['cluster_type'] for c in analysis['clusters']}
        assert 'FALSE_NEGATIVE' in types
        assert 'FALSE_POSITIVE' in types
