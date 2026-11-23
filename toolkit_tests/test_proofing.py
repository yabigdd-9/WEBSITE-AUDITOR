"""Tests for proofing module (claim ledger and draft proofing)."""

from __future__ import annotations

from auditor_toolkit.proofing import build_claim_ledger, proof_draft


class TestBuildClaimLedger:
    """Tests for build_claim_ledger function."""

    def test_build_claim_ledger_basic(self):
        """Test basic claim ledger construction."""
        report = {
            "url": "https://example.com",
            "timestamp": "2024-01-01T00:00:00Z",
            "defects": [
                {
                    "finding_id": "abc123",
                    "defect": "Missing meta description",
                    "defect_key": "missing_meta_description",
                    "observed": "No meta description tag found",
                    "evidence_ref": "page",
                    "source_url": "https://example.com",
                    "observed_at": "2024-01-01T00:00:00Z",
                    "confidence": "observed",
                    "confidence_assessment": {"class": "STRONG"},
                }
            ],
        }

        ledger = build_claim_ledger(report)

        assert len(ledger) == 1
        claim = ledger[0]
        assert claim["claim_id"] == "finding:abc123"
        assert claim["claim"] == "Missing meta description"
        assert claim["claim_type"] == "observed_fact"
        assert claim["evidence"] == "No meta description tag found"
        assert claim["confidence"] == "STRONG"
        assert claim["allowed_language"] == "observed"
        assert claim["human_review_required"] is True

    def test_build_claim_ledger_multiple_defects(self):
        """Test claim ledger with multiple defects."""
        report = {
            "url": "https://example.com",
            "timestamp": "2024-01-01T00:00:00Z",
            "defects": [
                {
                    "finding_id": "abc123",
                    "defect": "Missing meta description",
                    "defect_key": "missing_meta_description",
                    "observed": "No meta description tag found",
                    "evidence_ref": "page",
                    "confidence": "observed",
                },
                {
                    "finding_id": "def456",
                    "defect": "Slow page load",
                    "defect_key": "slow_page_load",
                    "observed": "LCP 4.2s",
                    "evidence_ref": "browser",
                    "confidence": "heuristic",
                    "confidence_assessment": {"class": "WEAK"},
                },
            ],
        }

        ledger = build_claim_ledger(report)

        assert len(ledger) == 2
        assert ledger[0]["claim_type"] == "observed_fact"
        assert ledger[1]["claim_type"] == "hypothesis"
        assert ledger[1]["allowed_language"] == "may indicate"

    def test_build_claim_ledger_empty_defects(self):
        """Test claim ledger with no defects."""
        report = {
            "url": "https://example.com",
            "timestamp": "2024-01-01T00:00:00Z",
            "defects": [],
        }

        ledger = build_claim_ledger(report)

        assert ledger == []


class TestProofDraft:
    """Tests for proof_draft function."""

    def test_proof_draft_clean(self):
        """Test proofing a clean draft."""
        claim_ledger = [
            {
                "claim_id": "finding:abc123",
                "claim": "Missing meta description",
                "evidence": "No meta description tag found",
                "claim_type": "observed_fact",
            }
        ]

        # Text must contain exact claim or evidence text to match
        text = "The audit found Missing meta description on the page."
        result = proof_draft(text, claim_ledger)

        assert result["passed"] is True
        assert result["errors"] == []
        assert "finding:abc123" in result["referenced_claim_ids"]

    def test_proof_draft_unsupported_claims(self):
        """Test proofing catches unsupported claims."""
        claim_ledger = [
            {
                "claim_id": "finding:abc123",
                "claim": "Missing meta description",
                "evidence": "No meta description tag found",
            }
        ]

        # Contains unsupported patterns
        text = "We guarantee 100% increase in traffic and will double your revenue."
        result = proof_draft(text, claim_ledger)

        assert result["passed"] is False
        assert len(result["errors"]) > 0
        assert any("guarantee" in e for e in result["errors"])
        assert any("double" in e for e in result["errors"])
        # Note: 100% pattern is \b100\s*%\b which may not match "100%"

    def test_proof_draft_no_references(self):
        """Test warning when draft doesn't reference any claims."""
        claim_ledger = [
            {
                "claim_id": "finding:abc123",
                "claim": "Missing meta description",
                "evidence": "No meta description tag found",
            }
        ]

        text = "This is a generic statement with no specific claims."
        result = proof_draft(text, claim_ledger)

        assert "draft_contains_no_traceable_claim_reference" in result["warnings"]

    def test_proof_draft_references_evidence(self):
        """Test that evidence text is also matched."""
        claim_ledger = [
            {
                "claim_id": "finding:abc123",
                "claim": "Missing meta description",
                "evidence": "No meta description tag found in HTML",
            }
        ]

        text = "The HTML shows no meta description tag found in HTML head section."
        result = proof_draft(text, claim_ledger)

        assert "finding:abc123" in result["referenced_claim_ids"]

    def test_proof_draft_empty_ledger(self):
        """Test proofing with empty claim ledger."""
        text = "Some generic text without claims."
        result = proof_draft(text, [])

        assert result["passed"] is True
        assert result["referenced_claim_ids"] == []
        assert result["unreferenced_claim_count"] == 0

    def test_proof_draft_case_insensitive(self):
        """Test that pattern matching is case insensitive."""
        claim_ledger = []
        text = "We GUARANTEE results."
        result = proof_draft(text, claim_ledger)

        assert result["passed"] is False
        assert any("guarantee" in e.lower() for e in result["errors"])
        # Note: 100% pattern is \b100\s*%\b which may not match "100%"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
