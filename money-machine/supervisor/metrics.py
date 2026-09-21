"""Optional Prometheus-format export for the supervisor.

The v32 default observability path is lightweight JSON/JSONL. This helper remains
optional and must compile cleanly even when Prometheus is not used.
"""
from __future__ import annotations

from datetime import datetime


def export_prometheus_metrics(d) -> str:
    lines = []

    for row in d.execute("SELECT state, count(*) n FROM pipeline_items GROUP BY state"):
        state = str(row["state"]).replace('"', "_")
        lines.append(f'pipeline_items_total{{state="{state}"}} {row["n"]}')

    for row in d.execute("SELECT worker_id, lease_seconds FROM worker_registry"):
        worker_id = str(row["worker_id"]).replace('"', "_")
        lines.append(f'worker_alive{{worker_id="{worker_id}"}} 1')

    active = d.execute(
        "SELECT count(*) FROM pipeline_items "
        "WHERE lease_until IS NOT NULL AND lease_until > ?",
        (datetime.now().isoformat(),),
    ).fetchone()[0]
    lines.append(f"lease_active_total {active}")

    for row in d.execute("SELECT service, state FROM circuit_breakers"):
        service = str(row["service"]).replace('"', "_")
        state = str(row["state"]).replace('"', "_")
        state_val = {"closed": 0, "open": 1, "half_open": 0.5}.get(row["state"], -1)
        lines.append(
            f'circuit_breaker_state{{service="{service}",state="{state}"}} {state_val}'
        )

    for row in d.execute("SELECT bucket, count, cap FROM rate_buckets"):
        bucket = str(row["bucket"]).replace('"', "_")
        used = row["count"]
        cap = row["cap"]
        lines.append(f'rate_bucket_usage{{bucket="{bucket}",used="{used}",cap="{cap}"}} {used}')

    for row in d.execute("SELECT name, value FROM mm_metrics"):
        name = str(row["name"]).replace("-", "_").replace(".", "_")
        lines.append(f"{name} {row['value']}")

    return "\n".join(lines) + "\n"


def export_prometheus_metrics_cli(d):
    print(export_prometheus_metrics(d))
