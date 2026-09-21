#!/usr/bin/env python3
"""Unified Operator Dashboard - consolidates all system metrics and health indicators."""

import contextlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from mm_core import connect, now, root


def generate_unified_dashboard() -> Dict[str, Any]:
    """Generate a comprehensive dashboard combining all system metrics."""

    dashboard = {
        "generated_at": now(),
        "system_health": get_system_health(),
        "supervisor_status": get_supervisor_status(),
        "model_router_stats": get_model_router_stats(),
        "pipeline_metrics": get_pipeline_metrics(),
        "learning_insights": get_learning_insights(),
        "financial_metrics": get_financial_metrics(),
        "performance_indicators": get_performance_indicators()
    }

    return dashboard


def get_system_health() -> Dict[str, Any]:
    """Get overall system health status."""
    try:
        # Check database connectivity
        with contextlib.closing(connect()) as conn:
            conn.execute("SELECT 1").fetchone()
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Check if supervisor is running
    supervisor_pid = _read_supervisor_pid()
    supervisor_status = "running" if supervisor_pid and _pid_alive(supervisor_pid) else "stopped"

    return {
        "database": db_status,
        "supervisor": supervisor_status,
        "timestamp": now()
    }


def get_supervisor_status() -> Dict[str, Any]:
    """Get supervisor and worker status."""
    import subprocess
    import os
    from supervisor.cli import _read_pid, _is_running, _log

    pid = _read_pid()
    alive = pid is not None and _pid_alive(pid)

    try:
        hb = {}
        if _read_pid():
            hb_str = (root() / "state" / "supervisor.heartbeat").read_text().strip()
            hb = json.loads(hb_str) if hb_str else {}
    except Exception:
        hb = {"error": "Unable to read heartbeat"}

    # Get worker stats from pipeline
    worker_stats = get_worker_statistics()

    return {
        "running": bool(alive),
        "pid": pid if alive else None,
        "heartbeat": hb,
        "workers": worker_stats
    }


def get_worker_statistics() -> Dict[str, Any]:
    """Get statistics for all pipeline workers."""
    try:
        with contextlib.closing(connect(readonly=True)) as conn:
            # Get recent processing stats
            rows = conn.execute("""
                SELECT
                    state,
                    COUNT(*) as count,
                    AVCASE WHEN julianday(updated_at) - julianday(created_at) > 0
                         THEN (julianday(updated_at) - julianday(created_at)) * 86400
                         ELSE 0 END as avg_processing_time_seconds
                FROM pipeline_items
                WHERE updated_at >= datetime('now', '-1 hour')
                GROUP BY state
            """).fetchall()

            return {
                row[0]: {
                    "count": row[1],
                    "avg_processing_time_seconds": round(row[2] or 0, 2)
                } for row in rows
            }
    except Exception as e:
        return {"error": str(e)}


def get_model_router_stats() -> Dict[str, Any]:
    """Get model router usage and compliance statistics."""
    try:
        with contextlib.closing(connect(readonly=True)) as conn:
            # Get model invocation stats from last 24 hours
            rows = conn.execute("""
                SELECT
                    provider,
                    COUNT(*) as total_calls,
                    SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked_calls,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_calls,
                    AVG(cost_usd) as avg_cost_usd
                FROM mm_model_invocations
                WHERE created_at >= datetime('now', '-1 day')
                GROUP BY provider
            """).fetchall()

            total_calls = sum(row[1] for row in rows) if rows else 0
            blocked_calls = sum(row[2] for row in rows) if rows else 0

            zero_cost_compliance = (
                (blocked_calls / total_calls * 100) if total_calls > 0 else 100.0
            )  # All blocked calls are zero-cost by policy

            return {
                "providers": {
                    row[0]: {
                        "total_calls": row[1],
                        "blocked_calls": row[2],
                        "successful_calls": row[3],
                        "avg_cost_usd": round(row[4] or 0, 4),
                        "zero_cost_compliant": (row[2] / row[1] * 100) if row[1] > 0 else 100.0
                    } for row in rows
                },
                "summary": {
                    "total_calls_24h": total_calls,
                    "blocked_calls_24h": blocked_calls,
                    "zero_cost_compliance_percentage": round(zero_cost_compliance, 2),
                    "total_cost_usd_24h": round(sum((row[4] or 0) * row[1] for row in rows), 4)
                }
            }
    except Exception as e:
        return {"error": str(e)}


def get_pipeline_metrics() -> Dict[str, Any]:
    """Get pipeline processing metrics and stage distribution."""
    try:
        with contextlib.closing(connect(readonly=True)) as conn:
            # Stage distribution
            stage_rows = conn.execute("""
                SELECT state, COUNT(*) as count
                FROM pipeline_items
                GROUP BY state
            """).fetchall()

            # Processing rates (last hour)
            rate_rows = conn.execute("""
                SELECT
                    COUNT(*) as processed_last_hour,
                    SUM(CASE WHEN state IN ('DONE', 'VALIDATED') THEN 1 ELSE 0 END) as successful_last_hour
                FROM pipeline_items
                WHERE updated_at >= datetime('now', '-1 hour')
            """).fetchone()

            # Average processing times by stage
            time_rows = conn.execute("""
                SELECT
                    state,
                    AVG(CASE WHEN julianday(updated_at) > julianday(created_at)
                         THEN (julianday(updated_at) - julianday(created_at)) * 86400
                         ELSE 0 END) as avg_seconds
                FROM pipeline_items
                WHERE updated_at >= datetime('now', '-1 hour')
                AND state NOT IN ('PENDING', 'DISCOVERED')
                GROUP BY state
            """).fetchall()

            return {
                "stage_distribution": {row[0]: row[1] for row in stage_rows},
                "processing_rates": {
                    "processed_last_hour": rate_rows[0] if rate_rows else 0,
                    "successful_last_hour": rate_rows[1] if rate_rows else 0,
                    "success_rate_percentage": round(
                        (rate_rows[1] / rate_rows[0] * 100) if rate_rows and rate_rows[0] > 0 else 0, 2
                    )
                },
                "average_processing_times_seconds": {
                    row[0]: round(row[1] or 0, 2) for row in time_rows
                }
            }
    except Exception as e:
        return {"error": str(e)}


def get_learning_insights() -> Dict[str, Any]:
    """Get insights from the learning and experimentation system."""
    try:
        with contextlib.closing(connect(readonly=True)) as conn:
            # Recent learning outcomes
            learning_rows = conn.execute("""
                SELECT
                    pattern,
                    actual,
                    confidence,
                    created_at
                FROM mm_learning
                WHERE created_at >= datetime('now', '-7 days')
                ORDER BY created_at DESC
                LIMIT 20
            """).fetchall()

            # Experiment statistics
            exp_rows = conn.execute("""
                SELECT
                    variant,
                    COUNT(*) as total_experiments,
                    SUM(CASE WHEN result = 'positive' THEN 1 ELSE 0 END) as positive_results
                FROM mm_experiments
                WHERE created_at >= datetime('now', '-30 days')
                GROUP BY variant
            """).fetchall()

            # Weekly experiment suggestions generated
            weekly_suggestions = conn.execute("""
                SELECT COUNT(*) as count
                FROM mm_learning
                WHERE pattern LIKE 'experiment_suggestion_%'
                AND created_at >= datetime('now', '-7 days')
            """).fetchone()[0]

            return {
                "recent_learning": [
                    {
                        "pattern": row[0],
                        "actual_value": row[1],
                        "confidence": row[2],
                        "timestamp": row[3]
                    } for row in learning_rows
                ],
                "experiment_results": {
                    row[0]: {
                        "total_experiments": row[1],
                        "positive_results": row[2],
                        "success_rate_percentage": round(
                            (row[2] / row[1] * 100) if row[1] > 0 else 0, 2
                        )
                    } for row in exp_rows
                },
                "weekly_suggestions_generated": weekly_suggestions
            }
    except Exception as e:
        return {"error": str(e)}


def get_financial_metrics() -> Dict[str, Any]:
    """Get financial and revenue tracking metrics."""
    try:
        with contextlib.closing(connect(readonly=True)) as conn:
            # Revenue metrics
            revenue_row = conn.execute("""
                SELECT
                    SUM(cents) as total_received_cents,
                    COUNT(*) as payment_count,
                    AVG(cents) as avg_payment_cents
                FROM mm_cash
                WHERE occurred_at >= datetime('now', '-30 days')
            """).fetchone()

            # Proposal and quote metrics
            proposal_row = conn.execute("""
                SELECT
                    COUNT(*) as total_proposals,
                    SUM(CASE WHEN stage = 'VALIDATED' THEN 1 ELSE 0 END) as validated_proposals
                FROM mm_deals
                WHERE updated_at >= datetime('now', '-30 days')
            """).fetchone()

            return {
                "revenue": {
                    "total_received_nzd": round((revenue_row[0] or 0) / 100, 2) if revenue_row[0] else 0,
                    "payment_count_30d": revenue_row[1] if revenue_row else 0,
                    "avg_payment_nzd": round((revenue_row[2] or 0) / 100, 2) if revenue_row[2] else 0
                },
                "proposals": {
                    "total_proposals_30d": proposal_row[0] if proposal_row else 0,
                    "validated_proposals_30d": proposal_row[1] if proposal_row else 0,
                    "validation_rate_percentage": round(
                        (proposal_row[1] / proposal_row[0] * 100) if proposal_row and proposal_row[0] > 0 else 0, 2
                    )
                }
            }
    except Exception as e:
        return {"error": str(e)}


def get_performance_indicators() -> Dict[str, Any]:
    """Get key performance indicators and system health metrics."""
    try:
        with contextlib.closing(connect(readonly=True)) as conn:
            # System uptime approximation (based on supervisor start)
            supervisor_start = None
            try:
                supervisor_start_str = (root() / "state" / "supervisor.heartbeat").read_text().strip()
                if supervisor_start_str:
                    supervisor_start = json.loads(supervisor_start_str).get("started")
            except Exception:
                pass

            # Error rates
            error_row = conn.execute("""
                SELECT
                    COUNT(*) as total_errors,
                    SUM(CASE WHEN created_at >= datetime('now', '-24 hours') THEN 1 ELSE 0 END) as errors_24h
                FROM pipeline_items
                WHERE state IN ('RETRYABLE_FAILURE', 'PERMANENT_FAILURE')
            """).fetchone()

            # Business metrics
            business_row = conn.execute("""
                SELECT
                    COUNT(*) as total_businesses,
                    SUM(CASE WHEN is_dummy = 0 THEN 1 ELSE 0 END) as real_businesses,
                    SUM(CASE WHEN discovered_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as new_businesses_week
                FROM businesses
            """).fetchone()

            return {
                "system": {
                    "supervisor_started": supervisor_start,
                    "uptime_approximation_hours": None  # Would need to calculate from supervisor_start
                },
                "error_rates": {
                    "total_errors": error_row[0] if error_row else 0,
                    "errors_last_24h": error_row[1] if error_row else 0
                },
                "business_metrics": {
                    "total_businesses": business_row[0] if business_row else 0,
                    "real_businesses": business_row[1] if business_row else 0,
                    "new_businesses_last_week": business_row[2] if business_row else 0
                }
            }
    except Exception as e:
        return {"error": str(e)}


def _read_supervisor_pid() -> int | None:
    """Read supervisor PID from file."""
    try:
        pid_file = root() / "state" / "supervisor.pid"
        if pid_file.exists():
            return int(pid_file.read_text().strip())
    except Exception:
        pass
    return None


def _pid_alive(pid: int) -> bool:
    """Check if a PID is currently alive."""
    if pid <= 0:
        return False
    try:
        import os
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but we can't signal it
    except OSError:
        return False


def save_dashboard_json():
    """Save dashboard as JSON file."""
    dashboard = generate_unified_dashboard()
    output_path = root() / "reports" / "unified_dashboard.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(dashboard, f, indent=2, default=str)

    return str(output_path)


def save_dashboard_html():
    """Save dashboard as HTML file."""
    dashboard = generate_unified_dashboard()
    html_content = generate_dashboard_html(dashboard)
    output_path = root() / "reports" / "unified_dashboard.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        f.write(html_content)

    return str(output_path)


def generate_dashboard_html(data: Dict[str, Any]) -> str:
    """Generate HTML representation of the dashboard."""
    # This would generate a nice HTML dashboard - simplified for now
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Unified Operator Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 20px; background: #f5f5f5; }}
        .header {{ background: #333; color: white; padding: 20px; border-radius: 8px; }}
        .section {{ background: white; margin: 20px 0; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .metric {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #eee; }}
        .metric-value {{ font-weight: bold; color: #2c3e50; }}
        .metric-label {{ color: #7f8c8d; }}
        .status-healthy {{ color: #27ae60; }}
        .status-warning {{ color: #f39c12; }}
        .status-error {{ color: #e74c3c; }}
        .json-view {{ background: #f8f9fa; padding: 15px; border-radius: 4px; font-family: monospace; font-size: 14px; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 Unified Operator Dashboard</h1>
        <p>Generated at: {data.get('generated_at', 'Unknown')}</p>
    </div>

    <div class="section">
        <h2>System Health</h2>
        <div class="metric">
            <span class="metric-label">Database:</span>
            <span class="metric-value {'status-healthy' if data.get('system_health', {}).get('database') == 'healthy' else 'status-error'}">
                {data.get('system_health', {}).get('database', 'Unknown')}
            </span>
        </div>
        <div class="metric">
            <span class="metric-label">Supervisor:</span>
            <span class="metric-value {'status-healthy' if data.get('system_health', {}).get('supervisor') == 'running' else 'status-error'}">
                {data.get('system_health', {}).get('supervisor', 'Unknown')}
            </span>
        </div>
    </div>

    <div class="section">
        <h2>Pipeline Metrics</h2>
        <div class="metric">
            <span class="metric-label">Processed Last Hour:</span>
            <span class="metric-value">{data.get('pipeline_metrics', {}).get('processing_rates', {}).get('processed_last_hour', 0)}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Success Rate:</span>
            <span class="metric-value">{data.get('pipeline_metrics', {}).get('processing_rates', {}).get('success_rate_percentage', 0)}%</span>
        </span>
        </div>
    </div>

    <div class="section">
        <h2>Financial Metrics</h2>
        <div class="metric">
            <span class="metric-label">Total Received (NZD):</span>
            <span class="metric-value">${data.get('financial_metrics', {}).get('revenue', {}).get('total_received_nzd', 0)}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Payment Count (30d):</span>
            <span class="metric-value">{data.get('financial_metrics', {}).get('revenue', {}).get('payment_count_30d', 0)}</span>
        </div>
    </div>

    <div class="section">
        <h2>Learning & Experiments</h2>
        <div class="metric">
            <span class="metric-label">Weekly Suggestions:</span>
            <span class="metric-value">{data.get('learning_insights', {}).get('weekly_suggestions_generated', 0)}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Experiments (30d):</span>
            <span class="metric-value">{sum(v.get('total_experiments', 0) for v in data.get('learning_insights', {}).get('experiment_results', {}).values())}</span>
        </div>
    </div>

    <div class="section">
        <h2>Raw JSON Data</h2>
        <div class="json-view">{json.dumps(data, indent=2, default=str)}</div>
    </div>
</body>
</html>"""


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--html":
        path = save_dashboard_html()
        print(f"HTML dashboard saved to: {path}")
    else:
        path = save_dashboard_json()
        print(f"JSON dashboard saved to: {path}")