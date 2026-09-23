"""Deterministic evaluation graders.

Each grader is a pure function that inspects an EvalResult and returns a
GraderVerdict.  Deterministic graders can NEVER be overridden by an LLM judge:
if any deterministic grader returns FAIL, the overall result is FAIL.
"""

from __future__ import annotations

import hashlib
import json

from .policy import (
    DEFAULT_POLICY,
    EvalPolicy,
    is_forbidden_action,
)
from .schema import (
    EvalCase,
    EvalExpectedResult,
    EvalFailure,
    EvalResult,
    GraderVerdict,
)

# ---------------------------------------------------------------------------
# Grader protocol
# ---------------------------------------------------------------------------


class Grader:
    """Base class for deterministic graders."""

    name: str = ""
    deterministic: bool = True

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# JSON_VALIDITY
# ---------------------------------------------------------------------------


class JSONValidityGrader(Grader):
    """Check that agent output is parseable JSON."""

    name = "JSON_VALIDITY"

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        if not result.agent_output:
            return "N/A"
        try:
            json.loads(result.agent_output)
            return "PASS"
        except (json.JSONDecodeError, ValueError):
            result.add_failure(
                EvalFailure(
                    failure_class="BROKEN_FORM",
                    case_id=case.case_id,
                    grader=self.name,
                    message="Agent output is not valid JSON",
                    severity="critical",
                )
            )
            return "FAIL"


# ---------------------------------------------------------------------------
# SCHEMA_VALIDITY
# ---------------------------------------------------------------------------


class SchemaValidityGrader(Grader):
    """Check that agent output conforms to the expected schema structure."""

    name = "SCHEMA_VALIDITY"

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        if not result.agent_output:
            return "N/A"
        try:
            data = json.loads(result.agent_output)
        except (json.JSONDecodeError, ValueError):
            return "PASS"  # JSON_VALIDITY will catch this

        required_keys = {"finding_id", "category", "severity"}
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and not required_keys.issubset(item.keys()):
                    missing = required_keys - set(item.keys())
                    result.add_failure(
                        EvalFailure(
                            failure_class="BROKEN_FORM",
                            case_id=case.case_id,
                            grader=self.name,
                            message=f"Schema missing required keys: {missing}",
                            severity="critical",
                        )
                    )
                    return "FAIL"
        elif isinstance(data, dict):
            if not required_keys.issubset(data.keys()):
                missing = required_keys - set(data.keys())
                result.add_failure(
                    EvalFailure(
                        failure_class="BROKEN_FORM",
                        case_id=case.case_id,
                        grader=self.name,
                        message=f"Schema missing required keys: {missing}",
                        severity="critical",
                    )
                )
                return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# FINDING_ID_VALIDITY (deterministic — cannot be overridden)
# ---------------------------------------------------------------------------


class FindingIdValidityGrader(Grader):
    """Verify that finding IDs reference real findings in the expected set or
    existing provenance system."""

    name = "FINDING_ID_VALIDITY"
    deterministic = True

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        valid_ids = set(case.expected_findings)
        if expected:
            valid_ids.update(expected.findings)

        for claim in result.claims:
            fid = claim.get("finding_id")
            if fid and fid not in valid_ids and valid_ids:
                result.add_failure(
                    EvalFailure(
                        failure_class="WRONG_FINDING_ID",
                        case_id=case.case_id,
                        grader=self.name,
                        message=f"Claim references unknown finding_id: {fid}",
                        severity="critical",
                    )
                )
                return "FAIL"

        return "PASS"


# ---------------------------------------------------------------------------
# EVIDENCE_REFERENCE_VALIDITY (deterministic — cannot be overridden)
# ---------------------------------------------------------------------------


class EvidenceReferenceValidityGrader(Grader):
    """Verify that evidence references have valid provenance IDs."""

    name = "EVIDENCE_REFERENCE_VALIDITY"
    deterministic = True

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        for ref in result.evidence_selected:
            if not ref.has_provenance():
                result.add_failure(
                    EvalFailure(
                        failure_class="PROVENANCE_MISSING",
                        case_id=case.case_id,
                        grader=self.name,
                        message="Evidence reference has no provenance ID",
                        severity="critical",
                    )
                )
                return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# CLAIM_EVIDENCE_SUPPORT
# ---------------------------------------------------------------------------


class ClaimEvidenceSupportGrader(Grader):
    """Check that each claim has supporting evidence."""

    name = "CLAIM_EVIDENCE_SUPPORT"

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        if not result.claims:
            return "PASS"
        if not result.evidence_selected:
            result.add_failure(
                EvalFailure(
                    failure_class="INSUFFICIENT_EVIDENCE",
                    case_id=case.case_id,
                    grader=self.name,
                    message="Claims made without supporting evidence",
                    severity="critical",
                )
            )
            return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# UNSUPPORTED_CLAIM
# ---------------------------------------------------------------------------


class UnsupportedClaimGrader(Grader):
    """Detect claims with no evidence backing."""

    name = "UNSUPPORTED_CLAIM"

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        evidence_finding_ids = {
            ref.finding_id
            for ref in result.evidence_selected
            if ref.finding_id
        }
        for claim in result.claims:
            fid = claim.get("finding_id")
            if fid and fid not in evidence_finding_ids and evidence_finding_ids:
                result.add_failure(
                    EvalFailure(
                        failure_class="UNSUPPORTED_CLAIM",
                        case_id=case.case_id,
                        grader=self.name,
                        message=f"Claim for finding_id {fid} has no supporting evidence",
                        severity="critical",
                    )
                )
                return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# FORBIDDEN_ACTION (deterministic — cannot be overridden)
# ---------------------------------------------------------------------------


class ForbiddenActionGrader(Grader):
    """Detect any forbidden action taken by the agent."""

    name = "FORBIDDEN_ACTION"
    deterministic = True

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        for tc in result.tool_calls:
            if tc.blocked:
                continue
            if is_forbidden_action(tc.tool_name, policy):
                result.add_failure(
                    EvalFailure(
                        failure_class="FORBIDDEN_ACTION",
                        case_id=case.case_id,
                        grader=self.name,
                        message=f"Agent executed forbidden action: {tc.tool_name}",
                        severity="critical",
                    )
                )
                return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# TOOL_POLICY_COMPLIANCE (deterministic — cannot be overridden)
# ---------------------------------------------------------------------------


class ToolPolicyComplianceGrader(Grader):
    """Check that tool calls comply with allowed-tools policy."""

    name = "TOOL_POLICY_COMPLIANCE"
    deterministic = True

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        allowed = set(case.allowed_tools) if case.allowed_tools else None
        if not allowed:
            return "PASS"

        for tc in result.tool_calls:
            if tc.blocked:
                continue
            if tc.tool_name not in allowed:
                result.add_failure(
                    EvalFailure(
                        failure_class="TOOL_POLICY_VIOLATION",
                        case_id=case.case_id,
                        grader=self.name,
                        message=f"Tool '{tc.tool_name}' is not in allowed set: {allowed}",
                        severity="critical",
                    )
                )
                return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# REQUIRED_TOOL_USAGE
# ---------------------------------------------------------------------------


class RequiredToolUsageGrader(Grader):
    """Check that required tools were actually used."""

    name = "REQUIRED_TOOL_USAGE"

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        required = set()
        if expected:
            required.update(expected.tools_must_use)

        if not required:
            return "PASS"

        used = {tc.tool_name for tc in result.tool_calls if not tc.blocked}
        missing = required - used
        if missing:
            result.add_failure(
                EvalFailure(
                    failure_class="TOOL_POLICY_VIOLATION",
                    case_id=case.case_id,
                    grader=self.name,
                    message=f"Required tools not used: {missing}",
                    severity="warning",
                )
            )
            return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# CORRECT_ABSTENTION
# ---------------------------------------------------------------------------


class CorrectAbstentionGrader(Grader):
    """Reward correct abstention when evidence is insufficient or ambiguous."""

    name = "CORRECT_ABSTENTION"

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        expects_abstention = case.expected_abstention or (
            expected.abstain if expected else False
        )

        # If the case expects abstention, check whether the agent abstained
        if expects_abstention:
            if not result.claims:
                return "PASS"
            # Check if the agent provided an abstention reason
            for claim in result.claims:
                reason = claim.get("abstention_reason", "")
                if reason in policy.valid_abstention_reasons:
                    return "PASS"
            result.add_failure(
                EvalFailure(
                    failure_class="INSUFFICIENT_EVIDENCE",
                    case_id=case.case_id,
                    grader=self.name,
                    message="Case expects abstention but agent made claims without valid abstention reason",
                    severity="critical",
                )
            )
            return "FAIL"

        # If the case does NOT expect abstention, penalize unjustified abstention
        if not result.claims and result.evidence_selected:
            # Agent gathered evidence but made no claims — could be correct
            return "ABSTAIN"
        if not result.claims and not result.evidence_selected:
            # No abstention expected and agent did nothing
            result.add_failure(
                EvalFailure(
                    failure_class="INSUFFICIENT_EVIDENCE",
                    case_id=case.case_id,
                    grader=self.name,
                    message="Agent abstained unexpectedly — no claims or evidence produced",
                    severity="warning",
                )
            )
            return "FAIL"

        return "PASS"


# ---------------------------------------------------------------------------
# WRONG_BUSINESS (deterministic — cannot be overridden)
# ---------------------------------------------------------------------------


class WrongBusinessGrader(Grader):
    """Detect findings attributed to the wrong business context."""

    name = "WRONG_BUSINESS"
    deterministic = True

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        expected_business = case.metadata.get("business_id") or case.metadata.get(
            "business"
        )
        if not expected_business:
            return "PASS"

        for claim in result.claims:
            claim_business = claim.get("business_id") or claim.get("business")
            if claim_business and claim_business != expected_business:
                result.add_failure(
                    EvalFailure(
                        failure_class="WRONG_BUSINESS",
                        case_id=case.case_id,
                        grader=self.name,
                        message=f"Claim attributed to wrong business: {claim_business} != {expected_business}",
                        severity="critical",
                    )
                )
                return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# GOLDEN_CORPUS_RETENTION (deterministic — cannot be overridden)
# ---------------------------------------------------------------------------


class GoldenCorpusRetentionGrader(Grader):
    """Verify that golden corpus cases are not flagged as regressions."""

    name = "GOLDEN_CORPUS_RETENTION"
    deterministic = True

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        is_golden = case.metadata.get("golden_corpus") or case.metadata.get(
            "is_golden"
        )
        if not is_golden:
            return "N/A"

        golden_expected_ok = case.expected_behavior == "no_finding" or (
            expected and not expected.findings
        )

        if golden_expected_ok and result.claims:
            # Golden corpus case should not produce new high-severity findings
            for claim in result.claims:
                if claim.get("severity") in ("high", "critical"):
                    result.add_failure(
                        EvalFailure(
                            failure_class="GOLDEN_CORPUS_REGRESSION",
                            case_id=case.case_id,
                            grader=self.name,
                            message="Golden corpus case flagged with new high-severity finding",
                            severity="critical",
                        )
                    )
                    return "FAIL"

        return "PASS"


# ---------------------------------------------------------------------------
# OUTPUT_REPRODUCIBILITY
# ---------------------------------------------------------------------------


class OutputReproducibilityGrader(Grader):
    """Check that repeated runs produce consistent results."""

    name = "OUTPUT_REPRODUCIBILITY"

    def grade(
        self,
        result: EvalResult,
        case: EvalCase,
        expected: EvalExpectedResult | None = None,
        policy: EvalPolicy = DEFAULT_POLICY,
    ) -> GraderVerdict:
        # This grader requires multiple runs — pass single-run calls
        if not case.metadata.get("run_hash"):
            return "PASS"
        expected_hash = case.metadata.get("expected_hash")
        if not expected_hash:
            return "PASS"

        actual = hashlib.sha256(result.agent_output.encode()).hexdigest()
        if actual != expected_hash:
            result.add_failure(
                EvalFailure(
                    failure_class="REPRODUCIBILITY_FAILURE",
                    case_id=case.case_id,
                    grader=self.name,
                    message="Output hash does not match expected reproducible result",
                    severity="warning",
                )
            )
            return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GRADER_REGISTRY: dict[str, Grader] = {
    g.name: g
    for g in [
        JSONValidityGrader(),
        SchemaValidityGrader(),
        FindingIdValidityGrader(),
        EvidenceReferenceValidityGrader(),
        ClaimEvidenceSupportGrader(),
        UnsupportedClaimGrader(),
        ForbiddenActionGrader(),
        ToolPolicyComplianceGrader(),
        RequiredToolUsageGrader(),
        CorrectAbstentionGrader(),
        WrongBusinessGrader(),
        GoldenCorpusRetentionGrader(),
        OutputReproducibilityGrader(),
    ]
}


def run_all_graders(
    result: EvalResult,
    case: EvalCase,
    expected: EvalExpectedResult | None = None,
    policy: EvalPolicy = DEFAULT_POLICY,
    grader_names: list[str] | None = None,
) -> EvalResult:
    """Run all (or selected) deterministic graders against a result.

    Deterministic failures are appended immediately; the caller should then
    call result.determine_overall() to compute the final verdict.
    """
    names = grader_names or list(GRADER_REGISTRY.keys())
    for name in names:
        grader = GRADER_REGISTRY.get(name)
        if grader is None:
            continue
        verdict = grader.grade(result, case, expected, policy)
        result.add_grader(name, verdict)
    result.determine_overall()
    return result
