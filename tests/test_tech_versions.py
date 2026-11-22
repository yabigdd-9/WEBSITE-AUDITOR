"""Tests for technology version detection."""

from auditor_toolkit.technology.versions import (
    _is_outdated,
    check_outdated,
    detect_version,
)


def test_detect_version_wordpress():
    html = '<meta name="generator" content="WordPress 5.8">'
    v = detect_version("WordPress", html=html)
    assert v.detected_version == "5.8"
    assert v.is_outdated


def test_detect_version_jquery():
    html = '<script src="jquery-3.4.1.min.js"></script>'
    v = detect_version("jQuery", html=html)
    assert v.detected_version == "3.4.1"
    assert v.is_outdated


def test_detect_version_unknown():
    v = detect_version("UnknownTech")
    assert v.detected_version == ""
    assert v.latest_version == ""


def test_detect_version_known_no_extraction():
    v = detect_version("PHP", known_version="8.1")
    assert v.detected_version == "8.1"
    assert v.is_outdated  # Latest is 8.3


def test_is_outdated_true():
    assert _is_outdated("5.8", "6.4")


def test_is_outdated_false():
    assert not _is_outdated("6.4", "6.4")
    assert not _is_outdated("6.5", "6.4")


def test_check_outdated():
    versions = [
        detect_version("WordPress", known_version="5.8"),
        detect_version("jQuery", known_version="3.7.1"),
    ]
    outdated = check_outdated(versions)
    assert len(outdated) == 1
    assert outdated[0].name == "WordPress"
