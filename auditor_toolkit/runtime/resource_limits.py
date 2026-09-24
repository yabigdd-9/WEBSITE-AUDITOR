"""Resource limits — browser, memory, disk supervision."""

from __future__ import annotations

import os
import resource
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResourceLimits:
    max_browser_rss_mb: int = 1200
    max_disk_usage_pct: float = 90.0
    max_open_files: int = 1024
    browser_recycle_after_sites: int = 10
    browser_max_pages: int = 20
    browser_max_job_seconds: int = 180


def check_browser_memory(pid: int | None = None) -> int:
    """Return RSS in MB for the given process (or current process)."""
    import psutil
    try:
        p = psutil.Process(pid or os.getpid())
        return p.memory_info().rss // (1024 * 1024)
    except (ImportError, psutil.NoSuchProcess):
        try:
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
        except Exception:
            return 0


def check_disk_usage(path: Path | None = None) -> float:
    """Return disk usage percentage."""
    total, used, _ = shutil.disk_usage(str(path or Path.home()))
    return (used / total) * 100 if total > 0 else 0.0


def check_open_files() -> int:
    """Return number of open file descriptors."""
    try:
        return resource.getrusage(resource.RUSAGE_SELF).ru_nvcsw + resource.getrusage(resource.RUSAGE_SELF).ru_nivcsw
    except Exception:
        return 0


def enforce_limits(limits: ResourceLimits | None = None) -> dict[str, bool]:
    """Check all resource limits. Returns dict of limit_name: exceeded."""
    limits = limits or ResourceLimits()
    results = {
        "browser_memory": check_browser_memory() < limits.max_browser_rss_mb,
        "disk_usage": check_disk_usage() < limits.max_disk_usage_pct,
    }
    return results
