"""Core typed models, registry, evidence, scoring and remediation helpers."""

from .evidence import build_page_evidence
from .normalize import normalize_defects
from .profiles import detect_site_type, resolve_profile
from .remediation import RemediationStateStore, initial_remediation
from .scoring import category_scores

__all__ = [
    "build_page_evidence",
    "normalize_defects",
    "detect_site_type",
    "resolve_profile",
    "RemediationStateStore",
    "initial_remediation",
    "category_scores",
]
