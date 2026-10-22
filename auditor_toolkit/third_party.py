"""
Third-party request inventory.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlsplit

from auditor_toolkit.checks import Finding


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}:{port}"


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Finding], dict[str, Any]]:
    """Analyse HTML for third-party request findings."""
    findings: list[Finding] = []
    origin = _origin(url)

    from bs4 import BeautifulSoup

    external: dict[str, int] = {}
    soup = BeautifulSoup(html, "lxml")
    for tag, attr in (("script", "src"), ("iframe", "src"), ("img", "src"),
                      ("link", "href"), ("source", "src")):
        for element in soup.find_all(tag):
            if tag == "link" and not set(element.get("rel", [])).intersection(
                {"stylesheet", "preload", "modulepreload", "icon"}
            ):
                continue
            value = str(element.get(attr, ""))
            try:
                ext_origin = _origin(urljoin(url, value))
            except ValueError:
                continue
            if ext_origin and ext_origin != origin:
                external[ext_origin] = external.get(ext_origin, 0) + 1

    evidence = {
        "url": url,
        "external_domains": sorted(external),
        "external_request_count": sum(external.values()),
        "limitation": "DOM references only; not proof that a request completed.",
    }

    if external:
        findings.append(
            Finding(
                "third-party-requests",
                "Third-party requests detected",
                f"{len(external)} external domains, {sum(external.values())} requests",
                "medium",
                url,
                check="third_party",
                evidence_source="dom:external resource attributes",
                observed=f"{len(external)} external domains referenced: {', '.join(sorted(external))}",
                business_impact="Third-party scripts and assets add page weight, create "
                "privacy/cookie exposure, and can break if the vendor changes or goes down.",
                remediation_action="Audit each third-party domain; remove unused ones and "
                "consider self-hosting critical assets.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="M",
            )
        )

    return findings, evidence



def analyse_rendered(data: dict, url: str) -> tuple[list[Finding], dict[str, Any]]:
    """Inventory attempted browser requests, including requests later blocked."""
    requests = data.get("resource_requests")
    if not isinstance(requests, list) or not all(isinstance(item, str) for item in requests):
        raise ValueError("Browser resource request capture unavailable")
    origin = _origin(url)
    external: dict[str, int] = {}
    for item in requests:
        try:
            target = _origin(item)
        except ValueError:
            continue
        if target and target != origin:
            external[target] = external.get(target, 0) + 1
    evidence = {"url": url, "external_domains": sorted(external),
                "external_request_count": sum(external.values()),
                "limitation": "Up to 1000 attempted requests; not proof of successful delivery."}
    findings = []
    if external:
        findings.append(Finding(
            "third-party-requests", "Third-party requests detected",
            f"{len(external)} external origins requested", "medium", url,
            check="third_party", evidence_source="browser:request events",
            observed=", ".join(sorted(external)),
            remediation_action="Review external resource dependencies.",
        ))
    return findings, evidence
