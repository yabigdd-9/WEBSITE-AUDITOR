"""Tests for vulnerability advisory generation."""

from auditor_toolkit.technology.vulns import check_vulnerabilities, get_advisories
from auditor_toolkit.technology.schema import TechFingerprint, TechStack, VersionInfo


def test_get_advisories_affected():
    advisories = get_advisories("WordPress", "5.8")
    assert len(advisories) > 0
    assert any(a.cve_id for a in advisories)


def test_get_advisories_not_affected():
    advisories = get_advisories("WordPress", "6.4")
    assert len(advisories) == 0


def test_get_advisories_unknown_component():
    advisories = get_advisories("UnknownTech", "1.0")
    assert advisories == []


def test_check_vulnerabilities_with_vulns():
    fp = TechFingerprint()
    versions = [VersionInfo(name="WordPress", detected_version="5.8", is_outdated=True)]
    stack = TechStack(fingerprint=fp, versions=versions)
    advisories = check_vulnerabilities(stack)
    assert len(advisories) > 0


def test_check_vulnerabilities_no_vulns():
    fp = TechFingerprint()
    versions = [VersionInfo(name="WordPress", detected_version="6.4", is_outdated=False)]
    stack = TechStack(fingerprint=fp, versions=versions)
    advisories = check_vulnerabilities(stack)
    assert advisories == []
