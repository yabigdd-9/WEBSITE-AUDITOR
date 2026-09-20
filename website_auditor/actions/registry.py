from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any
from ..models import Action, Risk, stable_id

@dataclass(frozen=True)
class ActionDefinition:
    id: str; name: str; category: str; risk: Risk; connector: str
    requires_approval: bool = False; requires_authorization: bool = True; reversible: bool = False
    verification_checks: tuple[str, ...] = (); rollback_action_id: str | None = None

ACTION_DEFINITIONS: dict[str, ActionDefinition] = {
    "headers.add_hsts_propose": ActionDefinition(id="headers.add_hsts_propose", name="Propose HSTS header change", category="security", risk=Risk.MEDIUM, connector="local", requires_approval=True, requires_authorization=True, reversible=True, verification_checks=("security.hsts_present",)),
    "headers.add_security_headers_propose": ActionDefinition(id="headers.add_security_headers_propose", name="Propose security headers bundle (CSP, X-Frame, X-Content-Type, Referrer-Policy, Permissions-Policy)", category="security", risk=Risk.MEDIUM, connector="local", requires_approval=True, requires_authorization=True, reversible=True, verification_checks=("security.headers_present",)),
    "content.add_meta_description_patch": ActionDefinition(id="content.add_meta_description_patch", name="Generate/add missing meta/title patch", category="seo", risk=Risk.LOW, connector="local", requires_approval=False, requires_authorization=True, reversible=True, verification_checks=("seo.meta_present",)),
    "content.add_canonical_patch": ActionDefinition(id="content.add_canonical_patch", name="Generate/add missing canonical URL patch", category="seo", risk=Risk.LOW, connector="local", requires_approval=False, requires_authorization=True, reversible=True, verification_checks=("seo.canonical_present",)),
    "content.add_og_tags_patch": ActionDefinition(id="content.add_og_tags_patch", name="Generate/add missing Open Graph tags patch", category="seo", risk=Risk.LOW, connector="local", requires_approval=False, requires_authorization=True, reversible=True, verification_checks=("seo.og_present",)),
    "content.fix_broken_links_patch": ActionDefinition(id="content.fix_broken_links_patch", name="Generate broken link fix patch (301 redirects or link removal)", category="seo", risk=Risk.MEDIUM, connector="local", requires_approval=True, requires_authorization=True, reversible=True, verification_checks=("link.no_404",)),
    "review.defect": ActionDefinition(id="review.defect", name="Queue defect for human review", category="workflow", risk=Risk.LOW, connector="local", requires_approval=False, requires_authorization=False, reversible=True, verification_checks=("review.queued",)),
    "review.defect_with_details": ActionDefinition(id="review.defect_with_details", name="Queue detailed defect for human review with full evidence", category="workflow", risk=Risk.LOW, connector="local", requires_approval=False, requires_authorization=False, reversible=True, verification_checks=("review.queued",)),
}

DEFECT_TO_ACTION: dict[str, str] = {
    "Missing HSTS": "headers.add_hsts_propose", "Missing X-Frame-Options": "headers.add_security_headers_propose",
    "Missing Referrer-Policy": "headers.add_security_headers_propose", "Missing Permissions-Policy": "headers.add_security_headers_propose",
    "Missing X-Content-Type": "headers.add_security_headers_propose", "Missing CSP": "headers.add_security_headers_propose",
    "Missing page title": "content.add_meta_description_patch",
    "Missing meta description": "content.add_meta_description_patch",
    "Missing canonical": "content.add_canonical_patch",
    "Missing Open Graph": "content.add_og_tags_patch",
    "broken link": "content.fix_broken_links_patch",
    "No contact form": "review.defect",
    "HTML markup error": "review.defect",
    "Missing H1": "review.defect_with_details",
    "Thin content": "review.defect_with_details",
    "No structured data": "review.defect_with_details",
    "Missing <title>": "content.add_meta_description_patch",
}

def get_definition(action_id: str) -> ActionDefinition: return ACTION_DEFINITIONS[action_id]

def action_from_defect(domain: str, defect: dict[str, Any], environment: str = "local") -> Action:
    defect_text = str(defect.get("issue", "") or defect.get("message", "") or defect.get("defect", "")).lower()
    action_def_id = "review.defect"
    for key, action_id in DEFECT_TO_ACTION.items():
        if key.lower() in defect_text: action_def_id = action_id; break
    definition = get_definition(action_def_id)
    normalized_defect = json.dumps(defect, sort_keys=True, default=str)
    
    # Build fix details for richer payloads
    fix_details = {
        "issue": defect_text,
        "defect_key": defect.get("defect_key") or defect.get("key") or defect.get("id"),
        "severity": defect.get("severity") or defect.get("priority"),
        "impact": defect.get("impact") or defect.get("message"),
        "raw_data": defect,
    }
    
    return Action(
        action_id=stable_id("act", [domain, definition.id, defect_text]), name=definition.name, category=definition.category,
        risk=definition.risk, connector=definition.connector, domain=domain, environment=environment,
        requires_approval=definition.requires_approval, requires_authorization=definition.requires_authorization,
        reversible=definition.reversible, idempotency_key=stable_id("idem", [domain, definition.id, defect_text, normalized_defect]),
        payload={"defect": defect, "details": fix_details}, verification_checks=list(definition.verification_checks), rollback_action_id=definition.rollback_action_id,
    )

SAMPLE_DEFECTS: list[dict[str, Any]] = [{"issue": "Missing HSTS", "severity": "medium"}, {"issue": "Missing page title", "severity": "high"}]
