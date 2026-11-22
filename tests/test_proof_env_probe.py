"""Tests for proof capture environment probing."""

from auditor_toolkit.proof.capture.env_probe import (
    CaptureEnvironment,
    probe_environment,
)


def test_probe_environment_defaults():
    env = probe_environment()
    assert isinstance(env, CaptureEnvironment)
    assert env.viewport_width == 1280
    assert env.viewport_height == 900
    assert env.browser_type == "chromium"
    assert env.locale == "en-NZ"
    assert env.timezone == "Pacific/Auckland"


def test_probe_environment_custom_viewport():
    env = probe_environment(viewport_width=1920, viewport_height=1080)
    assert env.viewport_width == 1920
    assert env.viewport_height == 1080


def test_probe_environment_fingerprint():
    env = probe_environment()
    fp = env.fingerprint()
    assert len(fp) == 16
