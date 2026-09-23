"""Tests for ProofEnvironment dataclass and probe function."""

from auditor_toolkit.proof.environment import ProofEnvironment, probe_environment


def test_proof_environment_defaults():
    env = ProofEnvironment()
    assert env.browser_name == "chromium"
    assert env.viewport_width == 1280
    assert env.viewport_height == 900
    assert env.device_scale_factor == 1.0
    assert env.locale == "en-NZ"
    assert env.timezone == "Pacific/Auckland"
    assert env.reduced_motion == "no-preference"
    assert env.color_scheme == "light"
    assert env.fonts == []


def test_proof_environment_fingerprint_stable():
    env1 = ProofEnvironment(
        browser_name="chromium",
        browser_version="120.0",
        viewport_width=1280,
        viewport_height=900,
    )
    env2 = ProofEnvironment(
        browser_name="chromium",
        browser_version="120.0",
        viewport_width=1280,
        viewport_height=900,
    )
    assert env1.fingerprint() == env2.fingerprint()


def test_proof_environment_fingerprint_different():
    env1 = ProofEnvironment(viewport_width=1280, viewport_height=900)
    env2 = ProofEnvironment(viewport_width=1920, viewport_height=1080)
    assert env1.fingerprint() != env2.fingerprint()


def test_proof_environment_matches():
    env1 = ProofEnvironment(browser_version="120.0", viewport_width=1280)
    env2 = ProofEnvironment(browser_version="120.0", viewport_width=1280)
    assert env1.matches(env2)


def test_proof_environment_not_matches():
    env1 = ProofEnvironment(browser_version="120.0")
    env2 = ProofEnvironment(browser_version="121.0")
    assert not env1.matches(env2)


def test_proof_environment_matches_non_instance():
    env = ProofEnvironment()
    assert not env.matches("not-an-env")


def test_proof_environment_fingerprint_includes_fonts():
    env1 = ProofEnvironment(fonts=["Arial", "Helvetica"])
    env2 = ProofEnvironment(fonts=["Helvetica", "Arial"])  # sorted
    assert env1.fingerprint() == env2.fingerprint()


def test_proof_environment_fingerprint_different_fonts():
    env1 = ProofEnvironment(fonts=["Arial"])
    env2 = ProofEnvironment(fonts=["Courier"])
    assert env1.fingerprint() != env2.fingerprint()


def test_proof_environment_frozen():
    env = ProofEnvironment()
    try:
        env.browser_name = "firefox"  # type: ignore[misc]
        assert False, "Should not be able to modify frozen dataclass"
    except (TypeError, AttributeError):
        pass


def test_probe_environment_returns_instance():
    env = probe_environment()
    assert isinstance(env, ProofEnvironment)
    assert env.capture_timestamp != ""
    assert env.page_snapshot_id != ""
    assert env.browser_name == "chromium"
