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
        findings.append(Finding("missing_title", "Missing page title", "Search snippet risk", "high", url))
    if not meta_description or not (meta_description.get("content") or "").strip():
        findings.append(Finding("missing_meta_description", "Missing meta description", "Lower CTR", "medium", url))
    if not canonical or not canonical.get("href"):
        findings.append(Finding("missing_canonical_url", "Missing canonical URL", "Duplicate content risk", "medium", url))
    if not og_tags:
        findings.append(Finding("missing_open_graph_tags", "Missing Open Graph tags", "Poor social preview", "medium", url))
    if len(words) < 200:
        findings.append(Finding("thin_content_200_words", "Thin content (<200 words)", "Review page purpose", "medium", url))
    if not viewport:
        findings.append(Finding("viewport", "Missing viewport metadata", "Mobile layout review", "medium", url))
    if not schema:
        findings.append(Finding("schema_missing", "No structured data found", "Eligibility not guaranteed", "low", url, check="schema"))
    for index, image in enumerate(soup.find_all("img"), 1):
        if image.get("alt") is None:
            findings.append(Finding("image-alt", "Image missing alt attribute", image.get("src") or "image", "high", url, check="accessibility_static", selector=f"img:nth-of-type({index})"))
    for input_el in soup.find_all("input"):
        input_type = (input_el.get("type") or "").lower()
        name = " ".join(filter(None, [input_el.get("name"), input_el.get("id"), input_el.get("value")])).lower()
        marketing = re.search(r"marketing|subscribe|newsletter|promo", name)
        if input_type in {"checkbox", "radio"} and input_el.has_attr("checked") and marketing:
            findings.append(Finding("consent_prechecked", "Preselected marketing choice", name, "medium", url, check="ux"))
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
        findings.append(Finding("server_error", "Server error response", f"HTTP {status_code}", "critical", check="fetch"))
    elif status_code >= 400:
        findings.append(Finding("client_error", "Client error response", f"HTTP {status_code}", "high", check="fetch"))
    elif status_code == 200 and re.search(r"<(?:title|h1)[^>]*>\s*(?:404(?: error)?|page not found|not found|page does not exist)\s*(?:[|–—-][^<]*)?</(?:title|h1)>", text):
        findings.append(Finding("soft_404", "Possible soft 404", "200 page says not found", "high", check="fetch"))
    return "ok" if not findings else "error", findings

