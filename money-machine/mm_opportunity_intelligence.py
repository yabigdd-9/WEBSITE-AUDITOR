"""Shadow opportunity intelligence for WEBSITE-AUDITOR v45.

Pure, deterministic decision-support utilities for:
- identity confidence,
- evidence completeness,
- next-best-evidence planning,
- source/query quality analytics.

This module never sends outreach, calls a model, changes pipeline state, or
promotes a prospect. It is advisory/shadow-only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import re
import sqlite3
from urllib.parse import urlsplit

RULE_VERSION = "v45-shadow-intelligence-v1"

_GENERIC_NAME_TOKENS = {
    "and", "the", "limited", "ltd", "company", "co", "nz", "new", "zealand",
    "services", "service", "group", "solutions", "christchurch", "auckland",
    "wellington", "canterbury",
}

_NEGATIVE_STATES = {
    "REJECTED", "NO_VERIFIED_EMAIL", "PERMANENT_FAILURE", "SUPPRESSED", "DUPLICATE",
}
_QUALIFIED_OR_LATER = {
    "QUALIFIED", "CONTACT_PENDING", "CONTACT_RESOLVED", "VERIFICATION_PENDING",
    "VERIFIED", "REMEDIATION_PENDING", "DEMO_PENDING", "DEMO_READY", "QA_PENDING",
    "OUTREACH_PENDING", "APPROVAL_PENDING", "APPROVED", "READY_TO_SEND",
    "SENT", "RESPONDED", "CONVERTED",
}

_STAGE_REQUIREMENTS = {
    "DISCOVERED": ("business_name", "canonical_host", "source"),
    "IDENTITY_PENDING": ("business_name", "canonical_host", "source"),
    "IDENTITY_RESOLVED": ("business_name", "canonical_host", "source"),
    "AUDIT_PENDING": ("business_name", "canonical_host", "source"),
    "AUDITED": ("business_name", "canonical_host", "audit"),
    "QUALIFICATION_PENDING": (
        "business_name", "canonical_host", "audit", "commercial_evidence"
    ),
    "QUALIFIED": (
        "business_name", "canonical_host", "audit", "commercial_evidence"
    ),
    "CONTACT_PENDING": (
        "business_name", "canonical_host", "audit", "commercial_evidence",
        "contact_evidence",
    ),
    "CONTACT_RESOLVED": (
        "business_name", "canonical_host", "audit", "commercial_evidence",
        "contact_evidence",
    ),
    "VERIFICATION_PENDING": (
        "business_name", "canonical_host", "audit", "commercial_evidence",
        "contact_evidence",
    ),
}


def _row_dict(row) -> dict:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return {}


def _safe_json(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _host(url: str) -> str:
    try:
        parsed = urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    return (parsed.hostname or "").casefold().removeprefix("www.")


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{2,}", str(text or "").casefold())
        if token not in _GENERIC_NAME_TOKENS
    }


def identity_confidence(business, evidence: dict | None = None) -> dict:
    """Estimate identity confidence from deterministic first-party metadata.

    This is not proof that a business is legitimate. It quantifies how much
    identity evidence is present and exposes contradictions/missing signals.
    """
    b = _row_dict(business)
    evidence = dict(evidence or {})
    url = str(b.get("public_website") or evidence.get("public_website") or "")
    host = str(
        b.get("canonical_host")
        or evidence.get("canonical_host")
        or _host(url)
    )
    name = str(b.get("name") or evidence.get("business_name") or "")
    region = str(b.get("region") or evidence.get("region") or "")
    source = str(b.get("source") or evidence.get("source") or "")
    legal_name = str(evidence.get("legal_name") or "")
    trading_name = str(evidence.get("trading_name") or "")
    nzbn = str(evidence.get("nzbn") or "")
    discovery_quality = evidence.get("discovery_quality")
    if not isinstance(discovery_quality, dict):
        discovery_quality = {}

    score = 0.0
    supporting: list[str] = []
    contradicting: list[str] = []
    missing: list[str] = []

    if host:
        score += 0.35
        supporting.append("public_host_present")
        if host.endswith(".nz") or host.endswith(".co.nz"):
            score += 0.10
            supporting.append("nz_domain_signal")
    else:
        missing.append("canonical_host")

    if name:
        score += 0.10
        supporting.append("business_name_present")
    else:
        missing.append("business_name")

    name_tokens = _tokens(name)
    host_tokens = _tokens(host.replace(".", " "))
    if name_tokens and host_tokens:
        overlap = name_tokens & host_tokens
        host_compact = re.sub(r"[^a-z0-9]", "", host.casefold())
        joined_name = "".join(sorted(name_tokens, key=lambda token: name.casefold().find(token)))
        if overlap:
            score += 0.20
            supporting.append("name_domain_alignment:" + sorted(overlap)[0])
        elif joined_name and joined_name in host_compact:
            score += 0.20
            supporting.append("name_domain_alignment:compacted_name")
        else:
            # Absence of a deterministic match is missing/unknown evidence,
            # not proof of an identity conflict. Explicit contradictory
            # evidence (for example a discovery-quality rejection) is handled
            # separately below.
            missing.append("name_domain_alignment")
    elif host and name:
        missing.append("name_domain_alignment")

    if region:
        score += 0.05
        supporting.append("region_present")
    else:
        missing.append("region")

    if source:
        score += 0.05
        supporting.append("source_provenance_present")
    else:
        missing.append("source_provenance")

    if legal_name or trading_name:
        score += 0.075
        supporting.append("legal_or_trading_name_present")
    if nzbn:
        score += 0.075
        supporting.append("nzbn_present")

    disposition = discovery_quality.get("disposition")
    classification = discovery_quality.get("classification")
    if disposition == "ACCEPT":
        score += 0.05
        supporting.append("discovery_quality_accept")
    elif disposition == "REJECT":
        score -= 0.30
        contradicting.append(
            "discovery_quality_reject:" + str(classification or "unknown")
        )
    elif disposition == "REVIEW":
        missing.append("discovery_quality_decisive_signal")

    score = round(min(1.0, max(0.0, score)), 4)
    if contradicting:
        status = "CONFLICTED"
    elif score >= 0.75:
        status = "HIGH"
    elif score >= 0.50:
        status = "MEDIUM"
    else:
        status = "LOW"

    return {
        "confidence": score,
        "status": status,
        "supporting_signals": supporting,
        "contradicting_signals": contradicting,
        "missing_signals": sorted(set(missing)),
        "requires_review": bool(contradicting) or score < 0.50,
        "rule_version": RULE_VERSION,
        "shadow_only": True,
    }


def evidence_completeness(stage: str, observed) -> dict:
    """Measure whether the current decision has the evidence it claims to need.

    Missing evidence is UNKNOWN, not negative evidence.
    """
    observed_set = {str(item) for item in (observed or ()) if item}
    required = _STAGE_REQUIREMENTS.get(
        str(stage or ""),
        ("business_name", "canonical_host", "source"),
    )
    present = [name for name in required if name in observed_set]
    missing = [name for name in required if name not in observed_set]
    score = round(len(present) / len(required), 4) if required else 1.0
    return {
        "stage": str(stage or ""),
        "required": list(required),
        "present": present,
        "missing": missing,
        "completeness": score,
        "status": "COMPLETE" if not missing else "INCOMPLETE",
        "interpretation": (
            "Missing evidence is unknown and must not be treated as negative evidence."
        ),
        "rule_version": RULE_VERSION,
        "shadow_only": True,
    }


_ACTIONS = {
    "canonical_host": {
        "action": "VERIFY_PUBLIC_WEBSITE",
        "cost": "LOW",
        "information_gain": 0.95,
        "reason": "Resolve a canonical public website before deeper work.",
    },
    "business_name": {
        "action": "VERIFY_BUSINESS_IDENTITY",
        "cost": "LOW",
        "information_gain": 0.95,
        "reason": "Confirm the evidence belongs to a named active business.",
    },
    "source": {
        "action": "RECOVER_SOURCE_PROVENANCE",
        "cost": "LOW",
        "information_gain": 0.70,
        "reason": "Recover source/query provenance before trusting the candidate.",
    },
    "audit": {
        "action": "RUN_STATIC_AUDIT",
        "cost": "LOW",
        "information_gain": 0.90,
        "reason": "Technical need is unknown until deterministic audit evidence exists.",
    },
    "commercial_evidence": {
        "action": "INSPECT_FIRST_PARTY_COMMERCIAL_PAGES",
        "cost": "LOW",
        "information_gain": 0.92,
        "reason": (
            "Inspect first-party services, booking, quote and conversion evidence "
            "instead of treating missing commercial evidence as a negative signal."
        ),
    },
    "contact_evidence": {
        "action": "DISCOVER_OWN_SITE_CONTACT_EVIDENCE",
        "cost": "LOW",
        "information_gain": 0.75,
        "reason": "Inspect first-party contact evidence without guessing an address.",
    },
}


def next_best_evidence(identity: dict, completeness: dict) -> dict:
    """Recommend, but never execute, the next cheapest information-gain step."""
    missing = list(completeness.get("missing") or [])
    identity_missing = list(identity.get("missing_signals") or [])
    contradictions = list(identity.get("contradicting_signals") or [])

    if contradictions:
        return {
            "action": "HUMAN_IDENTITY_REVIEW",
            "cost": "HUMAN",
            "information_gain": 1.0,
            "reason": "Identity evidence conflicts; do not auto-advance.",
            "trigger": contradictions[0],
            "execute": False,
            "rule_version": RULE_VERSION,
        }

    if identity.get("confidence", 0.0) < 0.50:
        key = "canonical_host" if "canonical_host" in identity_missing else "business_name"
        chosen = dict(_ACTIONS[key])
        chosen.update({
            "trigger": key,
            "execute": False,
            "rule_version": RULE_VERSION,
        })
        return chosen

    candidates = []
    for key in missing:
        action = _ACTIONS.get(key)
        if action:
            candidates.append((action["information_gain"], key, action))
    if candidates:
        _, key, action = max(candidates, key=lambda item: (item[0], item[1]))
        chosen = dict(action)
        chosen.update({
            "trigger": key,
            "execute": False,
            "rule_version": RULE_VERSION,
        })
        return chosen

    return {
        "action": "NO_ADDITIONAL_EVIDENCE_REQUIRED",
        "cost": "NONE",
        "information_gain": 0.0,
        "reason": "The current stage has its declared minimum evidence set.",
        "trigger": None,
        "execute": False,
        "rule_version": RULE_VERSION,
    }


def counterfactual_explanation(state: str, assessment: dict,
                               qualification: dict | None = None) -> dict:
    """Explain what would have to change under the current v45 qualification rules.

    This is explanatory only. It does not rescore the prospect, predict that
    new evidence will be found, or authorize a state transition.
    """
    qualification = dict(qualification or {})
    identity = dict(assessment.get("identity") or {})
    completeness = dict(assessment.get("evidence_completeness") or {})
    missing = list(completeness.get("missing") or [])
    changes: list[dict] = []

    if identity.get("status") == "CONFLICTED":
        changes.append({
            "kind": "IDENTITY",
            "condition": "Resolve contradictory identity evidence with human review.",
            "guarantees_decision_change": False,
        })
    elif identity.get("confidence", 0.0) < 0.50:
        changes.append({
            "kind": "IDENTITY",
            "condition": "Add enough verified identity evidence to remove the low-confidence hold.",
            "guarantees_decision_change": False,
        })

    for field in missing:
        if field == "audit":
            changes.append({
                "kind": "EVIDENCE",
                "field": field,
                "condition": "Capture deterministic audit evidence before interpreting technical need.",
                "guarantees_decision_change": False,
            })
        elif field == "commercial_evidence":
            changes.append({
                "kind": "EVIDENCE",
                "field": field,
                "condition": (
                    "Capture substantive first-party service/booking/quote/commercial evidence "
                    "before interpreting missing commercial evidence as low opportunity."
                ),
                "guarantees_decision_change": False,
            })
        elif field == "contact_evidence":
            changes.append({
                "kind": "EVIDENCE",
                "field": field,
                "condition": "Capture verified first-party contact evidence.",
                "guarantees_decision_change": False,
            })

    commercial = qualification.get("commercial_score")
    technical = qualification.get("technical_score")
    if str(state or "") in {"REJECTED", "QUALIFICATION_PENDING"}:
        if isinstance(commercial, (int, float)) and not isinstance(commercial, bool):
            if commercial < 30:
                changes.append({
                    "kind": "CURRENT_RULE_THRESHOLD",
                    "axis": "commercial",
                    "current": float(commercial),
                    "threshold": 30.0,
                    "gap": round(30.0 - float(commercial), 1),
                    "condition": (
                        "A commercial qualification score at or above 30 would satisfy "
                        "the current commercial axis."
                    ),
                    "guarantees_decision_change": False,
                })
        if isinstance(technical, (int, float)) and not isinstance(technical, bool):
            if technical < 40:
                changes.append({
                    "kind": "CURRENT_RULE_THRESHOLD",
                    "axis": "technical",
                    "current": float(technical),
                    "threshold": 40.0,
                    "gap": round(40.0 - float(technical), 1),
                    "condition": (
                        "A supported technical score at or above 40 would satisfy "
                        "the current technical axis."
                    ),
                    "guarantees_decision_change": False,
                })
        elif technical is None:
            changes.append({
                "kind": "UNKNOWN_AXIS",
                "axis": "technical",
                "condition": "Technical qualification remains unknown until valid audit evidence exists.",
                "guarantees_decision_change": False,
            })

    if not changes:
        changes.append({
            "kind": "NONE_IDENTIFIED",
            "condition": "No decision-changing counterfactual is justified by the current evidence.",
            "guarantees_decision_change": False,
        })

    return {
        "current_state": str(state or ""),
        "counterfactuals": changes,
        "explanatory_only": True,
        "automatic_action": False,
        "rule_version": RULE_VERSION,
    }


def shadow_assessment(business, stage: str, observed=(), evidence=None) -> dict:
    identity = identity_confidence(business, evidence=evidence)
    completeness = evidence_completeness(stage, observed)
    return {
        "identity": identity,
        "evidence_completeness": completeness,
        "next_best_evidence": next_best_evidence(identity, completeness),
        "rule_version": RULE_VERSION,
        "shadow_only": True,
        "paid_calls": 0,
        "external_sends": 0,
    }


def _latest_event_evidence(d: sqlite3.Connection, business_id: int, to_state: str) -> dict:
    try:
        row = d.execute(
            "SELECT evidence FROM pipeline_events WHERE business_id=? AND to_state=? "
            "AND evidence IS NOT NULL ORDER BY id DESC LIMIT 1",
            (business_id, to_state),
        ).fetchone()
    except sqlite3.OperationalError:
        return {}
    return _safe_json(row["evidence"] if row else None)


def _table_exists(d: sqlite3.Connection, name: str) -> bool:
    return bool(d.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone())


def _infer_assessment_stage(
    d: sqlite3.Connection,
    business_id: int,
    current_state: str,
    identity_ev: dict,
    audit_ev: dict,
    qualification_ev: dict,
    contact_ev: dict,
) -> str:
    """Map terminal/review states back to the stage whose evidence is incomplete."""
    if current_state in _STAGE_REQUIREMENTS:
        return current_state

    try:
        row = d.execute(
            "SELECT from_state FROM pipeline_events "
            "WHERE business_id=? AND to_state=? AND from_state IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (business_id, current_state),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row and row["from_state"] in _STAGE_REQUIREMENTS:
        return row["from_state"]

    if current_state == "NO_VERIFIED_EMAIL":
        return "CONTACT_PENDING"
    if contact_ev:
        return "CONTACT_PENDING"
    if qualification_ev or audit_ev:
        return "QUALIFICATION_PENDING"
    if identity_ev:
        return "AUDIT_PENDING"
    return "DISCOVERED"


def prospect_snapshot(d: sqlite3.Connection, business_id: int) -> dict:
    """Read-only shadow assessment for one existing prospect."""
    business = d.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
    if not business:
        raise ValueError("Business not found: %s" % business_id)
    b = _row_dict(business)

    state = "DISCOVERED"
    pipeline_payload = {}
    if _table_exists(d, "pipeline_items"):
        row = d.execute(
            "SELECT state,payload FROM pipeline_items WHERE business_id=?",
            (business_id,),
        ).fetchone()
        if row:
            state = row["state"]
            pipeline_payload = _safe_json(row["payload"])

    identity_ev = _latest_event_evidence(d, business_id, "IDENTITY_RESOLVED")
    audit_ev = _latest_event_evidence(d, business_id, "AUDITED")
    qualification_ev = _latest_event_evidence(d, business_id, "QUALIFICATION_PENDING")
    qualified_ev = _latest_event_evidence(d, business_id, "QUALIFIED")
    contact_ev = _latest_event_evidence(d, business_id, "CONTACT_RESOLVED")

    merged_identity = dict(identity_ev)
    for source in (pipeline_payload, qualification_ev):
        for key in (
            "canonical_host", "legal_name", "trading_name", "nzbn",
            "discovery_quality",
        ):
            if key not in merged_identity and key in source:
                merged_identity[key] = source[key]

    assessment_stage = _infer_assessment_stage(
        d,
        business_id,
        state,
        identity_ev,
        audit_ev,
        qualification_ev,
        contact_ev,
    )

    observed = set()
    if b.get("name"):
        observed.add("business_name")
    if b.get("source"):
        observed.add("source")
    if b.get("canonical_host") or identity_ev.get("canonical_host") or _host(b.get("public_website")):
        observed.add("canonical_host")
    if audit_ev:
        observed.add("audit")
    commercial = qualified_ev or qualification_ev
    commercial_opportunity = (
        commercial.get("commercial_opportunity")
        if isinstance(commercial, dict) else None
    )
    if isinstance(commercial_opportunity, dict) and commercial_opportunity:
        observed.add("commercial_evidence")
    if contact_ev:
        observed.add("contact_evidence")
    if _table_exists(d, "prospect_outcomes"):
        if d.execute(
            "SELECT 1 FROM prospect_outcomes WHERE business_id=? LIMIT 1",
            (business_id,),
        ).fetchone():
            observed.add("outcome")

    assessment = shadow_assessment(
        b,
        stage=assessment_stage,
        observed=observed,
        evidence=merged_identity,
    )
    assessment.update({
        "business_id": business_id,
        "business_name": b.get("name"),
        "state": state,
        "assessment_stage": assessment_stage,
        "observed_evidence": sorted(observed),
        "derived": {
            "audit": audit_ev,
            "qualification": commercial,
        },
    })
    assessment["counterfactual"] = counterfactual_explanation(
        state,
        assessment,
        commercial,
    )
    return assessment


def _query_fingerprint(source: str) -> str:
    text = str(source or "")
    if text.startswith("searxng-local:"):
        return text.split(":", 1)[1][:160]
    return ""


def intelligence_summary(d: sqlite3.Connection, limit: int = 500) -> dict:
    """Return one bounded read-only summary of the shadow intelligence layer."""
    bounded_limit = max(1, min(int(limit), 2000))
    rows = d.execute(
        "SELECT id FROM businesses WHERE coalesce(is_dummy,0)=0 "
        "ORDER BY id LIMIT ?",
        (bounded_limit + 1,),
    ).fetchall()
    truncated = len(rows) > bounded_limit
    rows = rows[:bounded_limit]

    identity_status = Counter()
    completeness_status = Counter()
    next_actions = Counter()
    assessed = 0

    for row in rows:
        snapshot = prospect_snapshot(d, int(row["id"]))
        assessed += 1
        identity_status[str(snapshot["identity"].get("status") or "UNKNOWN")] += 1
        completeness_status[
            str(snapshot["evidence_completeness"].get("status") or "UNKNOWN")
        ] += 1
        next_actions[
            str(snapshot["next_best_evidence"].get("action") or "UNKNOWN")
        ] += 1

    sources = source_query_summary(d)
    diagnostics = Counter(
        str(item.get("diagnostic", {}).get("signal") or "UNKNOWN")
        for item in sources["sources"]
    )
    review = shadow_review_queue(d, limit=min(bounded_limit, 500))

    return {
        "prospects_assessed": assessed,
        "identity_status": dict(sorted(identity_status.items())),
        "evidence_completeness": dict(sorted(completeness_status.items())),
        "next_best_evidence": dict(sorted(next_actions.items())),
        "review_queue_count": review["count"],
        "source_count": sources["source_count"],
        "source_diagnostics": dict(sorted(diagnostics.items())),
        "bounded_limit": bounded_limit,
        "truncated": truncated,
        "automatic_action": False,
        "shadow_only": True,
        "rule_version": RULE_VERSION,
        "paid_calls": 0,
        "external_sends": 0,
    }


def shadow_review_queue(d: sqlite3.Connection, limit: int = 50) -> dict:
    """Return high-value human-review candidates without changing pipeline state.

    Only current negative/review states are considered. Priority is based on
    identity uncertainty, missing required evidence, and near-threshold current
    qualification scores. The queue is diagnostic and read-only.
    """
    if not _table_exists(d, "pipeline_items"):
        return {
            "items": [],
            "count": 0,
            "automatic_action": False,
            "shadow_only": True,
            "rule_version": RULE_VERSION,
            "paid_calls": 0,
            "external_sends": 0,
        }

    bounded_limit = max(1, min(int(limit), 500))
    rows = d.execute(
        """SELECT p.business_id,p.state
           FROM pipeline_items p
           JOIN businesses b ON b.id=p.business_id
           WHERE coalesce(b.is_dummy,0)=0
             AND p.state IN (
               'REJECTED','NO_VERIFIED_EMAIL','NEEDS_REVIEW',
               'PERMANENT_FAILURE'
             )
           ORDER BY p.business_id
           LIMIT ?""",
        (bounded_limit * 4,),
    ).fetchall()

    items = []
    for row in rows:
        snapshot = prospect_snapshot(d, int(row["business_id"]))
        reasons = []
        priority = 0

        identity = snapshot["identity"]
        completeness = snapshot["evidence_completeness"]
        qualification = snapshot.get("derived", {}).get("qualification") or {}

        if identity.get("status") == "CONFLICTED":
            priority += 50
            reasons.append("identity_conflict")
        elif identity.get("requires_review"):
            priority += 30
            reasons.append("low_identity_confidence")

        missing = list(completeness.get("missing") or [])
        if missing:
            priority += min(30, 10 + 5 * len(missing))
            reasons.append("missing_required_evidence:" + ",".join(sorted(missing)))

        commercial = qualification.get("commercial_score")
        technical = qualification.get("technical_score")
        if row["state"] == "REJECTED":
            if isinstance(commercial, (int, float)) and not isinstance(commercial, bool):
                if 20 <= float(commercial) < 30:
                    priority += 10
                    reasons.append("commercial_near_current_threshold")
            if isinstance(technical, (int, float)) and not isinstance(technical, bool):
                if 30 <= float(technical) < 40:
                    priority += 10
                    reasons.append("technical_near_current_threshold")

        if reasons:
            items.append({
                "business_id": snapshot["business_id"],
                "business_name": snapshot["business_name"],
                "state": snapshot["state"],
                "priority": priority,
                "reasons": reasons,
                "next_best_evidence": snapshot["next_best_evidence"],
                "counterfactual": snapshot["counterfactual"],
                "automatic_action": False,
            })

    items.sort(key=lambda item: (-item["priority"], item["business_id"]))
    items = items[:bounded_limit]
    return {
        "items": items,
        "count": len(items),
        "automatic_action": False,
        "shadow_only": True,
        "rule_version": RULE_VERSION,
        "paid_calls": 0,
        "external_sends": 0,
    }


def _source_diagnostic(total: int, qualification_yield: float,
                       negative_terminal_rate: float,
                       engagement_rate: float,
                       won_rate: float) -> dict:
    """Return a conservative diagnostic signal for one discovery source.

    This is advisory only. Small samples remain INSUFFICIENT_SAMPLE and no
    source is automatically promoted, suppressed, or removed from discovery.
    """
    if total < 10:
        signal = "INSUFFICIENT_SAMPLE"
        reason = "Need at least 10 non-dummy prospects before judging source quality."
    elif won_rate > 0 or engagement_rate >= 0.20:
        signal = "PROMISING"
        reason = "Observed downstream engagement/outcome evidence is present."
    elif negative_terminal_rate >= 0.70 and qualification_yield <= 0.10:
        signal = "POOR_YIELD"
        reason = "High negative-terminal rate with very low qualification yield."
    else:
        signal = "MIXED"
        reason = "Evidence is mixed; keep observing before changing discovery behavior."
    return {
        "signal": signal,
        "reason": reason,
        "minimum_sample": 10,
        "sample_size": total,
        "automatic_action": False,
    }


def source_query_summary(d: sqlite3.Connection) -> dict:
    """Read-only yield/rejection/outcome analytics by discovery source."""
    has_pipeline = _table_exists(d, "pipeline_items")
    query = (
        "SELECT b.id,b.source,p.state FROM businesses b "
        "LEFT JOIN pipeline_items p ON p.business_id=b.id "
        "WHERE coalesce(b.is_dummy,0)=0"
        if has_pipeline else
        "SELECT b.id,b.source,NULL as state FROM businesses b "
        "WHERE coalesce(b.is_dummy,0)=0"
    )
    rows = d.execute(query).fetchall()

    won_ids: set[int] = set()
    replied_ids: set[int] = set()
    if _table_exists(d, "prospect_outcomes"):
        for row in d.execute(
            "SELECT business_id,outcome FROM prospect_outcomes "
            "WHERE outcome IN ('WON','REPLIED','CALL_OR_DISCOVERY')"
        ).fetchall():
            if row["outcome"] == "WON":
                won_ids.add(int(row["business_id"]))
            else:
                replied_ids.add(int(row["business_id"]))

    grouped = defaultdict(lambda: {
        "total": 0,
        "states": Counter(),
        "qualified_businesses": 0,
        "negative_terminal_businesses": 0,
        "won_businesses": 0,
        "engaged_businesses": 0,
    })

    for row in rows:
        source = str(row["source"] or "unknown")
        stats = grouped[source]
        stats["total"] += 1
        state = str(row["state"] or "UNTRACKED")
        stats["states"][state] += 1
        if state in _QUALIFIED_OR_LATER:
            stats["qualified_businesses"] += 1
        if state in _NEGATIVE_STATES:
            stats["negative_terminal_businesses"] += 1
        bid = int(row["id"])
        if bid in won_ids:
            stats["won_businesses"] += 1
        if bid in replied_ids or bid in won_ids:
            stats["engaged_businesses"] += 1

    sources = []
    for source, stats in grouped.items():
        total = stats["total"]
        qualification_yield = round(
            stats["qualified_businesses"] / total, 4
        ) if total else 0.0
        negative_terminal_rate = round(
            stats["negative_terminal_businesses"] / total, 4
        ) if total else 0.0
        won_rate = round(stats["won_businesses"] / total, 4) if total else 0.0
        engagement_rate = round(
            stats["engaged_businesses"] / total, 4
        ) if total else 0.0
        sources.append({
            "source": source,
            "query_fingerprint": _query_fingerprint(source),
            "total": total,
            "qualified_businesses": stats["qualified_businesses"],
            "negative_terminal_businesses": stats["negative_terminal_businesses"],
            "won_businesses": stats["won_businesses"],
            "engaged_businesses": stats["engaged_businesses"],
            "qualification_yield": qualification_yield,
            "negative_terminal_rate": negative_terminal_rate,
            "won_rate": won_rate,
            "engagement_rate": engagement_rate,
            "diagnostic": _source_diagnostic(
                total,
                qualification_yield,
                negative_terminal_rate,
                engagement_rate,
                won_rate,
            ),
            "states": dict(sorted(stats["states"].items())),
        })

    sources.sort(key=lambda item: (-item["total"], item["source"]))
    return {
        "sources": sources,
        "source_count": len(sources),
        "business_count": sum(item["total"] for item in sources),
        "rule_version": RULE_VERSION,
        "shadow_only": True,
        "paid_calls": 0,
        "external_sends": 0,
    }
