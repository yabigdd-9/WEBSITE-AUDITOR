"""Tests for runtime soak test runner."""

import tempfile
from pathlib import Path

from auditor_toolkit.runtime.soak import SoakMetrics, SoakRunner


def test_soak_runner_start():
    runner = SoakRunner(output_dir=Path(tempfile.mkdtemp()))
    runner.start()
    assert runner.running
    assert runner.start_time


def test_soak_runner_stop():
    runner = SoakRunner(output_dir=Path(tempfile.mkdtemp()))
    runner.start()
    runner.stop()
    assert not runner.running


def test_soak_record_metrics(tmp_path):
    runner = SoakRunner(output_dir=tmp_path, duration_hours=0.01)  # Very short for testing
    runner.start()
    metrics = SoakMetrics(
        queue_depth=10,
        jobs_completed=5,
        memory_mb=100,
    )
    path = runner.record_metrics(metrics)
    assert path.exists()
    assert runner.snapshot_count == 1


def test_soak_is_complete():
    runner = SoakRunner(output_dir=Path(tempfile.mkdtemp()), duration_hours=0)
    runner.start_time = "2020-01-01T00:00:00+00:00"  # Long ago
    assert runner.is_complete


def test_soak_not_complete():
    runner = SoakRunner(output_dir=Path(tempfile.mkdtemp()), duration_hours=9999)
    runner.start()
    assert not runner.is_complete
