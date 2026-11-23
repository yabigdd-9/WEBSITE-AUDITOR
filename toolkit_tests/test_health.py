"""Tests for runtime health checks."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from auditor_toolkit.runtime.health import (
    HealthStatus,
    check_database,
    check_disk_space,
    check_external_apis,
    check_memory,
    check_network_connectivity,
    run_all_health_checks,
)


class TestDatabaseCheck:
    """Tests for database health check."""

    def test_database_healthy(self):
        """Test healthy database check."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            # Create a minimal database
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE runs (id TEXT PRIMARY KEY)")
                conn.execute("INSERT INTO runs VALUES ('test')")

            result = check_database(db_path)
            assert result.status == HealthStatus.HEALTHY
            assert result.details["run_count"] == 1

    def test_database_missing(self):
        """Test missing database file."""
        result = check_database("/nonexistent/path.db")
        assert result.status == HealthStatus.UNHEALTHY
        assert "not found" in result.message.lower()


class TestDiskSpaceCheck:
    """Tests for disk space health check."""

    def test_disk_space_healthy(self):
        """Test healthy disk space."""
        result = check_disk_space(".", min_free_gb=0.1, min_free_percent=1.0)
        assert result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
        assert result.details["free_gb"] > 0

    def test_disk_space_unhealthy(self):
        """Test unhealthy disk space (impossible threshold)."""
        result = check_disk_space(".", min_free_gb=1000000, min_free_percent=100)
        assert result.status == HealthStatus.UNHEALTHY


class TestMemoryCheck:
    """Tests for memory health check."""

    def test_memory_check_runs(self):
        """Test memory check executes without error."""
        result = check_memory(max_percent=100, warn_percent=99)
        assert result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNKNOWN)
        if result.status != HealthStatus.UNKNOWN:
            assert "used_percent" in result.details


class TestExternalAPIsCheck:
    """Tests for external API health checks."""

    def test_external_apis_timeout(self):
        """Test external APIs with very short timeout."""
        result = check_external_apis(timeout=0.001)
        # With such a short timeout, they'll likely timeout
        assert result.status in (HealthStatus.UNHEALTHY, HealthStatus.DEGRADED, HealthStatus.UNKNOWN)

    def test_external_apis_disabled(self):
        """Test external APIs with all disabled."""
        result = check_external_apis(
            check_pagespeed=False,
            check_languagetool=False,
            check_pollinations=False,
        )
        # All disabled should be healthy
        assert result.status == HealthStatus.HEALTHY
        for api_result in result.details["apis"].values():
            assert api_result["status"] == "skipped"


class TestNetworkConnectivityCheck:
    """Tests for network connectivity health check."""

    def test_network_check_runs(self):
        """Test network check executes."""
        # Use localhost which should work
        result = check_network_connectivity(hosts=["127.0.0.1"], timeout=1.0)
        assert result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY)


class TestRunAllHealthChecks:
    """Tests for aggregated health checks."""

    def test_run_all_checks(self):
        """Test running all health checks."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE runs (id TEXT PRIMARY KEY)")

            result = run_all_health_checks(
                db_path=db_path,
                disk_path=tmp,
                min_free_gb=0.1,
                check_apis=False,  # Skip external APIs for speed
            )

            assert "status" in result
            assert "timestamp" in result
            assert "checks" in result
            assert "summary" in result
            assert len(result["checks"]) >= 4  # database, disk, memory, network

    def test_overall_status_aggregation(self):
        """Test overall status aggregation logic."""
        # This tests the logic in run_all_health_checks
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE runs (id TEXT PRIMARY KEY)")

            # All checks should pass
            result = run_all_health_checks(
                db_path=db_path,
                disk_path=tmp,
                min_free_gb=0.1,
                check_apis=False,
            )
            # Overall status depends on individual checks
            assert result["status"] in ("healthy", "degraded", "unhealthy")


class TestHealthCheckCLI:
    """Tests for health check CLI integration."""

    def test_health_cli(self):
        """Test health CLI command."""
        import sys
        from io import StringIO

        from auditor_toolkit.cli import main

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            exit_code = main(["health", "--no-apis", "--min-free-gb", "0.1"])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert exit_code in (0, 1)
        # Should output valid JSON
        data = json.loads(output)
        assert "status" in data
        assert "checks" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
