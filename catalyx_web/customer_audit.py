"""Fixed, one-page customer audit profile for an isolated future worker.

This function is deliberately not called by the web application. The queue
worker remains disabled until it runs in a restricted process/container and
the release gates in the implementation plan are satisfied.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import httpx

from auditor_toolkit.checks import analyse_html, classify_response, dedupe_findings
from auditor_toolkit.hygiene import check_mixed_content, grade_security_headers
from auditor_toolkit.network import inspect_headers, inspect_schema

from .egress import (
    EgressCancelledError,
    EgressPolicyError,
    EgressTransportError,
    PinnedEgressTransport,
)
from .security import normalize_site

PROFILE = "customer_static_single_page_v1"
SCANNER_AGENT = "CatalyxLabs-Website-Auditor/1"
MAX_REDIRECTS_PER_FETCH = 3
MAX_TOTAL_REQUESTS = 8
MAX_RESPONSE_BYTES = 2_000_000
MAX_ROBOTS_RULES = 2_048
MAX_ROBOTS_RULE_BYTES = 2_048
MAX_ROBOTS_MATCH_STEPS = 1_000_000
MAX_TOTAL_SECONDS = 35
IMPACT_TEXT = {
    "missing_title": "Search previews may have less useful page information.",
    "missing_meta_description": "Search previews may fall back to other page text.",
    "missing_canonical_url": "Search systems may select a different preferred page URL.",
    "missing_open_graph_tags": "Shared links may show less context in previews.",
    "thin_content_200_words": "Visitors and search systems may have less text to interpret.",
    "viewport": "Some mobile browsers may show the page at an awkward scale.",
    "schema_missing": "Structured data does not provide this signal; eligibility is not assessed.",
    "image-alt": "Screen reader users may miss the purpose of an image.",
    "mixed-content": "Browsers may block or warn about some page resources.",
    "server_error": "The site returned a server error for this request.",
}
SEVERITY_GUIDANCE = {
    "low": "A smaller signal to review when convenient.",
    "medium": "Could affect clarity, usability, or site behavior; confirm before changing anything.",
    "high": "May have a material effect; verify the evidence and prioritize if valid.",
    "critical": "May indicate a severe issue; have a person confirm it promptly.",
}
CHECKS_NOT_RUN = {
    "deep_crawl": "The customer profile checks one page only.",
    "browser": "Rendered browser checks are disabled.",
    "accessibility_rendered": "Rendered accessibility checks are disabled.",
    "tls_certificate": "Certificate detail checks are disabled in this profile.",
    "external_tools": "External local tools are disabled.",
    "third_party_resources": "The profile does not fetch third-party resources.",
}


class _RobotsDisallowedError(Exception):
    def __init__(self, result: str):
        self.result = result


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _finding_records(findings) -> list[dict]:
    records = []
    for index, finding in enumerate(dedupe_findings(findings)):
        key = str(finding.defect_key)[:100]
        check = str(finding.check)[:50]
        identity = hashlib.sha256(f"{check}|{key}|{index}".encode()).hexdigest()[:24]
        severity = finding.severity if finding.severity in {"low", "medium", "high", "critical"} else "medium"
        records.append(
            {
                "id": identity,
                "check": check,
                "title": str(finding.defect)[:180],
                "severity": severity,
                "severity_rationale": SEVERITY_GUIDANCE[severity],
                "impact": IMPACT_TEXT.get(key, "Review the linked check evidence to understand the possible effect."),
                "confidence": finding.confidence if finding.confidence in {"observed", "inferred", "heuristic"} else "unknown",
                "evidence_ref": f"checks.{check}",
                "recommendation": str(finding.remediation_action or "Review this item with a website specialist.")[:240],
            }
        )
    return records


def _safe_jsonld_types(values) -> list[str]:
    safe = set()
    for value in values:
        item = str(value)
        if len(item) <= 80 and re.fullmatch(r"[A-Za-z][A-Za-z0-9_:./-]*", item):
            safe.add(item)
    return sorted(safe)[:25]


def _robots_path(value: str, *, pattern: bool = False) -> str:
    # Keep URI delimiters plus REP's unescaped '*' operator in rule patterns.
    # Other reserved characters are encoded on both sides before comparison.
    encoded = quote(value, safe="/%?*" if pattern else "/%?")

    def normalize_escape(match: re.Match[str]) -> str:
        octet = int(match.group(1), 16)
        character = chr(octet)
        if character.isascii() and (character.isalnum() or character in "-._~"):
            return character
        return f"%{octet:02X}"

    return re.sub(r"%([0-9A-Fa-f]{2})", normalize_escape, encoded)


def _robots_pattern_matches(
    pattern: str,
    target: str,
    anchored: bool,
    *,
    step_budget: list[int] | None = None,
) -> bool | None:
    """Match robots '*' patterns without feeding site text to a backtracking regex."""
    pattern_index = target_index = 0
    last_star = -1
    star_target_index = 0
    while target_index < len(target):
        if step_budget is not None:
            if step_budget[0] <= 0:
                return None
            step_budget[0] -= 1
        if pattern_index == len(pattern) and not anchored:
            return True
        if pattern_index < len(pattern) and pattern[pattern_index] == target[target_index]:
            pattern_index += 1
            target_index += 1
        elif pattern_index < len(pattern) and pattern[pattern_index] == "*":
            last_star = pattern_index
            pattern_index += 1
            star_target_index = target_index
        elif last_star >= 0:
            star_target_index += 1
            target_index = star_target_index
            pattern_index = last_star + 1
        else:
            return False
    while pattern_index < len(pattern) and pattern[pattern_index] == "*":
        if step_budget is not None:
            if step_budget[0] <= 0:
                return None
            step_budget[0] -= 1
        pattern_index += 1
    return pattern_index == len(pattern) and (not anchored or target_index == len(target))


def _robots_can_fetch(text: str, target: str, user_agent: str = SCANNER_AGENT) -> bool:
    """Apply RFC 9309 group selection and most-specific path rule semantics."""
    if len(text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        return False
    groups: list[tuple[list[str], list[tuple[str, bool]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, bool]] = []
    has_rules = False
    parsed_rule_count = 0

    def finish_group() -> None:
        if agents:
            groups.append((agents.copy(), rules.copy()))

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = line.split(":", 1)
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if has_rules:
                finish_group()
                agents, rules, has_rules = [], [], False
            if value:
                agents.append(value.lower())
        elif field in {"allow", "disallow"} and agents:
            has_rules = True
            if value:
                parsed_rule_count += 1
                if (
                    len(value.encode("utf-8")) > MAX_ROBOTS_RULE_BYTES
                    or parsed_rule_count > MAX_ROBOTS_RULES
                ):
                    return False
                rules.append((value, field == "allow"))
    finish_group()

    identity = user_agent.lower()
    matched_groups = [
        group for group in groups
        if any(agent_identifier != "*" and agent_identifier in identity for agent_identifier in group[0])
    ]
    if matched_groups:
        selected = matched_groups
    else:
        selected = [group for group in groups if "*" in group[0]]
    selected_rules = [rule for _group_agents, group_rules in selected for rule in group_rules]
    if not selected_rules:
        return True

    parts = urlsplit(target)
    target_path = _robots_path(parts.path or "/")
    if parts.query:
        target_path += "?" + _robots_path(parts.query)
    matches: list[tuple[int, bool]] = []
    match_budget = [MAX_ROBOTS_MATCH_STEPS]
    for pattern, allowance in selected_rules:
        if not pattern:
            continue
        anchored = pattern.endswith("$")
        if anchored:
            pattern = pattern[:-1]
        pattern = _robots_path(pattern, pattern=True)
        matched = _robots_pattern_matches(
            pattern, target_path, anchored, step_budget=match_budget
        )
        if matched is None:
            # Treat exhausted matching work as disallow so an attacker cannot
            # turn an incomplete rules evaluation into permission to fetch.
            return False
        if matched:
            specificity = len(pattern.replace("*", "").encode("ascii"))
            matches.append((specificity, allowance))
    if not matches:
        return True
    longest = max(length for length, _allowance in matches)
    return any(allowance for length, allowance in matches if length == longest)


def run_authorized_static_audit(
    site_origin: str,
    *,
    transport=None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict:
    """Run the fixed single-page profile after an operator-approved request.

    The caller must confirm a matching authorization receipt and must run this
    in a separate worker with OS-level network and filesystem restrictions.
    """
    normalized, input_host = normalize_site(site_origin)
    if normalized != site_origin:
        raise ValueError("The worker accepts only a normalized site origin")
    if input_host.startswith("www."):
        aliases = {input_host, input_host[4:]}
    else:
        aliases = {input_host, "www." + input_host}

    started = time.monotonic()
    started_at = _timestamp()
    request_budget = {"count": 0}
    robots_cache: dict[str, tuple[str | None, str]] = {}
    findings = []
    checks = {
        name: {"status": "not_run", "reason": reason}
        for name, reason in CHECKS_NOT_RUN.items()
    }
    owned_transport = transport or PinnedEgressTransport(
        max_bytes=MAX_RESPONSE_BYTES,
        timeout=8.0,
        cancel_check=cancel_check,
        deadline=started + MAX_TOTAL_SECONDS,
    )

    def check_cancelled() -> None:
        if cancel_check is not None and cancel_check():
            raise EgressCancelledError("The audit is no longer active")

    def get_bounded(client: httpx.Client, target: str, *, robots_fetch: bool = False) -> httpx.Response:
        current = target
        for _ in range(MAX_REDIRECTS_PER_FETCH + 1):
            check_cancelled()
            if time.monotonic() - started > MAX_TOTAL_SECONDS:
                raise EgressPolicyError("Audit exceeded the overall time limit")
            if not robots_fetch:
                allowed, result = robots_allows(client, current)
                if not allowed:
                    raise _RobotsDisallowedError(result)
            request_budget["count"] += 1
            if request_budget["count"] > MAX_TOTAL_REQUESTS:
                raise EgressPolicyError("Audit exceeded the request limit")
            response = client.get(current)
            try:
                check_cancelled()
            except EgressCancelledError:
                response.close()
                raise
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location", "")
            response.close()
            if not location or len(location) > 2048:
                raise EgressPolicyError("Redirect target is unavailable")
            parts = urlsplit(urljoin(current, location))
            try:
                target_origin, target_host = normalize_site(urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "")))
            except ValueError:
                raise EgressPolicyError("Redirect target is not allowed") from None
            if target_host not in aliases or (urlsplit(current).scheme == "https" and parts.scheme != "https"):
                raise EgressPolicyError("Redirect target is outside the approved site")
            current = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
        raise EgressPolicyError("Redirect limit reached")

    def robots_allows(client: httpx.Client, target: str) -> tuple[bool, str]:
        parts = urlsplit(target)
        origin, _host = normalize_site(urlunsplit((parts.scheme, parts.netloc, "", "", "")))
        if origin not in robots_cache:
            response = get_bounded(client, origin + "/robots.txt", robots_fetch=True)
            try:
                if response.status_code in {404, 410}:
                    robots_cache[origin] = (None, "not_found")
                elif response.status_code == 200:
                    robots_cache[origin] = (response.text, "available")
                else:
                    robots_cache[origin] = (None, "unavailable")
            finally:
                response.close()
        text, result = robots_cache[origin]
        if text is None:
            return result == "not_found", result
        allowed = _robots_can_fetch(text, target)
        return allowed, "allowed" if allowed else "disallowed"

    def blocked_report() -> dict:
        return {
            "schema_version": 1,
            "profile": PROFILE,
            "status": "blocked",
            "site_host": input_host,
            "started_at": started_at,
            "completed_at": _timestamp(),
            "checks": checks,
            "findings": [],
            "limitations": list(CHECKS_NOT_RUN),
        }

    try:
        client = httpx.Client(
            transport=owned_transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(8.0),
            headers={"user-agent": SCANNER_AGENT, "accept-encoding": "identity"},
        )
        try:
            robots_allowed, robots_status = robots_allows(client, normalized + "/")
            checks["robots"] = {"status": "allowed" if robots_allowed else "blocked", "result": robots_status}
            if not robots_allowed:
                return blocked_report()

            response = get_bounded(client, normalized + "/")
            status_code = response.status_code
            final_parts = urlsplit(str(response.url))
            final_host = final_parts.hostname or input_host
            _fetch_classification, fetch_findings = classify_response(status_code, response.text)
            findings.extend(fetch_findings)
            if not 200 <= status_code < 300:
                checks["fetch"] = {"status": "error", "http_status": status_code}
                return {
                    "schema_version": 1,
                    "profile": PROFILE,
                    "status": "partial",
                    "site_host": final_host,
                    "started_at": started_at,
                    "completed_at": _timestamp(),
                    "checks": checks,
                    "findings": _finding_records(findings),
                    "limitations": list(CHECKS_NOT_RUN),
                }
            checks["fetch"] = {"status": "complete", "http_status": status_code}
            html = response.text
            page_findings, page_observation = analyse_html(html, str(response.url))
            schema_findings, schema_observation = inspect_schema(html, str(response.url), "static")
            header_findings, _header_observation = inspect_headers(response)
            security_findings, security_observation = grade_security_headers(response.headers, str(response.url), deep=False)
            mixed_findings, mixed_observation = check_mixed_content(html, str(response.url))
            findings.extend(page_findings + schema_findings + header_findings + security_findings + mixed_findings)
            checks["page"] = {
                "status": "complete",
                "evidence": {
                    "word_count": min(int(page_observation.get("word_count", 0)), 100_000),
                    "link_count": min(int(page_observation.get("link_count", 0)), 10_000),
                    "image_count": min(html.lower().count("<img"), 10_000),
                },
            }
            checks["structured_data"] = {
                "status": "complete",
                "types": _safe_jsonld_types(schema_observation.get("types", [])),
                "block_count": min(html.lower().count("application/ld+json"), 100),
                "limitation": "Presence does not establish identity or search-result eligibility.",
            }
            expected_headers = set(security_observation.get("graded", []))
            header_names = {
                "content-security-policy",
                "x-content-type-options",
                "strict-transport-security",
            }
            lower_headers = {str(key).lower() for key in response.headers.keys()}
            checks["response_headers"] = {
                "status": "complete",
                "checked": sorted(header_names),
                "missing": sorted(header_names - lower_headers),
                "profile_header_count": len(expected_headers),
            }
            checks["mixed_content"] = {
                "status": "complete",
                "finding_count": min(int(mixed_observation.get("count", 0)), 10_000),
                "applicable": bool(mixed_observation.get("applicable", False)),
            }
            report = {
                "schema_version": 1,
                "profile": PROFILE,
                "status": "complete",
                "site_host": final_host,
                "started_at": started_at,
                "completed_at": _timestamp(),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "checks": checks,
                "findings": _finding_records(findings),
                "limitations": list(CHECKS_NOT_RUN),
            }
            return report
        finally:
            client.close()
    except _RobotsDisallowedError as exc:
        checks["robots"] = {"status": "blocked", "result": exc.result}
        return blocked_report()
    except EgressCancelledError:
        raise
    except EgressPolicyError:
        checks["fetch"] = {"status": "error", "reason": "The target did not meet the outbound request policy."}
    except EgressTransportError:
        checks["fetch"] = {"status": "error", "reason": "The target could not be fetched within the configured limits."}
    except (httpx.HTTPError, ValueError, OSError):
        checks["fetch"] = {"status": "error", "reason": "The target could not be fetched within the configured limits."}
    finally:
        if transport is None:
            owned_transport.close()
    return {
        "schema_version": 1,
        "profile": PROFILE,
        "status": "failed",
        "site_host": input_host,
        "started_at": started_at,
        "completed_at": _timestamp(),
        "checks": checks,
        "findings": [],
        "limitations": list(CHECKS_NOT_RUN),
    }
