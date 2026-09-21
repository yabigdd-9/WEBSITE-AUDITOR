"""Prometheus metrics export for the supervisor."""
from datetime import datetime

from mm_pipeline import root


def _label(value) -> str:
    """Escape a Prometheus label value deterministically."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def export_prometheus_metrics(d) -> str:
    """Export metrics in Prometheus text format."""
    lines = []

    for row in d.execute("SELECT state, count(*) n FROM pipeline_items GROUP BY state"):
        lines.append(
            'pipeline_items_total{state="' + _label(row["state"]) + '"} ' + str(row["n"])
        )

    for row in d.execute("SELECT worker_id, lease_seconds FROM worker_registry"):
        lines.append(
            'worker_alive{worker_id="' + _label(row["worker_id"]) + '"} 1'
        )

    active = d.execute(
        "SELECT count(*) FROM pipeline_items "
        "WHERE lease_until IS NOT NULL AND lease_until > ?",
        (datetime.now().isoformat(),),
    ).fetchone()[0]
    lines.append("lease_active_total " + str(active))

    for row in d.execute("SELECT service, state FROM circuit_breakers"):
        state_val = {"closed": 0, "open": 1, "half_open": 0.5}.get(row["state"], -1)
        lines.append(
            'circuit_breaker_state{service="' + _label(row["service"])
            + '",state="' + _label(row["state"]) + '"} ' + str(state_val)
        )

    for row in d.execute("SELECT bucket, count, cap FROM rate_buckets"):
        lines.append(
            'rate_bucket_usage{bucket="' + _label(row["bucket"])
            + '",used="' + _label(row["count"])
            + '",cap="' + _label(row["cap"]) + '"} ' + str(row["count"])
        )

    for row in d.execute("SELECT name, value FROM mm_metrics"):
        lines.append(str(row["name"]) + " " + str(row["value"]))

    return "\n".join(lines) + "\n"


def export_prometheus_metrics_cli(d):
    print(export_prometheus_metrics(d))
