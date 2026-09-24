import importlib.util
from pathlib import Path

_SOURCE = Path(__file__).parents[1] / "runtime_memory_measurer.py"
_SPEC = importlib.util.spec_from_file_location("runtime_memory_measurer", _SOURCE)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
measure_memory = _MODULE.measure_memory
measure_runtime = _MODULE.measure_runtime


def test_runtime_measurer_returns_result():
    elapsed, result = measure_runtime(sum, [1, 2, 3])

    assert elapsed >= 0
    assert result == 6


def test_memory_measurer_runs_function_and_reports_peak_bytes():
    peak_bytes, result = measure_memory(lambda: bytearray(100_000))

    assert peak_bytes > 0
    assert len(result) == 100_000
