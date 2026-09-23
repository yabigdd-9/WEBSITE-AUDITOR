"""Detect server technologies from headers and other signals."""

from __future__ import annotations

import re

from .checks import Finding


def analyse_html(
    response_text: str, final_url: str, response_headers: dict[str, str]
) -> tuple[list[Finding], dict]:
    """Return findings and evidence for server technology detection."""
    findings: list[Finding] = []
    evidence: dict = {}

    # Server header
    server = response_headers.get("Server", "")
    if server:
        findings.append(
            Finding(
                "server-header",
                f"Server header discloses technology: {server}",
                server,
                {"server": server},
                final_url,
                check="server_technology",
            )
        )

    # X-Powered-By header
    x_powered_by = response_headers.get("X-Powered-By", "")
    if x_powered_by:
        findings.append(
            Finding(
                "x-powered-by-header",
                f"X-Powered-By header discloses technology: {x_powered_by}",
                x_powered_by,
                {"x_powered_by": x_powered_by},
                final_url,
                check="server_technology",
            )
        )

    # Via header (can reveal proxies)
    via = response_headers.get("Via", "")
    if via:
        findings.append(
            Finding(
                "via-header",
                f"Via header reveals proxy: {via}",
                via,
                {"via": via},
                final_url,
                check="server_technology",
            )
        )

    # X-Generator header (CMS)
    x_generator = response_headers.get("X-Generator", "")
    if x_generator:
        findings.append(
            Finding(
                "x-generator-header",
                f"X-Generator header discloses CMS: {x_generator}",
                x_generator,
                {"x_generator": x_generator},
                final_url,
                check="server_technology",
            )
        )

    # Look for common server signatures in headers
    # Examples: Cloudflare, Akamai, etc.
    for header, value in response_headers.items():
        header_lower = header.lower()
        value_lower = value.lower()
        if "cloudflare" in value_lower or "cf-ray" in header_lower:
            findings.append(
                Finding(
                    "cloudflare-header",
                    "Cloudflare detected via headers",
                    value,
                    {"header": header, "value": value},
                    final_url,
                    check="server_technology",
                )
            )
        if "akamai" in value_lower:
            findings.append(
                Finding(
                    "akamai-header",
                    "Akamai detected via headers",
                    value,
                    {"header": header, "value": value},
                    final_url,
                    check="server_technology",
                )
            )

    return findings, evidence