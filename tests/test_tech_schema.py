"""Tests for technology schema."""

from auditor_toolkit.technology.schema import (
    TechDetection,
    TechEnrichmentResult,
    TechFingerprint,
    TechStack,
    VersionInfo,
    VulnerabilityAdvisory,
)


def test_tech_detection_defaults():
    d = TechDetection(name="WordPress", category="cms")
    assert d.name == "WordPress"
    assert d.confidence == 1.0
    assert d.evidence == ""


def test_tech_detection_to_dict():
    d = TechDetection(name="React", category="framework", confidence=0.9)
    dt = d.to_dict()
    assert dt["name"] == "React"


def test_fingerprint_empty():
    fp = TechFingerprint()
    assert fp.cms is None
    assert fp.all_detections == []


def test_fingerprint_to_dict():
    fp = TechFingerprint()
    d = fp.to_dict()
    assert "cms" in d
    assert "framework" in d


def test_fingerprint_with_detections():
    cms = TechDetection(name="WordPress", category="cms", confidence=0.95)
    fw = TechDetection(name="jQuery", category="framework", confidence=0.9)
    fp = TechFingerprint(cms=cms, framework=fw)
    assert len(fp.all_detections) == 2
    assert len(fp.all_detections) == 2


def test_version_info():
    v = VersionInfo(name="WordPress", detected_version="5.8", latest_version="6.4", is_outdated=True)
    assert v.is_outdated
    assert v.detected_version == "5.8"


def test_vulnerability_advisory():
    a = VulnerabilityAdvisory(component="WordPress", version="5.8", severity="high", cve_id="CVE-2023-1234")
    assert a.severity == "high"
    assert a.cve_id == "CVE-2023-1234"


def test_vulnerability_advisory_to_dict():
    a = VulnerabilityAdvisory(component="jQuery", severity="medium")
    d = a.to_dict()
    assert d["component"] == "jQuery"


def test_tech_stack():
    fp = TechFingerprint()
    stack = TechStack(fingerprint=fp)
    assert len(stack.vulnerabilities) == 0
    assert len(stack.versions) == 0


def test_tech_stack_with_vulns():
    from datetime import UTC, datetime
    fp = TechFingerprint()
    vuln = VulnerabilityAdvisory(component="WordPress", severity="high", detected_at=datetime.now(UTC).isoformat())
    stack = TechStack(fingerprint=fp, vulnerabilities=[vuln])
    assert len(stack.vulnerabilities) == 1


def test_tech_stack_with_outdated():
    fp = TechFingerprint()
    v = VersionInfo(name="WordPress", is_outdated=True)
    stack = TechStack(fingerprint=fp, versions=[v])
    assert len(stack.versions) == 1


def test_enrichment_result():
    fp = TechFingerprint()
    result = TechEnrichmentResult(url="https://example.com", fingerprint=fp)
    assert result.url == "https://example.com"
    assert result.tech_stack.fingerprint == fp
