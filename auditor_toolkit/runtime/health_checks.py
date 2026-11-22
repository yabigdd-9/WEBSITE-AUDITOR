"""Runtime health checks for auditor_toolkit.

Provides comprehensive health checking for:
- Database connectivity (SQLite)
- External API availability (PageSpeed, RankNibbler, etc.)
- System resources (disk space, memory)
- Overall system health aggregation
"""

from __future__ import annotations

import logging
import shutil
import socket
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Result of a single health check.

    Attributes:
        name: Unique identifier for the check.
        status: Health status (healthy/degraded/unhealthy/unknown).
        message: Human-readable description.
        details: Additional structured data.
        duration_ms: Check execution time in milliseconds.
        timestamp: When the check was performed.
    """

    name: str
    status: HealthStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def _time_check(func):
    """Decorator to time a health check function."""

    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        if isinstance(result, HealthCheck):
            result.duration_ms = elapsed
        return result

    return wrapper


@_time_check
def check_database(db_path: str | Path | None = None) -> HealthCheck:
    """Check database connectivity and basic integrity.

    Args:
        db_path: Path to SQLite database. Defaults to history.sqlite3
            in the standard output directory.

    Returns:
        HealthCheck with status and details.
    """
    if db_path is None:
        db_path = Path("outputs/toolkit/history.sqlite3")

    db_path = Path(db_path)
    try:
        if not db_path.is_file():
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database file not found: {db_path}",
                details={"path": str(db_path), "exists": False},
            )

        with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise sqlite3.DatabaseError("Database integrity check failed")
            conn.execute("SELECT 1 FROM runs LIMIT 1")
            cursor = conn.execute("SELECT COUNT(*) FROM runs")
            run_count = cursor.fetchone()[0]

        return HealthCheck(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database connection and integrity check passed",
            details={"path": str(db_path), "run_count": run_count, "integrity": "ok"},
        )
    except sqlite3.Error as e:
        logger.error("Database health check failed", exc_info=True)
        return HealthCheck(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database error: {e}",
            details={"path": str(db_path), "error": str(e)},
        )
    except Exception as e:
        logger.error("Unexpected error in database check", exc_info=True)
        return HealthCheck(
            name="database",
            status=HealthStatus.UNKNOWN,
            message=f"Unexpected error: {e}",
            details={"error": str(e)},
        )


@_time_check
def check_disk_space(
    path: str | Path = ".", min_free_gb: float = 1.0, min_free_percent: float = 5.0
) -> HealthCheck:
    """Check available disk space.

    Args:
        path: Path to check disk space for.
        min_free_gb: Minimum free space in GB.
        min_free_percent: Minimum free space as percentage.

    Returns:
        HealthCheck with status and details.
    """
    path = Path(path)
    try:
        total, used, free = shutil.disk_usage(path)
        free_gb = free / (1024**3)
        free_percent = (free / total) * 100

        details = {
            "path": str(path),
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free_gb, 2),
            "free_percent": round(free_percent, 2),
            "min_free_gb": min_free_gb,
            "min_free_percent": min_free_percent,
        }

        if free_gb < min_free_gb or free_percent < min_free_percent:
            return HealthCheck(
                name="disk_space",
                status=HealthStatus.UNHEALTHY,
                message=f"Low disk space: {free_gb:.2f} GB free ({free_percent:.1f}%)",
                details=details,
            )

        if free_gb < min_free_gb * 2 or free_percent < min_free_percent * 2:
            return HealthCheck(
                name="disk_space",
                status=HealthStatus.DEGRADED,
                message=f"Disk space warning: {free_gb:.2f} GB free ({free_percent:.1f}%)",
                details=details,
            )

        return HealthCheck(
            name="disk_space",
            status=HealthStatus.HEALTHY,
            message=f"Disk space OK: {free_gb:.2f} GB free ({free_percent:.1f}%)",
            details=details,
        )
    except Exception as e:
        logger.error("Disk space check failed", exc_info=True)
        return HealthCheck(
            name="disk_space",
            status=HealthStatus.UNKNOWN,
            message=f"Disk check error: {e}",
            details={"error": str(e)},
        )


@_time_check
def check_memory(
    max_percent: float = 90.0, warn_percent: float = 75.0
) -> HealthCheck:
    """Check system memory usage.

    Args:
        max_percent: Maximum memory usage percentage before unhealthy.
        warn_percent: Warning threshold percentage.

    Returns:
        HealthCheck with status and details.
    """
    try:
        import psutil

        mem = psutil.virtual_memory()
        used_percent = mem.percent

        details = {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_percent": round(used_percent, 1),
            "max_percent": max_percent,
            "warn_percent": warn_percent,
        }

        if used_percent >= max_percent:
            return HealthCheck(
                name="memory",
                status=HealthStatus.UNHEALTHY,
                message=f"High memory usage: {used_percent:.1f}%",
                details=details,
            )

        if used_percent >= warn_percent:
            return HealthCheck(
                name="memory",
                status=HealthStatus.DEGRADED,
                message=f"Memory usage warning: {used_percent:.1f}%",
                details=details,
            )

        return HealthCheck(
            name="memory",
            status=HealthStatus.HEALTHY,
            message=f"Memory OK: {used_percent:.1f}% used",
            details=details,
        )
    except ImportError:
        return HealthCheck(
            name="memory",
            status=HealthStatus.UNKNOWN,
            message="psutil not installed, cannot check memory",
            details={"psutil_available": False},
        )
    except Exception as e:
        logger.error("Memory check failed", exc_info=True)
        return HealthCheck(
            name="memory",
            status=HealthStatus.UNKNOWN,
            message=f"Memory check error: {e}",
            details={"error": str(e)},
        )


@_time_check
def check_external_apis(
    timeout: float = 5.0,
    check_pagespeed: bool = True,
    check_languagetool: bool = True,
    check_pollinations: bool = True,
) -> HealthCheck:
    """Check external API availability.

    Args:
        timeout: Request timeout in seconds.
        check_pagespeed: Check PageSpeed Insights API.
        check_languagetool: Check LanguageTool API.
        check_pollinations: Check Pollinations image API.

    Returns:
        HealthCheck with aggregated status and per-API details.
    """
    apis = {
        "pagespeed": {
            "url": "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            "enabled": check_pagespeed,
            "params": {"url": "https://example.com", "strategy": "mobile"},
        },
        "languagetool": {
            "url": "https://api.languagetool.org/v2/check",
            "enabled": check_languagetool,
            "data": {"text": "test", "language": "en-US"},
        },
        "pollinations": {
            "url": "https://image.pollinations.ai/prompt/test",
            "enabled": check_pollinations,
        },
    }

    results = {}
    unhealthy_count = 0
    degraded_count = 0

    with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        for name, config in apis.items():
            if not config.get("enabled", True):
                results[name] = {"status": "skipped", "enabled": False}
                continue

            try:
                url = config["url"]
                if name == "languagetool":
                    resp = client.post(url, data=config.get("data", {}))
                elif name == "pagespeed":
                    resp = client.get(url, params=config.get("params", {}))
                else:
                    resp = client.get(url)

                # PageSpeed returns 400 for invalid key but that means API is reachable
                if name == "pagespeed" and resp.status_code in (200, 400, 403):
                    results[name] = {"status": "healthy", "http_code": resp.status_code}
                elif resp.status_code == 200:
                    results[name] = {"status": "healthy", "http_code": resp.status_code}
                elif 400 <= resp.status_code < 500:
                    # Client errors may mean API is up but request invalid
                    results[name] = {"status": "degraded", "http_code": resp.status_code}
                    degraded_count += 1
                else:
                    results[name] = {"status": "unhealthy", "http_code": resp.status_code}
                    unhealthy_count += 1

            except httpx.TimeoutException:
                results[name] = {"status": "unhealthy", "error": "timeout"}
                unhealthy_count += 1
            except httpx.ConnectError as e:
                results[name] = {"status": "unhealthy", "error": f"connection: {e}"}
                unhealthy_count += 1
            except Exception as e:
                results[name] = {"status": "unknown", "error": str(e)}
                unhealthy_count += 1

    # Determine overall status
    if unhealthy_count > 0:
        status = HealthStatus.UNHEALTHY
        message = f"{unhealthy_count} external API(s) unhealthy"
    elif degraded_count > 0:
        status = HealthStatus.DEGRADED
        message = f"{degraded_count} external API(s) degraded"
    else:
        status = HealthStatus.HEALTHY
        message = "All external APIs healthy"

    return HealthCheck(
        name="external_apis",
        status=status,
        message=message,
        details={"apis": results},
    )


@_time_check
def check_network_connectivity(
    hosts: list[str] | None = None, timeout: float = 3.0
) -> HealthCheck:
    """Check basic network connectivity to known hosts.

    Args:
        hosts: List of hostnames to check (defaults to major DNS providers).
        timeout: Connection timeout in seconds.

    Returns:
        HealthCheck with status and details.
    """
    if hosts is None:
        hosts = ["8.8.8.8", "1.1.1.1", "google.com", "github.com"]

    results = {}
    failed = 0

    for host in hosts:
        try:
            socket.create_connection((host, 53), timeout=timeout)
            results[host] = {"status": "healthy"}
        except (socket.timeout, socket.gaierror, ConnectionRefusedError, OSError) as e:
            results[host] = {"status": "unhealthy", "error": str(e)}
            failed += 1
        except Exception as e:
            results[host] = {"status": "unknown", "error": str(e)}
            failed += 1

    if failed == len(hosts):
        status = HealthStatus.UNHEALTHY
        message = "No network connectivity"
    elif failed > 0:
        status = HealthStatus.DEGRADED
        message = f"{failed}/{len(hosts)} hosts unreachable"
    else:
        status = HealthStatus.HEALTHY
        message = "Network connectivity OK"

    return HealthCheck(
        name="network",
        status=status,
        message=message,
        details={"hosts": results},
    )


def run_all_health_checks(
    db_path: str | Path | None = None,
    disk_path: str | Path = ".",
    min_free_gb: float = 1.0,
    check_apis: bool = True,
    api_timeout: float = 5.0,
) -> dict[str, Any]:
    """Run all health checks and return aggregated results.

    Args:
        db_path: Database path for database check.
        disk_path: Path for disk space check.
        min_free_gb: Minimum free disk space in GB.
        check_apis: Whether to check external APIs.
        api_timeout: Timeout for API checks.

    Returns:
        Dictionary with overall status, timestamp, and individual check results.
    """
    checks = []

    # Database check
    checks.append(check_database(db_path))

    # Disk space check
    checks.append(check_disk_space(disk_path, min_free_gb=min_free_gb))

    # Memory check
    checks.append(check_memory())

    # Network connectivity
    checks.append(check_network_connectivity())

    # External APIs (optional)
    if check_apis:
        checks.append(check_external_apis(timeout=api_timeout))

    # Determine overall status
    statuses = [c.status for c in checks]
    if HealthStatus.UNHEALTHY in statuses:
        overall = HealthStatus.UNHEALTHY
    elif HealthStatus.DEGRADED in statuses:
        overall = HealthStatus.DEGRADED
    elif HealthStatus.UNKNOWN in statuses:
        overall = HealthStatus.DEGRADED  # Unknown is treated as degraded
    else:
        overall = HealthStatus.HEALTHY

    return {
        "status": overall.value,
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": [
            {
                "name": c.name,
                "status": c.status.value,
                "message": c.message,
                "details": c.details,
                "duration_ms": round(c.duration_ms, 2),
                "timestamp": c.timestamp,
            }
            for c in checks
        ],
        "summary": {
            "total": len(checks),
            "healthy": sum(1 for c in checks if c.status == HealthStatus.HEALTHY),
            "degraded": sum(1 for c in checks if c.status == HealthStatus.DEGRADED),
            "unhealthy": sum(1 for c in checks if c.status == HealthStatus.UNHEALTHY),
            "unknown": sum(1 for c in checks if c.status == HealthStatus.UNKNOWN),
        },
    }


# CLI entry point
def main() -> int:
    """Run health checks and print results as JSON."""
    import json

    result = run_all_health_checks()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
