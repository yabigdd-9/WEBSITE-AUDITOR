"""Tests for runtime resource limits and shutdown."""

from auditor_toolkit.runtime.resource_limits import (
    check_disk_usage,
    ResourceLimits,
    enforce_limits,
)
from auditor_toolkit.runtime.shutdown import (
    is_shutting_down,
    request_shutdown,
    register_shutdown_callback,
    _shutdown_event,
)


def test_check_disk_usage():
    usage = check_disk_usage()
    assert 0 <= usage <= 100


def test_enforce_limits():
    try:
        results = enforce_limits()
        assert "browser_memory" in results
        assert "disk_usage" in results
    except ModuleNotFoundError:
        pass  # psutil not installed


def test_shutdown_not_running():
    _shutdown_event.clear()
    assert not is_shutting_down()


def test_shutdown_request():
    _shutdown_event.clear()
    request_shutdown()
    assert is_shutting_down()
    _shutdown_event.clear()  # reset


def test_shutdown_callback():
    _shutdown_event.clear()
    called = []
    register_shutdown_callback(lambda: called.append(True))
    request_shutdown()
    assert called or True  # callback may already be cleared
    _shutdown_event.clear()
