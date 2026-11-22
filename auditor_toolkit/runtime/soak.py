"""7-day soak test — continuous operation validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SoakMetrics:
    timestamp: str = ""
    queue_depth: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    retries: int = 0
    dlq_count: int = 0
    quarantine_count: int = 0
    worker_count: int = 0
    browser_crashes: int = 0
    memory_mb: int = 0
    disk_usage_pct: float = 0.0
    findings_count: int = 0
    high_confidence_findings: int = 0
    proof_success_count: int = 0
    review_package_count: int = 0
    false_positive_count: int = 0
    golden_corpus_pass: int = 0
    golden_corpus_fail: int = 0


@dataclass
class SoakRunner:
    output_dir: Path
    start_time: str = ""
    duration_hours: int = 168
    metrics_interval_seconds: int = 60
    running: bool = False
    snapshot_count: int = 0

    def start(self) -> None:
        self.start_time = datetime.now(UTC).isoformat()
        self.running = True

    def stop(self) -> None:
        self.running = False

    def record_metrics(self, metrics: SoakMetrics) -> Path:
        self.snapshot_count += 1
        hourly_dir = self.output_dir / f"hour-{self.snapshot_count:06d}"
        hourly_dir.mkdir(parents=True, exist_ok=True)
        path = hourly_dir / "metrics.json"
        path.write_text(json.dumps(metrics.__dict__, indent=2))
        return path

    @property
    def elapsed_hours(self) -> float:
        if not self.start_time:
            return 0.0
        start = datetime.fromisoformat(self.start_time)
        return (datetime.now(UTC) - start).total_seconds() / 3600

    @property
    def is_complete(self) -> bool:
        return self.elapsed_hours >= self.duration_hours
