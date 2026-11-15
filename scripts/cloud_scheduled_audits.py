#!/usr/bin/env python3
"""Bounded, zero-paid-token canonical website audits for GitHub Actions.

No client database, supervisor, outreach transport, AI provider, browser, webhook,
or paid services. Reads only the explicitly tracked public website list.
Raw audit findings are not committed or uploaded from the public repository.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
MAX_SITES = 10


def load_sites(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        raise ValueError(f"Allowlist file is missing: {path}")
    urls = []
    hosts = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        url = raw.strip()
        if not url or url.startswith("#"):
            continue
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        if (parts.scheme != "https" or not host or not HOST.fullmatch(host)
                or "." not in host or parts.port is not None
                or parts.username or parts.password
                or parts.path not in ("", "/") or parts.query or parts.fragment
                or host.endswith((".local", ".internal", ".localhost"))
                or host.startswith(("localhost.", "127."))
                or all(ch.isdigit() or ch == "." for ch in host)):
            raise ValueError(f"Invalid HTTPS domain on line {number}; root domains only")
        if host in hosts:
            raise ValueError(f"Duplicate domain on line {number}: {host}")
        hosts.add(host)
        urls.append((host, url))
        if len(urls) > MAX_SITES:
            raise ValueError(f"Maximum {MAX_SITES} approved domains per scheduled run")
    if not urls:
        raise ValueError("No approved domains in allowlist")
    return urls


def summarize(results: list[tuple[str, str]], path: Path | None) -> None:
    lines = [
        "## Bounded canonical website audits",
        "",
        "Run type: independent GitHub Actions job (NOT the 24/7 supervisor).",
        "No paid models, browser rendering, outreach, or persistent MoneyMachine database.",
        "",
        "| Domain | Result |",
        "| --- | --- |",
    ]
    for host, status in results:
        lines.append(f"| `{host}` | {status} |")
    summary = "\n".join(lines) + "\n"
    if path:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(summary)
    print(summary)


def _safe_fetch_value_error(reason: object) -> str | None:
    """Classify known fetch failures without exposing site content or URLs."""
    if not isinstance(reason, str):
        return None
    exact = {
        "Response exceeded configured byte/time limit": "response_limit",
        "Too many redirects": "redirect_limit",
        "Redirect missing location": "redirect_missing_location",
        "URL resolves to a non-global address": "blocked_dns",
        "Private and non-global URLs are disabled": "blocked_address",
        "Control characters are not allowed in URLs": "invalid_url",
        "Only absolute HTTP(S) URLs without credentials are supported": "invalid_url",
    }
    if reason in exact:
        return exact[reason]
    if reason.startswith("Could not resolve host: "):
        return "dns_unresolved"
    if re.fullmatch(r"HTTP [45][0-9]{2}", reason):
        return "http_status"
    return None



def _audit_status(completed: subprocess.CompletedProcess, output_root: Path) -> str:
    """Expose only names of incomplete required checks, never raw site evidence.

    A canonical audit returns exit code 2 when required checks are incomplete.
    The full report stays in a temporary directory; Actions gets only a bounded
    status summary. Reject paths that escape that temporary directory.
    """
    if completed.returncode == 0:
        return "PASS"
    fallback = f"FAIL (exit {completed.returncode})"
    if completed.returncode != 2:
        return fallback
    try:
        records = json.loads(completed.stdout)
        if not isinstance(records, list) or len(records) != 1:
            return fallback
        record = records[0]
        if not isinstance(record, dict) or record.get("status") != "partial":
            return fallback
        artifact = record.get("artifacts", {}).get("json")
        if not isinstance(artifact, str):
            return fallback
        report_path = Path(artifact).resolve()
        if not report_path.is_relative_to(output_root.resolve()):
            return fallback
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") != "partial":
            return fallback
        checks = report.get("checks", {})
        if not isinstance(checks, dict):
            return fallback
        incomplete = sorted(
            name for name, check in checks.items()
            if isinstance(name, str)
            and re.fullmatch(r"[a-z][a-z0-9_]{0,48}", name)
            and isinstance(check, dict)
            and check.get("required") is True
            and check.get("status") != "ok"
        )
        if not incomplete:
            return fallback
        fetch_detail = checks.get("fetch", {})
        fetch_type = (fetch_detail.get("error_type")
                      if isinstance(fetch_detail, dict) else None)
        if not (isinstance(fetch_type, str) and
                re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,40}", fetch_type)):
            fetch_type = None
        fetch_code = (
            _safe_fetch_value_error(fetch_detail.get("reason"))
            if fetch_type == "ValueError" else None
        )
        labels = [
            ("fetch/ValueError/" + fetch_code if fetch_code else f"fetch/{fetch_type}")
            if name == "fetch" and fetch_type else name
            for name in incomplete[:4]
        ]
        label = ", ".join(labels)
        if len(incomplete) > 4:
            label += f" (+{len(incomplete) - 4} more)"
        return f"FAIL (partial: {label})"
    except (OSError, ValueError, TypeError, AttributeError):
        return fallback


def run(sites: list[tuple[str, str]], *, executable: str = "wa",
        timeout_seconds: int = 150, runner=subprocess.run,
        output_root: Path) -> int:
    results: list[tuple[str, str]] = []
    for host, url in sites:
        command = [
            executable, "audit", url, "--profile", "nz",
            "--max-pages", "2", "--max-depth", "1",
            "--concurrency", "1", "--output-root", str(output_root),
        ]
        print(f"Running bounded canonical audit: {host}", flush=True)
        try:
            completed = runner(
                command, check=False, capture_output=True,
                text=True, timeout=timeout_seconds,
            )
            status = _audit_status(completed, output_root)
        except subprocess.TimeoutExpired:
            status = "FAIL (timeout)"
        except OSError as exc:
            status = f"FAIL ({type(exc).__name__})"
        results.append((host, status))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    summarize(results, Path(summary_path) if summary_path else None)
    return 1 if any(status != "PASS" for _, status in results) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowlist", type=Path, default=Path("clients.txt"))
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate target domains without making network requests")
    args = parser.parse_args(argv)
    try:
        sites = load_sites(args.allowlist)
    except (OSError, ValueError) as exc:
        print(f"Scheduled audit blocked: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        summarize([(host, "allowlisted (not scanned)") for host, _ in sites], None)
        return 0
    # Per-run report artifacts never go to Git history, Actions artifacts or
    # stdout. They are removed as soon as the bounded run finishes.
    with tempfile.TemporaryDirectory(prefix="wa-cloud-audits-") as temporary:
        return run(sites, output_root=Path(temporary))


if __name__ == "__main__":
    raise SystemExit(main())
