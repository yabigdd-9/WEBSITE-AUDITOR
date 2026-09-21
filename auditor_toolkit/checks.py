from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

SEVERITY_WEIGHT = {"low": 4, "medium": 8, "high": 16, "critical": 30}


@dataclass(frozen=True)
class Finding:
    defect_key: str
    defect: str
    impact: str
    severity: str = "medium"
    source_url: str = ""
    review_required: bool = True
    check: str = "page"
    selector: str = ""
    confidence: str = "observed"
    # P5 evidence-first fields. Material findings must carry observed evidence
    # (source/selector/observed) plus a remediation pointer and effort band.
    # "heuristic" confidence marks weaker evidence — never silently.
    evidence_source: str = ""
    observed: str = ""
    business_impact: str = ""
    remediation_action: str = ""
    remediation_automation: str = "HUMAN_REVIEW"
    effort_band: str = "M"


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[Finding] = []
    for finding in findings:
        key = (finding.defect_key, finding.source_url, finding.selector or finding.impact)
        if key not in seen:
            seen.add(key)
            deduped.append(finding)
    return deduped


def score_findings(findings: list[Finding], complete: bool = True) -> dict[str, int | None]:
    """Legacy severity-sum entry point. New code should prefer
    scoring.score_from_findings() on finding records, which returns a full
    deduction breakdown linked to finding evidence."""
    severity = min(100, sum(SEVERITY_WEIGHT.get(f.severity, 8) for f in findings))
    return {
        "score": severity,
        "severity_score": severity,
        "health_score": max(0, 100 - severity) if complete else None,
    }


def analyse_html(html: str, url: str) -> tuple[list[Finding], dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    findings: list[Finding] = []
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    meta_description = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    og_tags = soup.find_all("meta", property=re.compile("^og:", re.I))
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]+", soup.get_text(" "))
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    schema = soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)})
    if not title:
        findings.append(
            Finding(
                "missing_title",
                "Missing page title",
                "Search snippet risk",
                "high",
                url,
                selector="head > title",
                evidence_source="dom:head>title absent",
                observed="no <title> element with text",
                business_impact="Search results show a bare URL; fewer clicks from search.",
                remediation_action="Add a unique descriptive <title> (50-60 chars).",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )
    if not meta_description or not (meta_description.get("content") or "").strip():
        findings.append(
            Finding(
                "missing_meta_description",
                "Missing meta description",
                "Lower CTR",
                "medium",
                url,
                selector='head > meta[name="description"]',
                evidence_source='dom:meta[name="description"] absent or empty',
                observed="no usable meta description content",
                business_impact="Search snippets fall back to page text; lower click-through.",
                remediation_action="Write a 120-155 char meta description per key page.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )
    if not canonical or not canonical.get("href"):
        findings.append(
            Finding(
                "missing_canonical_url",
                "Missing canonical URL",
                "Duplicate content risk",
                "medium",
                url,
                selector='head > link[rel="canonical"]',
                evidence_source='dom:link[rel="canonical"] absent',
                observed="no canonical href declared",
                business_impact="Search engines may split ranking across URL variants.",
                remediation_action="Add a self-referencing canonical link tag.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )
    if not og_tags:
        findings.append(
            Finding(
                "missing_open_graph_tags",
                "Missing Open Graph tags",
                "Poor social preview",
                "medium",
                url,
                selector='head > meta[property^="og:"]',
                evidence_source="dom:no meta[property^=og:] elements",
                observed="zero Open Graph tags",
                business_impact="Link shares render as plain text; less social traffic.",
                remediation_action="Add og:title, og:description, og:image tags.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="S",
            )
        )
    if len(words) < 200:
        findings.append(
            Finding(
                "thin_content_200_words",
                "Thin content (<200 words)",
                "Review page purpose",
                "medium",
                url,
                confidence="heuristic",
                evidence_source=f"text:word_count={len(words)}",
                observed=f"page body contains {len(words)} words (<200 threshold)",
                business_impact="Thin pages rarely rank or convert; intent unclear.",
                remediation_action="Expand page with real service proof (photos, FAQs, reviews).",
                remediation_automation="HUMAN_REVIEW",
                effort_band="M",
            )
        )
    if not viewport:
        findings.append(
            Finding(
                "viewport",
                "Missing viewport metadata",
                "Mobile layout review",
                "medium",
                url,
                selector='head > meta[name="viewport"]',
                evidence_source='dom:meta[name="viewport"] absent',
                observed="no viewport meta tag",
                business_impact="Mobile browsers may render a zoomed-out desktop layout.",
                remediation_action="Add viewport meta (width=device-width,initial-scale=1).",
                remediation_automation="AUTO_SAFE",
                effort_band="XS",
            )
        )
    if not schema:
        findings.append(
            Finding(
                "schema_missing",
                "No structured data found",
                "Eligibility not guaranteed",
                "low",
                url,
                check="schema",
                selector='script[type="application/ld+json"]',
                confidence="heuristic",
                evidence_source="dom:no ld+json script blocks",
                observed="zero structured-data blocks",
                business_impact="No rich-result eligibility signals for local business info.",
                remediation_action="Add LocalBusiness JSON-LD with name, phone, address.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="S",
            )
        )
    for index, image in enumerate(soup.find_all("img"), 1):
        if image.get("alt") is None:
            findings.append(
                Finding(
                    "image-alt",
                    "Image missing alt attribute",
                    image.get("src") or "image",
                    "high",
                    url,
                    check="accessibility_static",
                    selector=f"img:nth-of-type({index})",
                    evidence_source="dom:img without alt attribute",
                    observed=f"img src={image.get('src') or '?'} has no alt",
                    business_impact="Screen-reader users miss the image meaning; weaker image SEO.",
                    remediation_action="Add concise descriptive alt text to the image.",
                    remediation_automation="AUTO_PREVIEW",
                    effort_band="XS",
                )
            )
    for input_el in soup.find_all("input"):
        input_type = (input_el.get("type") or "").lower()
        name = " ".join(
            filter(None, [input_el.get("name"), input_el.get("id"), input_el.get("value")])
        ).lower()
        marketing = re.search(r"marketing|subscribe|newsletter|promo", name)
        if input_type in {"checkbox", "radio"} and input_el.has_attr("checked") and marketing:
            findings.append(
                Finding(
                    "consent_prechecked",
                    "Preselected marketing choice",
                    name,
                    "medium",
                    url,
                    check="ux",
                    selector=f"input[name='{input_el.get('name') or input_el.get('id') or '?'}']",
                    evidence_source="dom:checked marketing checkbox/radio",
                    observed=f"pre-checked input: {name or '?'}",
                    business_impact="Users may be opted into marketing unintentionally; trust risk.",
                    remediation_action="Leave marketing choices unchecked by default.",
                    remediation_automation="HUMAN_REVIEW",
                    effort_band="XS",
                )
            )
    links = [
        urljoin(url, a["href"].strip())
        for a in soup.find_all("a", href=True)
        if a["href"].strip() and not a["href"].startswith(("mailto:", "tel:", "#", "javascript:"))
    ]
    evidence = {
        "title": title,
        "word_count": len(words),
        "link_count": len(links),
        "sample_links": links[:25],
        "emails": sorted(set(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", html))),
        "schema_count": len(schema),
    }
    return dedupe_findings(findings), evidence


def classify_response(status_code: int, body: str) -> tuple[str, list[Finding]]:
    text = body.lower()
    findings: list[Finding] = []
    if status_code >= 500:
        findings.append(
            Finding(
                "server_error",
                "Server error response",
                f"HTTP {status_code}",
                "critical",
                check="fetch",
            )
        )
    elif status_code >= 400:
        findings.append(
            Finding(
                "client_error",
                "Client error response",
                f"HTTP {status_code}",
                "high",
                check="fetch",
            )
        )
    elif status_code == 200 and re.search(
        r"<(?:title|h1)[^>]*>\s*(?:404(?: error)?|page not found|not found|page does not exist)\s*(?:[|–—-][^<]*)?</(?:title|h1)>",
        text,
    ):
        findings.append(
            Finding(
                "soft_404", "Possible soft 404", "200 page says not found", "high", check="fetch"
            )
        )
    return "ok" if not findings else "error", findings
