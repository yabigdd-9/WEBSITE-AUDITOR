"""Passive P1 checks that operate on already-fetched evidence."""
from __future__ import annotations

import re
from typing import Any

import bs4
import dns.exception
import dns.resolver

from plugins.image_perf_auditor import audit_image_performance
from plugins.tech_stack_detector import detect_tech_stack


NZ_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?64[\s.-]?(?:2\d|[3-9])|0(?:2\d|[3-9]))[\s.-]?\d{2,4}[\s.-]?\d{3,4}(?!\d)"
)
NZ_POSTCODE_RE = re.compile(r"\b\d{4}\b")
NZ_ADDRESS_TERMS = re.compile(
    r"\b(?:street|st|road|rd|avenue|ave|drive|dr|lane|ln|place|pl|terrace|tce|crescent|cres)\b",
    re.IGNORECASE,
)


def accessibility_basics(soup: bs4.BeautifulSoup) -> tuple[list[dict], dict[str, Any]]:
    defects: list[dict] = []
    html_tag = soup.find("html")
    lang = (html_tag.get("lang") or "").strip() if html_tag else ""
    if not lang:
        defects.append(
            {
                "defect": "Missing HTML lang attribute",
                "impact": "Assistive technology may not know the page language",
            }
        )

    unlabeled: list[str] = []
    for control in soup.find_all(["input", "select", "textarea"]):
        if control.name == "input" and str(control.get("type") or "text").lower() in {
            "hidden",
            "submit",
            "button",
            "reset",
            "image",
        }:
            continue
        control_id = str(control.get("id") or "").strip()
        has_label = bool(control_id and soup.find("label", attrs={"for": control_id}))
        has_wrapping_label = control.find_parent("label") is not None
        has_aria = bool(control.get("aria-label") or control.get("aria-labelledby"))
        if not (has_label or has_wrapping_label or has_aria):
            unlabeled.append(control.name)

    if unlabeled:
        defects.append(
            {
                "defect": f"{len(unlabeled)} form control(s) missing accessible labels",
                "impact": "Forms may be difficult to use with screen readers",
            }
        )

    empty_buttons = 0
    for button in soup.find_all("button"):
        text = button.get_text(" ", strip=True)
        if not text and not button.get("aria-label") and not button.get("aria-labelledby"):
            empty_buttons += 1
    if empty_buttons:
        defects.append(
            {
                "defect": f"{empty_buttons} button(s) missing accessible names",
                "impact": "Screen-reader users may not know what the control does",
            }
        )

    return defects, {
        "html_lang": lang or None,
        "unlabeled_form_controls": len(unlabeled),
        "unnamed_buttons": empty_buttons,
    }


def cookie_security(headers: dict[str, Any], *, is_https: bool) -> tuple[list[dict], dict[str, Any]]:
    raw = ""
    for key, value in (headers or {}).items():
        if str(key).lower() == "set-cookie":
            raw = str(value)
            break
    if not raw:
        return [], {"cookies_observed": False}

    # This is intentionally conservative: combined Set-Cookie headers are treated as one
    # observation rather than pretending we can reconstruct every cookie perfectly.
    lower = raw.lower()
    defects: list[dict] = []
    if is_https and "secure" not in lower:
        defects.append(
            {
                "defect": "Observed cookie without Secure attribute",
                "impact": "Cookie confidentiality may be weaker on insecure transport",
            }
        )
    if "samesite=" not in lower:
        defects.append(
            {
                "defect": "Observed cookie without SameSite attribute",
                "impact": "Cross-site request protections may be weaker",
            }
        )
    return defects, {
        "cookies_observed": True,
        "secure_attribute_observed": "secure" in lower,
        "samesite_attribute_observed": "samesite=" in lower,
        "httponly_attribute_observed": "httponly" in lower,
    }


def nz_business_signals(text: str, html: str) -> dict[str, Any]:
    combined = f"{text}\n{html}"
    phones = sorted(set(match.group(0).strip() for match in NZ_PHONE_RE.finditer(combined)))
    address_signal = bool(NZ_ADDRESS_TERMS.search(combined) and NZ_POSTCODE_RE.search(combined))
    return {
        "nz_phone_count": len(phones),
        "nz_phone_examples": phones[:3],
        "postal_address_signal": address_signal,
        "nz_domain": ".nz" in combined.lower(),
    }


def passive_stack_and_images(html: str, headers: dict[str, Any]) -> dict[str, Any]:
    normalized_headers = dict(headers or {})
    normalized_headers.update({str(key).title(): value for key, value in (headers or {}).items()})
    return {
        "tech_stack": sorted(detect_tech_stack(html, normalized_headers)),
        "image_performance": audit_image_performance(html),
    }


def _txt_records(name: str, timeout: float = 4.0) -> list[str]:
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = timeout
    resolver.lifetime = timeout
    try:
        answer = resolver.resolve(name, "TXT")
    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.exception.Timeout,
    ):
        return []
    records: list[str] = []
    for item in answer:
        try:
            value = b"".join(item.strings).decode("utf-8", errors="replace")
        except AttributeError:
            value = item.to_text().strip('"')
        records.append(value)
    return records


def email_dns_security(domain: str, *, email_signal: bool) -> tuple[list[dict], dict[str, Any]]:
    """Check SPF and DMARC; only raise missing-record findings when the site exposes email."""
    spf_records = [item for item in _txt_records(domain) if item.lower().startswith("v=spf1")]
    dmarc_records = [
        item for item in _txt_records(f"_dmarc.{domain}") if item.lower().startswith("v=dmarc1")
    ]

    common_dkim_selectors: dict[str, bool] = {}
    if email_signal:
        for selector in ("google", "default", "selector1", "selector2"):
            records = _txt_records(f"{selector}._domainkey.{domain}", timeout=1.5)
            common_dkim_selectors[selector] = any(
                "v=dkim1" in item.lower() or "p=" in item.lower() for item in records
            )

    defects: list[dict] = []
    if email_signal and not spf_records:
        defects.append(
            {
                "defect": "No SPF record detected",
                "impact": "Domain email spoofing controls may be incomplete",
            }
        )
    if email_signal and not dmarc_records:
        defects.append(
            {
                "defect": "No DMARC record detected",
                "impact": "Domain email spoofing policy/reporting may be incomplete",
            }
        )

    return defects, {
        "email_signal": email_signal,
        "spf_present": bool(spf_records),
        "dmarc_present": bool(dmarc_records),
        "spf_records": spf_records[:3],
        "dmarc_records": dmarc_records[:3],
        "dkim_common_selector_hits": common_dkim_selectors,
        "dkim_note": (
            "No generic DKIM absence finding is emitted because selectors are deployment-specific; "
            "common selectors are reported as evidence only."
        ),
    }
