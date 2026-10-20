"""Optional, bounded SPF/DMARC observations; no message or spoofing assessment."""

import ipaddress
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from urllib.parse import urlsplit

CHECKER_VERSION = "6.0.3"
MAX_OUTPUT_BYTES = 1_048_576
MAX_QUERY_CALLS = 64
MAX_SECONDS = 30.0
LIMITATIONS = [
    "DNS record observations only; no SMTP connection, message submission or mailbox verification.",
    "Record validity does not establish message authentication, alignment or spoofing risk.",
    "DMARC policy location and tags are checker observations, not delivery or enforcement evidence.",
    "DKIM needs an explicit selector and is not assessed here.",
    "Missing dependency, lookup failure or exhausted limits mean unknown, not an invalid record.",
]


def normalize_domain(value):
    """Select the exact hostname; never guess the sending or organizational domain."""
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("Expected a bounded domain or HTTP(S) URL")
    if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise ValueError("Whitespace, controls and backslashes are not accepted")
    parsed = urlsplit(value if "://" in value else "https://" + value)
    if parsed.scheme not in {"http", "https"} or parsed.username is not None:
        raise ValueError("Expected HTTP(S) without credentials")
    if parsed.password is not None or not parsed.hostname:
        raise ValueError("A hostname without credentials is required")
    _ = parsed.port  # Validate syntax/range; DNS does not use the URL port.
    hostname = parsed.hostname[:-1] if parsed.hostname.endswith(".") else parsed.hostname
    host = hostname.encode("idna").decode("ascii").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("An email domain, not an IP address, is required")
    if len(host) > 253 or "." not in host or re.fullmatch(r"[0-9.]+", host):
        raise ValueError("Expected a fully qualified domain")
    labels = host.split(".")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels):
        raise ValueError("Invalid DNS label")
    if labels[-1] in {"local", "localhost", "internal", "lan", "home", "arpa", "invalid", "test"}:
        raise ValueError("Local and reserved domains are not accepted")
    return host


def unknown_result(domain, reason):
    return {
        "format_version": 2,
        "status": "unknown",
        "domain": domain,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "checker": {"name": "checkdmarc", "required_version": CHECKER_VERSION},
        "spf": {"status": "unknown", "valid": None, "reason": reason},
        "dmarc": {"status": "unknown", "valid": None, "reason": reason},
        "spoofing_risk": "NOT_ASSESSED",
        "limitations": list(LIMITATIONS),
    }


def inspect_email_auth(value, timeout=20.0):
    """Run selected checker APIs in an owned child, or return explicit unknown."""
    try:
        domain = normalize_domain(value)
    except (ValueError, UnicodeError):
        return unknown_result(None, "invalid_target")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        return unknown_result(domain, "invalid_timeout")
    if not 1 <= timeout <= MAX_SECONDS or not math.isfinite(timeout):
        return unknown_result(domain, "invalid_timeout")
    try:
        installed = metadata.version("checkdmarc")
    except metadata.PackageNotFoundError:
        return unknown_result(domain, "optional_checker_not_installed")
    if installed != CHECKER_VERSION:
        result = unknown_result(domain, "unsupported_checker_version")
        result["checker"]["installed_version"] = installed
        return result
    request = json.dumps({"domain": domain, "timeout": timeout}).encode()
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT")
                   if key in os.environ}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    # File-backed output prevents unbounded pipe buffering; reads are capped.
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
        source.write(request)
        source.seek(0)
        try:
            process = subprocess.Popen(
                [sys.executable, "-B", "-m", "auditor_toolkit.email_auth_worker"],
                cwd=Path(__file__).resolve().parent.parent,
                env=environment, stdin=source, stdout=output, stderr=subprocess.DEVNULL,
            )
        except OSError:
            return unknown_result(domain, "checker_child_unavailable")
        try:
            process.wait(timeout=float(timeout))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return unknown_result(domain, "checker_deadline_exceeded")
        except BaseException:
            if process.poll() is None:
                process.kill()
            process.wait()
            raise
        if process.returncode != 0:
            return unknown_result(domain, "checker_child_failed")
        output.seek(0)
        raw = output.read(MAX_OUTPUT_BYTES + 1)
    if len(raw) > MAX_OUTPUT_BYTES:
        return unknown_result(domain, "checker_output_limit")
    try:
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("format_version") != 2:
            raise ValueError("Invalid schema")
        if result.get("domain") != domain or result.get("checker", {}).get("version") != installed:
            raise ValueError("Invalid provenance")
        for protocol in ("spf", "dmarc"):
            observation = result[protocol]
            status, valid = observation["status"], observation["valid"]
            if status not in {"validated_record", "checker_rejected", "unknown"}:
                raise ValueError("Invalid protocol status")
            expected = {"validated_record": True, "checker_rejected": False, "unknown": None}[status]
            if valid is not expected:
                raise ValueError("Invalid validity state")
        result["status"] = ("unknown" if any(result[x]["valid"] is None for x in ("spf", "dmarc"))
                            else "complete")
        result["spoofing_risk"] = "NOT_ASSESSED"
        result["limitations"] = list(LIMITATIONS)
        return result
    except (KeyError, TypeError, ValueError, AttributeError):
        return unknown_result(domain, "malformed_checker_output")
