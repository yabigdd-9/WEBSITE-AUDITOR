"""Strategy pattern for opportunity scoring algorithms.

This module provides a pluggable architecture for scoring audit results
against opportunity policies to determine qualification and scores.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, UTC
from hashlib import sha256
import json
from typing import Any

from .models import CheckDefinition


@dataclass(frozen=True)
class OpportunityDimension:
    """A single opportunity scoring dimension with metadata."""
    name: str
    value: int  # 0-100
    weight: int  # policy weight
    explanation: str
    contribution: float  # value * weight / 100


@dataclass(frozen=True)
class OpportunityResult:
    """Result of an opportunity scoring operation."""
    status: str  # "qualified_for_internal_review", "quarantined", etc.
    reason: str
    score: float | None
    breakdown: dict[str, dict]  # dimension -> {value, weight, contribution, explanation}
    missing_context: list[str]
    evidence: list[dict]
    policy_sha256: str
    source_run_id: str | None
    buying_intent: str = "unknown"
    contact_eligible: bool = False


class OpportunityScoringStrategy(ABC):
    """Abstract base class for opportunity scoring strategies.

    An opportunity scoring strategy evaluates audit findings against a policy
    and produces an OpportunityResult with qualification status and score.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Strategy version."""
        pass

    @abstractmethod
    def validate_entry(self, entry: dict, context: dict, policy: dict) -> OpportunityResult | None:
        """Validate entry and return early result if disqualified, or None to continue.

        Args:
            entry: Audit entry with findings, status, run_id, etc.
            context: Service context (delivery_feasibility, business_service_fit, etc.)
            policy: Opportunity policy with weights and supported defect keys

        Returns:
            Early OpportunityResult if disqualified, None if validation passes.
        """
        pass

    @abstractmethod
    def calculate_dimensions(
        self, entry: dict, context: dict, policy: dict, now: int
    ) -> dict[str, OpportunityDimension]:
        """Calculate all scoring dimensions.

        Args:
            entry: Validated audit entry
            context: Service context
            policy: Opportunity policy
            now: Current timestamp

        Returns:
            Dict of dimension_name -> OpportunityDimension
        """
        pass

    @abstractmethod
    def build_result(
        self,
        entry: dict,
        context: dict,
        policy: dict,
        dimensions: dict[str, OpportunityDimension],
        now: int,
    ) -> OpportunityResult:
        """Build final OpportunityResult from calculated dimensions."""
        pass

    def score(self, entry: dict, context: dict, policy: dict, *, now: int) -> OpportunityResult:
        """Main scoring entry point."""
        # Validate
        early_result = self.validate_entry(entry, context, policy)
        if early_result is not None:
            return early_result

        # Calculate dimensions
        dimensions = self.calculate_dimensions(entry, context, policy, now)

        # Build result
        return self.build_result(entry, context, policy, dimensions, now)


class DefaultOpportunityStrategy(OpportunityScoringStrategy):
    """Default opportunity scoring strategy matching the original implementation."""

    name = "default"
    version = "1.0.0"

    # Severity to impact mapping
    SEVERITY_IMPACT = {"low": 25, "medium": 50, "high": 75, "critical": 100}

    def _digest(self, obj: Any) -> str:
        """Compute SHA256 digest of JSON-serializable object."""
        return sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()

    def validate_entry(self, entry: dict, context: dict, policy: dict) -> OpportunityResult | None:
        from scripts.cloud_discovery import canonical_domain

        # Suppressed or contact prohibited
        if context.get("suppressed") or context.get("contact_prohibited"):
            return OpportunityResult(
                status="quarantined", reason="suppressed_or_restricted", score=None,
                breakdown={}, missing_context=[], evidence=[],
                policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
            )

        # Incomplete audit
        if entry.get("status") != "COMPLETE":
            return OpportunityResult(
                status="quarantined", reason="incomplete_audit", score=None,
                breakdown={}, missing_context=[], evidence=[],
                policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
            )

        # Domain validation
        try:
            domain = canonical_domain(entry.get("domain"))
        except (ValueError, TypeError):
            return OpportunityResult(
                status="quarantined", reason="invalid_audit_identity", score=None,
                breakdown={}, missing_context=[], evidence=[],
                policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
            )

        # Run ID
        if not isinstance(entry.get("run_id"), str) or not entry["run_id"]:
            return OpportunityResult(
                status="quarantined", reason="missing_audit_identity", score=None,
                breakdown={}, missing_context=[], evidence=[],
                policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
            )

        # Findings validation
        findings = entry.get("findings")
        if not isinstance(findings, list) or not findings or len(findings) > 20:
            return OpportunityResult(
                status="quarantined", reason="no_observed_findings", score=None,
                breakdown={}, missing_context=[], evidence=[],
                policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
            )

        for finding in findings:
            if not isinstance(finding, dict):
                return OpportunityResult(
                    status="quarantined", reason="missing_or_speculative_evidence", score=None,
                    breakdown={}, missing_context=[], evidence=[],
                    policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
                )
            ref = finding.get("evidence_ref")
            if not (
                finding.get("confidence") == "observed"
                and finding.get("evidence_check_status") == "ok"
                and ref and ref == finding.get("evidence_check")
                and finding.get("source_url") and finding.get("observed")
                and finding.get("finding_id") and finding.get("remediation_action")
                and finding.get("severity") in {"low", "medium", "high", "critical"}
            ):
                return OpportunityResult(
                    status="quarantined", reason="missing_or_speculative_evidence", score=None,
                    breakdown={}, missing_context=[], evidence=[],
                    policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
                )
            try:
                if canonical_domain(finding["source_url"]) != domain:
                    return OpportunityResult(
                        status="quarantined", reason="evidence_domain_mismatch", score=None,
                        breakdown={}, missing_context=[], evidence=[],
                        policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
                    )
            except (ValueError, TypeError):
                return OpportunityResult(
                    status="quarantined", reason="invalid_evidence_url", score=None,
                    breakdown={}, missing_context=[], evidence=[],
                    policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
                )
            if finding.get("defect_key") not in policy["supported_defect_keys"]:
                return OpportunityResult(
                    status="quarantined", reason="unsupported_service", score=None,
                    breakdown={}, missing_context=[], evidence=[],
                    policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
                )

        # Duplicate finding check
        if len({f["finding_id"] for f in findings}) != len(findings):
            return OpportunityResult(
                status="quarantined", reason="duplicate_finding", score=None,
                breakdown={}, missing_context=[], evidence=[],
                policy_sha256=self._digest(policy), source_run_id=entry.get("run_id"),
            )

        return None  # Validation passed

    def calculate_dimensions(
        self, entry: dict, context: dict, policy: dict, now: int
    ) -> dict[str, OpportunityDimension]:
        findings = entry.get("findings", [])

        # verified_technical_impact: highest severity
        max_severity = max(self.SEVERITY_IMPACT[f["severity"]] for f in findings)

        # evidence_quality: independent verification
        all_verified = all(f.get("independently_verified") is True for f in findings)
        evidence_quality = 100 if all_verified else 75

        # delivery_feasibility and business_service_fit from context
        missing = []
        reasons = {}

        dimensions = {
            "verified_technical_impact": OpportunityDimension(
                name="verified_technical_impact",
                value=max_severity,
                weight=policy["weights"]["verified_technical_impact"],
                explanation="Highest observed severity; does not establish buying intent.",
                contribution=float(Decimal(max_severity) * policy["weights"]["verified_technical_impact"] / 100),
            ),
            "evidence_quality": OpportunityDimension(
                name="evidence_quality",
                value=evidence_quality,
                weight=policy["weights"]["evidence_quality"],
                explanation="Observed canonical evidence; independent verification raises confidence.",
                contribution=float(Decimal(evidence_quality) * policy["weights"]["evidence_quality"] / 100),
            ),
        }

        for key in ("delivery_feasibility", "business_service_fit"):
            value = context.get(key)
            if value is None:
                value = 0
                missing.append(key)
                reasons[key] = "Not configured or verified; contributes zero."
            elif type(value) is not int or not 0 <= value <= 100:
                raise ValueError("Owner service context must be 0-100 or unknown")
            else:
                reasons[key] = "Explicit reviewed service context; not customer intent."
            dimensions[key] = OpportunityDimension(
                name=key,
                value=value,
                weight=policy["weights"][key],
                explanation=reasons[key],
                contribution=float(Decimal(value) * policy["weights"][key] / 100),
            )

        # recency
        try:
            observed = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            age = now - observed.timestamp() if observed.tzinfo is not None else -1
        except (KeyError, TypeError, ValueError):
            age = -1
        recency = 100 if 0 <= age <= 7 * 86400 else 50 if 0 <= age <= 30 * 86400 else 0
        dimensions["recency"] = OpportunityDimension(
            name="recency",
            value=recency,
            weight=policy["weights"]["recency"],
            explanation="Explicit evaluation time versus audit timestamp; missing/future dates contribute zero.",
            contribution=float(Decimal(recency) * policy["weights"]["recency"] / 100),
        )

        return dimensions

    def build_result(
        self,
        entry: dict,
        context: dict,
        policy: dict,
        dimensions: dict[str, OpportunityDimension],
        now: int,
    ) -> OpportunityResult:
        findings = entry.get("findings", [])

        breakdown = {
            name: {
                "value": dim.value,
                "weight": dim.weight,
                "contribution": dim.contribution,
                "explanation": dim.explanation,
            }
            for name, dim in dimensions.items()
        }

        total_score = sum(dim.contribution for dim in dimensions.values())
        missing = [k for k in ("delivery_feasibility", "business_service_fit") if context.get(k) is None]

        return OpportunityResult(
            status="qualified_for_internal_review",
            reason="observed_supported_work",
            score=total_score,
            breakdown=breakdown,
            missing_context=missing,
            evidence=[
                {
                    "finding_id": f["finding_id"],
                    "source_url": f["source_url"],
                    "evidence_ref": f["evidence_ref"],
                    "audit_run_id": entry.get("run_id"),
                }
                for f in sorted(findings, key=lambda f: f["finding_id"])
            ],
            policy_sha256=self._digest(policy),
            source_run_id=entry.get("run_id"),
        )


# Strategy registry
_OPPORTUNITY_STRATEGIES: dict[str, OpportunityScoringStrategy] = {}


def register_opportunity_strategy(strategy: OpportunityScoringStrategy) -> None:
    """Register an opportunity scoring strategy."""
    if strategy.name in _OPPORTUNITY_STRATEGIES:
        raise ValueError(f"Strategy already registered: {strategy.name}")
    _OPPORTUNITY_STRATEGIES[strategy.name] = strategy


def get_opportunity_strategy(name: str) -> OpportunityScoringStrategy:
    """Get an opportunity scoring strategy by name."""
    if name not in _OPPORTUNITY_STRATEGIES:
        raise ValueError(
            f"Strategy not found: {name}. Available: {list(_OPPORTUNITY_STRATEGIES.keys())}"
        )
    return _OPPORTUNITY_STRATEGIES[name]


def list_opportunity_strategies() -> list[dict[str, str]]:
    """List all registered opportunity strategies."""
    return [
        {"name": s.name, "version": s.version}
        for s in _OPPORTUNITY_STRATEGIES.values()
    ]


# Auto-register default strategy
register_opportunity_strategy(DefaultOpportunityStrategy())