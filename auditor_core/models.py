"""Typed schemas for evidence-first website audit results."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    cosmetic = "cosmetic"


class FindingStatus(str, Enum):
    passed = "pass"
    fail = "fail"
    warn = "warn"
    info = "info"
    skipped = "skipped"
    error = "error"


class RemediationStatus(str, Enum):
    detected = "detected"
    acknowledged = "acknowledged"
    scheduled = "scheduled"
    in_progress = "in_progress"
    patched = "patched"
    verified = "verified"
    regressed = "regressed"
    accepted_risk = "accepted_risk"
    false_positive = "false_positive"


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str
    captured_at: datetime
    source: Literal["static", "rendered", "inferred"] = "static"
    http_status: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    html_sha256: str | None = None
    html_size_bytes: int | None = None
    html_snippet: str | None = None
    selector: str | None = None
    check_version: str = "1.0.0"
    tool_version: str = "website-auditor-v4"


class RemediationState(BaseModel):
    status: RemediationStatus = RemediationStatus.detected
    owner: str | None = None
    due_date: str | None = None
    fix_reference: str | None = None
    patch_file: str | None = None
    verification_command: str | None = None
    last_verified_at: str | None = None
    regression_alert: bool = False


class CheckDefinition(BaseModel):
    id: str
    name: str
    category: str
    severity: Severity
    standards: list[str] = Field(default_factory=list)
    auto_fixable: bool = False
    evidence_required: list[str] = Field(default_factory=list)
    default_priority: str = "P5"
    confidence: float = 0.9
    human_review: bool = False
    patterns: list[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


class Finding(BaseModel):
    check_id: str
    status: FindingStatus = FindingStatus.fail
    severity: Severity
    confidence: float = 0.9
    message: str
    business_impact: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    affected_urls: list[str] = Field(default_factory=list)
    category: str
    standards: list[str] = Field(default_factory=list)
    auto_fixable: bool = False
    human_review: bool = False
    priority: str = "P5"
    remediation: RemediationState = Field(default_factory=RemediationState)
    legacy_defect: dict[str, Any] | None = None

    @field_validator("confidence")
    @classmethod
    def _finding_confidence_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value
