"""Tests for runtime health matrix."""

from auditor_toolkit.runtime.health import check_health, HealthMatrix, CapabilityHealth


def test_check_health_passes():
    matrix = check_health()
    assert matrix.overall in ("PASS", "DEGRADED_OPTIONAL")
    assert len(matrix.capabilities) > 0


def test_check_health_custom_caps():
    matrix = check_health(capabilities=["discovery", "crawl"])
    assert "discovery" in matrix.capabilities
    assert "proof" not in matrix.capabilities


def test_health_matrix_is_ready():
    caps = {"test": CapabilityHealth(name="test", status="PASS")}
    m = HealthMatrix(capabilities=caps, overall="PASS")
    assert m.is_ready


def test_health_matrix_blocked():
    caps = {"test": CapabilityHealth(name="test", status="BLOCKED")}
    m = HealthMatrix(capabilities=caps, overall="BLOCKED")
    assert not m.is_ready


def test_health_matrix_to_dict():
    caps = {"test": CapabilityHealth(name="test", status="PASS", detail="ok")}
    m = HealthMatrix(capabilities=caps, overall="PASS")
    d = m.to_dict()
    assert d["overall"] == "PASS"
    assert "test" in d["capabilities"]
