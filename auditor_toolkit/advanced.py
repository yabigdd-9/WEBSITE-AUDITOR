"""Canonical orchestration of the four passive advanced checks; no separate engine."""

import argparse
import hashlib
import json
import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from urllib.parse import urlsplit

from . import images, tech, ux_static
from .checks import classify_response
from .common import Fetcher
from .email_auth import inspect_email_auth

CHECK_NAMES = ("technology", "email_security", "ux", "images")


def bounded_timeout(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError("Timeout must be 1–30 seconds") from exc
    if not math.isfinite(number) or not 1 <= number <= 30:
        raise argparse.ArgumentTypeError("Timeout must be 1–30 seconds")
    return number


def display_url(value):
    """Never echo a rejected credential-bearing URL in a failure report."""
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            return None
    except ValueError:
        return None
    return value


def run_advanced_audit(url, *, timeout=8.0, email_domain=None, fetcher=None):
    """Use canonical implementations once each; borrowed fetchers stay caller-owned."""
    timeout = bounded_timeout(timeout)
    report = {
        "format_version": 2, "scope": "four_passive_advanced_checks",
        "url": display_url(url), "status": "incomplete",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "checks": {}, "evidence": {},
        "tech_stack_detected": None, "email_security_dns": None,
        "ux_dark_patterns": None, "image_performance": None,
        "limitations": [
            "Completion describes requested check coverage, not a defect-free website or release.",
            "Passive technology, static UX/image and DNS evidence have their own interpretation limits.",
            "This command is not the full canonical audit, browser, crawl or external-tool workflow.",
        ],
    }
    client = fetcher
    owned = fetcher is None
    try:
        if not isinstance(url, str) or len(url) > 4096:
            raise ValueError("Invalid URL")
        if client is None:
            client = Fetcher(timeout=timeout, max_bytes=2_000_000)
        response = client.get(url)
        html, final_url = response.text, str(response.url)
        if len(response.content) > 2_000_000:
            raise ValueError("Response exceeds capture byte limit")
        response_status, _ = classify_response(response.status_code, html)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if not 200 <= response.status_code < 300 or response_status != "ok":
            raise ValueError("Unusable HTTP response")
        if content_type not in {"text/html", "application/xhtml+xml"} or not html.strip():
            raise ValueError("A nonempty HTML response is required")
        report["checks"]["fetch"] = {"status": "ok", "required": True}
        report["final_url"] = display_url(final_url)
        report["evidence"]["fetch"] = {
            "url": display_url(final_url), "status_code": response.status_code,
            "observed_at": response.extensions.get("observed_at", report["checked_at_utc"]),
            "redirects": response.extensions.get("redirect_chain", []),
            "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
            "body_sha256": hashlib.sha256(response.content).hexdigest(),
            "body_bytes": len(response.content), "content_type": content_type,
        }

        def perform(name, fn):
            started = time.perf_counter()
            try:
                found, data = fn()
                report["evidence"][name] = data
                report["checks"][name] = {"status": "ok", "required": True}
                return found, data
            except Exception as exc:
                report["checks"][name] = {
                    "status": "error", "required": True, "error_type": type(exc).__name__,
                    "reason": "Canonical checker did not produce a usable result",
                }
                return None, None
            finally:
                report["checks"][name]["elapsed_ms"] = int((time.perf_counter() - started) * 1000)

        _, technologies = perform("technology", lambda: tech.analyse_html(html, final_url, response.headers))
        if technologies is not None:
            names = {"Vue": "Vue.js"}
            report["tech_stack_detected"] = sorted(
                {names.get(row["technology"], row["technology"]) for row in technologies["technologies"]},
                key=str.casefold,
            )
        email_target = url if email_domain is None else email_domain
        _, email = perform("email_security", lambda: ([], inspect_email_auth(email_target, timeout)))
        if email is not None:
            if email["status"] != "complete":
                report["checks"]["email_security"].update(
                    status="unknown", reason="SPF/DMARC record validation is incomplete; inspect evidence")
            report["email_security_dns"] = {
                "format_version": 2, "spf_valid": email["spf"]["valid"],
                "dmarc_valid": email["dmarc"]["valid"], "spoofing_risk": "NOT_ASSESSED",
                "status": email["status"], "observation": email,
            }
        ux_findings, ux = perform("ux", lambda: ux_static.analyse_html(html, final_url))
        if ux is not None:
            names = {"consent_prechecked": "Pre-ticked Consent", "confirmshaming_review": "Confirmshaming"}
            report["ux_dark_patterns"] = [
                {"type": names[f.defect_key], "severity": f.severity.title(),
                 "description": f.defect + ": " + f.observed, "finding": asdict(f),
                 "method": "static-ux-choice-evidence-v2", "consent_behaviour_verified": False,
                 "legal_compliance_assessed": False} for f in ux_findings
            ]
        image_findings, image = perform("images", lambda: images.analyse_html(html, final_url, response.headers))
        if image is not None:
            report["image_performance"] = {
                **image, "findings": [asdict(f) for f in image_findings],
                "legacy_compatibility": {
                    "format_version": 2,
                    "retired_fields": ["score", "optimization_score", "missing_lazy_load",
                                       "missing_responsive_srcset", "legacy_formats_count"],
                    "reason": "Old arithmetic did not measure performance or establish defects.",
                },
            }
        report["status"] = ("complete" if all(row["status"] == "ok" for row in report["checks"].values())
                            else "incomplete")
    except Exception as exc:
        # Do not embed exception strings which may expose credentials or arbitrary response text.
        if "fetch" not in report["checks"]:
            report["checks"]["fetch"] = {
                "status": "error", "required": True, "reason": "Public HTML capture failed",
                "error_type": type(exc).__name__,
            }
        else:
            report["checks"]["assembly"] = {
                "status": "error", "required": True, "reason": "Advanced report assembly failed",
                "error_type": type(exc).__name__,
            }
        for name in CHECK_NAMES:
            report["checks"].setdefault(name, {"status": "skipped", "required": True,
                                               "reason": "A preceding required operation failed"})
    finally:
        if owned and client is not None:
            try:
                client.close()
            except Exception as exc:
                report["checks"]["cleanup"] = {
                    "status": "error", "required": True, "reason": "Owned fetcher cleanup failed",
                    "error_type": type(exc).__name__,
                }
                report["status"] = "incomplete"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Canonical passive advanced checks; JSON format 2")
    parser.add_argument("url")
    parser.add_argument("--timeout", type=bounded_timeout, default=8.0)
    parser.add_argument("--email-domain", help="Explicit email domain; defaults to requested URL hostname")
    args = parser.parse_args(argv)
    result = run_advanced_audit(args.url, timeout=args.timeout, email_domain=args.email_domain)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
