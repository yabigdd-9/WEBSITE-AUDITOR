"""Production preflight — verifies all dependencies before startup."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    message: str = ""


@dataclass
class PreflightResult:
    status: str  # "READY", "DEGRADED", "BLOCKED"
    checks: list[PreflightCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [{"name": c.name, "passed": c.passed, "message": c.message} for c in self.checks],
            "errors": self.errors,
            "all_passed": self.all_passed,
        }


def _check(name: str, condition: bool, message: str = "") -> PreflightCheck:
    return PreflightCheck(name=name, passed=condition, message=message)


def _check_dir_writable(path: Path) -> PreflightCheck:
    path.mkdir(parents=True, exist_ok=True)
    ok = os.access(path, os.W_OK)
    return _check(f"dir_writable:{path}", ok, "" if ok else f"{path} not writable")


def _check_binary(name: str) -> PreflightCheck:
    found = shutil.which(name) is not None
    return _check(f"binary:{name}", found, "" if found else f"{name} not found")


def _check_db_reachable(db_path: Path) -> PreflightCheck:
    import sqlite3
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.execute("SELECT 1")
        conn.close()
        return _check("database:reachable", True)
    except Exception as e:
        return _check("database:reachable", False, str(e))


def _check_python_deps() -> PreflightCheck:
    missing = []
    for mod in ["httpx", "beautifulsoup4", "trafilatura", "playwright", "phonenumbers", "rapidfuzz", "extruct"]:
        pkg = mod.replace("-", "_")
        try:
            __import__(pkg)
        except ImportError:
            missing.append(mod)
    ok = len(missing) == 0
    return _check("python:deps", ok, f"missing: {', '.join(missing)}" if missing else "")


def _check_disk_space(min_mb: int = 500) -> PreflightCheck:
    import shutil
    _, _, free = shutil.disk_usage(ROOT)
    free_mb = free // (1024 * 1024)
    ok = free_mb >= min_mb
    return _check(f"disk:space>={min_mb}MB", ok, f"{free_mb}MB free" if ok else f"only {free_mb}MB free")


def _check_no_duplicate_supervisor() -> PreflightCheck:
    import subprocess
    try:
        result = subprocess.run(["pgrep", "-f", "auditor_toolkit.supervisor"], capture_output=True, text=True)
        pids = [p for p in result.stdout.strip().split() if p]
        ok = len(pids) <= 1
        return _check("supervisor:no_duplicate", ok, f"{len(pids)} running" if ok else f"{len(pids)} supervisors running")
    except FileNotFoundError:
        return _check("supervisor:no_duplicate", True, "pgrep unavailable")


def run_preflight(
    db_path: Path | None = None,
    min_disk_mb: int = 500,
    required_dirs: list[Path] | None = None,
) -> PreflightResult:
    """Run all preflight checks. Returns BLOCKED if any critical check fails."""
    checks: list[PreflightCheck] = []
    errors: list[str] = []

    # Critical checks
    checks.append(_check_python_deps())
    if not checks[-1].passed:
        errors.append(checks[-1].message)

    if db_path:
        checks.append(_check_db_reachable(db_path))
        if not checks[-1].passed:
            errors.append(checks[-1].message)

    checks.append(_check_disk_space(min_disk_mb))
    if not checks[-1].passed:
        errors.append(checks[-1].message)

    # Directory checks
    dirs = required_dirs or [ROOT / "var" / "runtime", ROOT / "reports"]
    for d in dirs:
        checks.append(_check_dir_writable(d))

    # Optional checks
    checks.append(_check_no_duplicate_supervisor())
    checks.append(_check_binary("python3"))

    # Browser check (optional)
    try:
        __import__("playwright")
        checks.append(_check("browser:playwright", True))
    except ImportError:
        checks.append(_check("browser:playwright", False, "playwright not installed"))

    has_browser = any(c.name == "browser:playwright" and c.passed for c in checks)
    if not has_browser:
        errors.append("Chrome/Playwright not available — browser checks disabled")

    # Determine status
    critical_failed = any(not c.passed and "python" in c.name or "database" in c.name or "disk" in c.name for c in checks)
    if critical_failed:
        status = "BLOCKED"
    elif any(not c.passed for c in checks):
        status = "DEGRADED"
    else:
        status = "READY"

    return PreflightResult(status=status, checks=checks, errors=errors)
