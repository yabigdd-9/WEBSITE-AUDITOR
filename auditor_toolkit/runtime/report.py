"""Release readiness report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ReleaseStatus = Literal["READY", "READY_WITH_LIMITATIONS", "NOT_READY"]


@dataclass
class ReleaseReadinessReport:
    commit_sha: str = ""
    start_time: str = ""
    end_time: str = ""
    status: ReleaseStatus = "NOT_READY"
    gates_passed: int = 0
    gates_total: int = 0
    limitations: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit_sha": self.commit_sha,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status,
            "gates_passed": self.gates_passed,
            "gates_total": self.gates_total,
            "limitations": self.limitations,
            "metrics": self.metrics,
        }


def generate_release_report(
    commit_sha: str = "",
    soak_hours: float = 0.0,
    gates: dict[str, bool] | None = None,
    metrics: dict[str, Any] | None = None,
    limitations: list[str] | None = None,
) -> ReleaseReadinessReport:
    from datetime import UTC, datetime

    gates = gates or {}
    metrics = metrics or {}
    limitations = limitations or []

    passed = sum(1 for v in gates.values() if v)
    total = len(gates)

    if soak_hours < 168 or passed < total:
        status = "NOT_READY"
    elif limitations:
        status = "READY_WITH_LIMITATIONS"
    else:
        status = "READY"

    return ReleaseReadinessReport(
        commit_sha=commit_sha,
        start_time=metrics.get("soak_start", ""),
        end_time=datetime.now(UTC).isoformat(),
        status=status,
        gates_passed=passed,
        gates_total=total,
        limitations=limitations,
        metrics=metrics,
    )


def save_report(report: ReleaseReadinessReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "RELEASE_READINESS.json"
    json_path.write_text(json.dumps(report.to_dict(), indent=2))

    md_path = output_dir / "RELEASE_READINESS.md"
    md_path.write_text(_render_markdown(report))
    return json_path, md_path


def _render_markdown(report: ReleaseReadinessReport) -> str:
    lines = [
        "# Release Readiness Report",
        f"**Commit:** {report.commit_sha}",
        f"**Status:** {report.status}",
        f"**Gates:** {report.gates_passed}/{report.gates_total}",
        "",
        "## Metrics",
        "",
    ]
    for k, v in report.metrics.items():
        lines.append(f"- **{k}:** {v}")
    if report.limitations:
        lines += ["", "## Limitations", ""]
        for limitation in report.limitations:
            lines.append(f"- {limitation}")
    return "\n".join(lines)
