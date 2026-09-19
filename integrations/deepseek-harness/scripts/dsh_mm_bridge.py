#!/usr/bin/env python3
"""Restricted DeepSeek Harness -> WEBSITE-AUDITOR bridge.

Only explicitly allowlisted operations are exposed. No arbitrary shell is accepted.
No send, approval, payment, deployment, or production mutation command exists here.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

DEFAULT_TIMEOUT = 180
BOUNDED_WRITE_ENV = "DSH_MM_ALLOW_BOUNDED_WRITES"


def _find_repo_root() -> Path:
    override = os.environ.get("WEBSITE_AUDITOR_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "website_auditor.py").is_file() and (candidate / "money-machine" / "mm").is_file():
            return candidate
    raise RuntimeError("cannot locate WEBSITE-AUDITOR root; set WEBSITE_AUDITOR_ROOT")


REPO_ROOT = _find_repo_root()
MM = REPO_ROOT / "money-machine" / "mm"
AUDITOR = REPO_ROOT / "website_auditor.py"

READ_ONLY_MM = {
    "runtime": ["--runtime"],
    "polish-status": ["polish-status"],
    "doctor": ["doctor"],
    "status": ["status"],
}


def _repo_path(value: str) -> Path:
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    p = p.resolve()
    try:
        p.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("path must stay inside WEBSITE-AUDITOR") from exc
    return p


def _public_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must be an absolute http(s) URL")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "::1"} or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("local/private targets are not allowed by the Harness bridge")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast):
        raise ValueError("local/private targets are not allowed by the Harness bridge")
    return value


def _bounded_writes_enabled() -> bool:
    return os.environ.get(BOUNDED_WRITE_ENV, "").strip() == "1"


def build_command(args: argparse.Namespace) -> tuple[list[str], dict[str, str]]:
    env = os.environ.copy()
    env.pop("PYTHONSTARTUP", None)
    env.pop("BASH_ENV", None)

    if args.action in READ_ONLY_MM:
        return [str(MM), *READ_ONLY_MM[args.action]], env

    if args.action == "email-status":
        return [str(MM), "email-status", str(args.business_id), "--json"], env

    if args.action == "outreach-plan":
        brief = _repo_path(args.brief)
        if not brief.is_file():
            raise ValueError("brief file does not exist")
        return [str(MM), "outreach-plan", "--brief", str(brief)], env

    if args.action == "audit-site":
        url = _public_http_url(args.url)
        output = _repo_path(args.output) if args.output else None
        cmd = [sys.executable, str(AUDITOR), url, "--format", "json"]
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            cmd.extend(["--output", str(output)])
        return cmd, env

    if args.action == "email-find":
        if not _bounded_writes_enabled():
            raise PermissionError(
                f"email-find is disabled; set {BOUNDED_WRITE_ENV}=1 only for supervised runs"
            )
        return [str(MM), "email-find", str(args.business_id), "--json"], env

    if args.action == "demo-qa":
        if not _bounded_writes_enabled():
            raise PermissionError(
                f"demo-qa is disabled; set {BOUNDED_WRITE_ENV}=1 only for supervised runs"
            )
        demo = _repo_path(args.path)
        if not demo.is_file():
            raise ValueError("demo file does not exist")
        return [str(MM), "demo-qa", str(args.business_id), "--path", str(demo)], env

    raise ValueError(f"unsupported action: {args.action}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)

    for name in READ_ONLY_MM:
        sub.add_parser(name)

    q = sub.add_parser("email-status")
    q.add_argument("--business-id", type=int, required=True)

    q = sub.add_parser("outreach-plan")
    q.add_argument("--brief", required=True)

    q = sub.add_parser("audit-site")
    q.add_argument("--url", required=True)
    q.add_argument("--output")

    q = sub.add_parser("email-find")
    q.add_argument("--business-id", type=int, required=True)

    q = sub.add_parser("demo-qa")
    q.add_argument("--business-id", type=int, required=True)
    q.add_argument("--path", required=True)

    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        cmd, env = build_command(args)
        timeout = int(os.environ.get("DSH_MM_TIMEOUT", DEFAULT_TIMEOUT))
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=max(5, min(timeout, 600)),
            shell=False,
        )
        envelope = {
            "bridge": "deepseek-harness/mm-v1",
            "action": args.action,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "bounded_writes_enabled": _bounded_writes_enabled(),
        }
        print(json.dumps(envelope, ensure_ascii=False))
        return proc.returncode
    except (ValueError, PermissionError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({
            "bridge": "deepseek-harness/mm-v1",
            "action": getattr(args, "action", None),
            "blocked": True,
            "error": str(exc),
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
