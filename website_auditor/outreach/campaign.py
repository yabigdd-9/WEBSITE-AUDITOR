"""Dry-run campaign simulation with no transport capability."""
from __future__ import annotations

import csv
import json
import re
import string
from pathlib import Path
from typing import Any

from .ranking import rank_prospect
from .suppression import SuppressionStore, normalize_domain


SPAM_TERMS = {
    "act now",
    "buy now",
    "guaranteed",
    "100% free",
    "limited time",
    "urgent",
    "winner",
    "risk free",
    "no obligation",
    "make money",
}
FALSE_URGENCY = {"act now", "limited time", "urgent", "last chance", "today only"}
OPT_OUT_TERMS = {"unsubscribe", "opt out", "opt-out", "reply no", "reply stop"}


class SafeTemplate(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def template_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name:
            fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return fields


def render_template(template: str, variables: dict[str, Any]) -> tuple[str, list[str]]:
    required = template_fields(template)
    missing = sorted(
        field for field in required if variables.get(field) in (None, "")
    )
    rendered = template.format_map(SafeTemplate({k: str(v) for k, v in variables.items()}))
    return rendered, missing


def split_subject_body(rendered: str) -> tuple[str, str]:
    lines = rendered.splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        return lines[0].split(":", 1)[1].strip(), "\n".join(lines[1:]).strip()
    return "", rendered.strip()


def spam_risk(subject: str, body: str) -> dict[str, Any]:
    combined = f"{subject}\n{body}"
    lower = combined.lower()
    issues: list[str] = []
    score = 0

    if not subject:
        issues.append("missing subject")
        score += 10
    if len(subject) > 65:
        issues.append("long subject")
        score += 8
    alpha = [char for char in subject if char.isalpha()]
    if alpha:
        caps_ratio = sum(char.isupper() for char in alpha) / len(alpha)
        if caps_ratio > 0.5 and len(alpha) >= 8:
            issues.append("high subject caps ratio")
            score += 12
    if subject.count("!") + subject.count("?") >= 3:
        issues.append("excessive subject punctuation")
        score += 8

    triggers = sorted(term for term in SPAM_TERMS if term in lower)
    if triggers:
        issues.append("spam-trigger phrases: " + ", ".join(triggers))
        score += min(25, len(triggers) * 6)

    links = re.findall(r"https?://\S+", body)
    if len(links) > 3:
        issues.append("high link count")
        score += min(15, (len(links) - 3) * 3)

    urgency = sorted(term for term in FALSE_URGENCY if term in lower)
    if urgency:
        issues.append("urgency language requires factual review: " + ", ".join(urgency))
        score += 8

    return {
        "score": min(100, score),
        "risk": "high" if score >= 40 else "medium" if score >= 20 else "low",
        "issues": issues,
        "link_count": len(links),
    }


def compliance_review(
    variables: dict[str, Any],
    subject: str,
    body: str,
    *,
    suppression: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []

    email = str(variables.get("email") or variables.get("recipient") or "")
    domain = normalize_domain(email or variables.get("domain") or "")

    if suppression.get("suppressed"):
        blockers.append(
            f"suppression match ({suppression.get('scope')}): {suppression.get('reason') or 'suppressed'}"
        )
    if not email or "@" not in email:
        blockers.append("no valid recipient email supplied")
    if not variables.get("sender_name"):
        warnings.append("sender identity missing")
    if not variables.get("agency_name"):
        warnings.append("agency/business identity missing")
    if not variables.get("physical_address"):
        warnings.append("physical business address not supplied")
    if not any(term in body.lower() for term in OPT_OUT_TERMS):
        warnings.append("clear opt-out/reply instruction not detected")
    if not subject:
        warnings.append("subject line missing")

    country = str(variables.get("country") or "").strip().upper()
    if country in {"NZ", "NEW ZEALAND"} or domain.endswith(".nz"):
        warnings.append(
            "NZ prospect: human review should confirm consent/basis, accurate sender identity, "
            "functional unsubscribe and other Unsolicited Electronic Messages Act requirements"
        )
    elif country in {"AU", "AUSTRALIA"} or domain.endswith(".au"):
        warnings.append("AU prospect: human review should confirm Spam Act requirements")
    elif country in {"US", "USA", "UNITED STATES"}:
        warnings.append("US prospect: human review should confirm CAN-SPAM requirements")
    elif country in {"UK", "GB", "EU"}:
        warnings.append("UK/EU prospect: human review should confirm PECR/GDPR basis and notice requirements")
    else:
        warnings.append("jurisdiction/basis requires human compliance review before any send")

    return {
        "blocked": bool(blockers),
        "blockers": blockers,
        "warnings": warnings,
        "legal_note": "Simulation only; this is a checklist, not legal advice or approval to send.",
    }


def read_prospects(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def simulate_campaign(
    prospects: list[dict[str, Any]],
    template: str,
    *,
    suppression_store: SuppressionStore,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = dict(defaults or {})
    results: list[dict[str, Any]] = []
    reviewable = 0

    for index, prospect in enumerate(prospects, 1):
        variables = {**defaults, **prospect}
        email = str(variables.get("email") or variables.get("recipient") or "")
        domain = str(variables.get("domain") or normalize_domain(email))
        variables["domain"] = domain

        rendered, missing = render_template(template, variables)
        subject, body = split_subject_body(rendered)
        suppression = suppression_store.check(email=email, domain=domain)
        spam = spam_risk(subject, body)
        compliance = compliance_review(
            variables,
            subject,
            body,
            suppression=suppression,
        )
        ranking = rank_prospect(variables)

        can_review_for_send = (
            not missing
            and not compliance["blocked"]
            and spam["risk"] != "high"
        )
        if can_review_for_send:
            reviewable += 1

        results.append(
            {
                "row": index,
                "domain": domain,
                "recipient": email,
                "ranking": ranking,
                "missing_variables": missing,
                "suppression": suppression,
                "spam_risk": spam,
                "compliance": compliance,
                "rendered_draft": rendered,
                "eligible_for_human_send_review": can_review_for_send,
            }
        )

    results.sort(
        key=lambda item: (
            -float(item["ranking"]["review_score"]),
            str(item.get("domain") or ""),
            int(item["row"]),
        )
    )
    return {
        "schema_version": 1,
        "mode": "simulation_only",
        "prospect_count": len(results),
        "eligible_for_human_send_review_count": reviewable,
        "transport_available": False,
        "results": results,
        "note": "No email is sent. Eligibility means ready for human review, not approved to send.",
    }


def write_simulation(report: dict[str, Any], output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    return destination
