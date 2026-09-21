"""Deterministic audit-hygiene checks: robots.txt, sitemap, security headers.

Pure-stdlib + BeautifulSoup. Every check returns (findings, evidence) and
attaches observed evidence, remediation and effort bands (P5), so results feed
straight into the derived scoring pipeline. No browser, no paid services.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from .checks import Finding

# Graded by default: these two overlap inspect_headers() (kept: this grader adds
# P5 evidence/remediation while the legacy check is preserved for compatibility).
# referrer-policy / permissions-policy are graded in deep mode only to avoid
# changing default scores for previously-clean pages.
SECURITY_HEADERS_DEFAULT = (
    "content-security-policy",
    "x-content-type-options",
)
SECURITY_HEADERS_DEEP = (
    "referrer-policy",
    "permissions-policy",
)
SECURITY_HEADERS = SECURITY_HEADERS_DEFAULT + SECURITY_HEADERS_DEEP


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def check_robots(fetcher, url: str) -> tuple[list[Finding], dict]:
    """Fetch /robots.txt; flag absence (crawl-waste risk) with observed evidence."""
    origin = _origin(url)
    target = origin + "/robots.txt"
    try:
        response = fetcher.get(target)
    except Exception as exc:
        return [
            Finding(
                "robots-unreachable",
                "robots.txt unreachable",
                f"Fetch failed: {exc}",
                "low",
                url,
                check="crawl",
                confidence="heuristic",
                evidence_source="fetch:robots.txt error",
                observed=f"GET {target} raised {type(exc).__name__}",
                business_impact="Crawler behaviour unknown; crawl budget may be wasted.",
                remediation_action="Publish a minimal robots.txt (allow / + sitemap line).",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        ], {"url": target, "status": "unreachable", "error": str(exc)}
    evidence: dict = {"url": target, "status_code": response.status_code}
    findings: list[Finding] = []
    if response.status_code in (404, 410):
        findings.append(
            Finding(
                "robots-missing",
                "No robots.txt",
                f"HTTP {response.status_code}",
                "low",
                url,
                check="crawl",
                evidence_source="fetch:robots.txt status",
                observed=f"GET {target} returned HTTP {response.status_code}",
                business_impact="Crawlers guess crawl rules; sitemap undiscoverable via robots.",
                remediation_action="Publish a minimal robots.txt with a sitemap line.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="XS",
            )
        )
    elif response.status_code == 200:
        body = response.text
        evidence["bytes"] = len(body)
        parser = RobotFileParser()
        parser.parse(body.splitlines())
        evidence["sitemaps_declared"] = parser.site_maps() or []
        if "sitemap" not in body.lower():
            findings.append(
                Finding(
                    "robots-no-sitemap",
                    "robots.txt declares no sitemap",
                    "Sitemap undiscoverable",
                    "low",
                    url,
                    check="crawl",
                    evidence_source="parse:robots.txt body",
                    observed="robots.txt has no sitemap directive",
                    business_impact="Search engines may discover new pages more slowly.",
                    remediation_action="Add a Sitemap: line pointing at the sitemap URL.",
                    remediation_automation="AUTO_PREVIEW",
                    effort_band="XS",
                )
            )
    else:
        findings.append(
            Finding(
                "robots-unexpected-status",
                "robots.txt unexpected status",
                f"HTTP {response.status_code}",
                "low",
                url,
                check="crawl",
                confidence="heuristic",
                evidence_source="fetch:robots.txt status",
                observed=f"GET {target} returned HTTP {response.status_code}",
                business_impact="Crawler behaviour unknown.",
                remediation_action="Serve robots.txt with HTTP 200 or 404.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="XS",
            )
        )
    return findings, evidence


def check_sitemap(fetcher, url: str, declared: list[str] | None = None) -> tuple[list, dict]:
    """Validate sitemap URLs (declared in robots or conventional default).

    Deterministic and bounded: at most 2 sitemaps, XML well-formedness + loc
    count only — full URL validation is Lychee's job when installed (P4+).
    """
    import xml.etree.ElementTree as ET

    origin = _origin(url)
    candidates = list(declared or []) or [origin + "/sitemap.xml"]
    findings: list[Finding] = []
    checked = []
    for candidate in candidates[:2]:
        if urlparse(candidate).netloc != urlparse(origin).netloc:
            continue
        try:
            response = fetcher.get(candidate)
        except Exception as exc:
            checked.append({"url": candidate, "status": "unreachable", "error": str(exc)})
            continue
        entry: dict = {"url": candidate, "status": response.status_code}
        if response.status_code == 200:
            try:
                xml = ET.fromstring(response.content)
                locs = [
                    el.text.strip()
                    for el in xml.iter()
                    if el.tag.rsplit("}", 1)[-1] == "loc" and (el.text or "").strip()
                ]
                entry["loc_count"] = len(locs)
                entry["well_formed"] = True
            except ET.ParseError:
                entry["well_formed"] = False
                findings.append(
                    Finding(
                        "sitemap-malformed",
                        "Sitemap XML malformed",
                        candidate,
                        "medium",
                        url,
                        check="crawl",
                        evidence_source="parse:sitemap XML",
                        observed=f"{candidate} is not well-formed XML",
                        business_impact="Search engines may ignore the sitemap entirely.",
                        remediation_action="Regenerate valid sitemap XML (urlset, escaped URLs).",
                        remediation_automation="HUMAN_REVIEW",
                        effort_band="S",
                    )
                )
        elif response.status_code in (404, 410):
            findings.append(
                Finding(
                    "sitemap-missing",
                    "Sitemap not found",
                    f"HTTP {response.status_code}",
                    "low",
                    url,
                    check="crawl",
                    evidence_source="fetch:sitemap status",
                    observed=f"GET {candidate} returned HTTP {response.status_code}",
                    business_impact="New/updated pages rely on link discovery alone.",
                    remediation_action="Publish a sitemap.xml and reference it in robots.txt.",
                    remediation_automation="AUTO_PREVIEW",
                    effort_band="S",
                )
            )
        checked.append(entry)
    return findings, {"checked": checked}


def grade_security_headers(
    headers: dict, url: str, deep: bool = False
) -> tuple[list[Finding], dict]:
    """Grade security headers present on the fetched response.

    Missing HSTS on HTTPS is medium (P10 HUMAN_REVIEW remediation class);
    other missing headers are low. Observed values are recorded as evidence.
    `deep=True` additionally grades referrer-policy/permissions-policy.
    """
    lower = {str(k).lower(): v for k, v in dict(headers).items()}
    wanted = SECURITY_HEADERS if deep else SECURITY_HEADERS_DEFAULT
    expected = sorted(wanted) + ["strict-transport-security"]
    findings: list[Finding] = []
    for header in wanted:
        if not lower.get(header):
            findings.append(
                Finding(
                    f"header-{header}",
                    f"Missing {header}",
                    "Review deployment requirements",
                    "low",
                    url,
                    check="headers",
                    evidence_source="http:response headers",
                    observed=f"response has no {header} header",
                    business_impact="Reduced hardening signal; minor trust/compliance note.",
                    remediation_action=f"Send a {header} header from the web server.",
                    remediation_automation="HUMAN_REVIEW",
                    effort_band="S",
                )
            )
    if url.startswith("https:") and not lower.get("strict-transport-security"):
        findings.append(
            Finding(
                "header-hsts",
                "Missing HSTS",
                "Review HTTPS deployment",
                "medium",
                url,
                check="headers",
                evidence_source="http:response headers",
                observed="https response has no strict-transport-security header",
                business_impact="First-visit HTTPS downgrade attacks remain possible.",
                remediation_action="Add Strict-Transport-Security (long max-age).",
                remediation_automation="HUMAN_REVIEW",
                effort_band="S",
            )
        )
    return findings, {
        "graded": expected,
        "present": sorted(k for k in lower if k in set(expected)),
    }


def detect_conversion_signals(html: str, url: str) -> tuple[list[Finding], dict]:
    """Detect contact/booking/quote-form conversion paths (P4 content signals).

    Presence findings are low severity with observed evidence; absence of any
    contact path is a medium conversion weakness feeding P9 opportunity input.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    import re as _re

    text = soup.get_text(" ").lower()
    signals = {
        "contact_path": bool(
            soup.find("a", href=lambda h: h and ("contact" in h.lower() or "mailto:" in h.lower()))
            or soup.find(string=lambda s: s and "contact us" in s.lower())
            or _re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
        ),
        "phone": bool(soup.find("a", href=lambda h: h and h.lower().startswith("tel:"))),
        "booking": any(w in text for w in ("book online", "book now", "booking", "appointment")),
        "quote_form": any(
            w in text
            for w in ("request a quote", "get a quote", "quote form", "free quote", "enquire")
        ),
        "form_present": bool(soup.find("form")),
    }
    # Presence signals are recorded as evidence only, not as deductions: a page
    # WITH a contact path must not score worse than a page without one. The
    # only signal-derived deduction is no-contact-path (below).
    findings: list[Finding] = []
    # contact_path already includes visible email addresses, so only flag when
    # no phone, contact link/address, or form is observable anywhere.
    if not any([signals["contact_path"], signals["phone"], signals["form_present"]]):
        findings.append(
            Finding(
                "no-contact-path",
                "No contact path found",
                "No phone, contact link or form",
                "medium",
                url,
                check="ux",
                confidence="heuristic",
                evidence_source="dom:conversion signal scan",
                observed="no tel: link, contact link, or form element found",
                business_impact="Visitors cannot easily enquire; direct conversion loss.",
                remediation_action="Add a visible phone number and enquiry form.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="M",
            )
        )
    return findings, {"signals": signals}


def check_mixed_content(html: str, page_url: str) -> tuple[list[Finding], dict]:
    """Flag http:// subresources on an https:// page (deterministic, static)."""
    if not page_url.startswith("https:"):
        return [], {"applicable": False}
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    offenders = []
    for tag, attr in (
        ("img", "src"), ("script", "src"), ("link", "href"),
        ("iframe", "src"), ("video", "src"), ("audio", "src"),
    ):
        for el in soup.find_all(tag, **{attr: True}):
            src = str(el.get(attr) or "")
            if src.startswith("http://"):
                offenders.append(f"{tag}[{attr}={src[:80]}]")
    findings = []
    if offenders:
        findings.append(
            Finding(
                "mixed-content",
                "Mixed content on HTTPS page",
                f"{len(offenders)} http:// subresources",
                "medium",
                page_url,
                check="headers",
                selector=", ".join(offenders[:5]),
                evidence_source="dom:http:// subresource URLs",
                observed=f"{len(offenders)} subresources load over http://",
                business_impact="Browsers block or warn on mixed content; broken media/trust.",
                remediation_action="Serve all subresources over https://.",
                remediation_automation="AUTO_PREVIEW",
                effort_band="S",
            )
        )
    return findings, {"offenders": offenders[:25], "count": len(offenders)}


def discover_internal_links(html: str, page_url: str, limit: int = 50) -> list[str]:
    """Same-origin http(s) links for bounded broken-link validation."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    base = urlparse(page_url).netloc
    out = []
    for a in soup.find_all("a", href=True):
        href = (a["href"] or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        absolute = urljoin(page_url, href).split("#")[0]
        parsed = urlparse(absolute)
        if parsed.scheme in ("http", "https") and parsed.netloc == base:
            out.append(absolute)
    return list(dict.fromkeys(out))[:limit]


def validate_links(fetcher, page_url: str, links: list[str], limit: int = 20) -> tuple[list, dict]:
    """Deterministic broken-link validation (stdlib HEAD→GET fallback).

    Bounded to `limit` same-origin links. Lychee remains the recommended
    external validator when installed; this is the $0 built-in equivalent.
    Returns (findings, evidence) in the standard shape.
    """
    findings: list[Finding] = []
    checked = []
    head = getattr(fetcher, "head", None)
    for link in links[:limit]:
        try:
            if head is not None:
                status = head(link).status_code
                if status in (405, 501):
                    status = fetcher.get(link).status_code
            else:
                status = fetcher.get(link).status_code
        except Exception as exc:
            checked.append({"url": link, "status": "unreachable", "error": str(exc)[:200]})
            continue
        checked.append({"url": link, "status": status})
        if status == 404:
            findings.append(
                Finding(
                    "broken-internal-link",
                    "Broken internal link (404)",
                    link,
                    "medium",
                    page_url,
                    check="crawl",
                    selector=f"a[href='{link[:80]}']",
                    evidence_source="fetch:link HEAD/GET status",
                    observed=f"GET {link[:100]} returned HTTP 404",
                    business_impact="Visitors and crawlers hit dead ends; wasted crawl budget.",
                    remediation_action="Fix or remove the link; add a redirect if the page moved.",
                    remediation_automation="AUTO_PREVIEW",
                    effort_band="XS",
                )
            )
        elif status >= 500:
            findings.append(
                Finding(
                    "server-error-link",
                    "Internal link returns server error",
                    f"{link} -> HTTP {status}",
                    "high",
                    page_url,
                    check="crawl",
                    evidence_source="fetch:link HEAD/GET status",
                    observed=f"GET {link[:100]} returned HTTP {status}",
                    business_impact="Destination page is broken for visitors and crawlers.",
                    remediation_action="Fix the destination page, then re-check the link.",
                    remediation_automation="HUMAN_REVIEW",
                    effort_band="S",
                )
            )
    broken = sum(1 for c in checked if c.get("status") == 404)
    return findings, {"checked": checked, "broken": broken}
