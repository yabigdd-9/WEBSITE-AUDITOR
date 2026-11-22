"""Tests for proof schema data models."""

from auditor_toolkit.proof.schema import (
    AfterState,
    BeforeState,
    CaptureEnvironment,
    DOMSnapshot,
    IssueRegion,
    ProofPackage,
    ProposedFix,
    ScreenshotArtifact,
    VerificationResult,
)


def test_capture_environment():
    env = CaptureEnvironment(
        viewport_width=1280,
        viewport_height=900,
        browser_type="chromium",
        locale="en-NZ",
    )
    assert env.viewport_width == 1280
    assert env.browser_type == "chromium"


def test_capture_env_fingerprint():
    env1 = CaptureEnvironment(viewport_width=1280, viewport_height=900)
    env2 = CaptureEnvironment(viewport_width=1280, viewport_height=900)
    assert env1.fingerprint() == env2.fingerprint()


def test_capture_env_different():
    env1 = CaptureEnvironment(viewport_width=1280)
    env2 = CaptureEnvironment(viewport_width=1920)
    assert env1.fingerprint() != env2.fingerprint()


def test_screenshot_artifact():
    ss = ScreenshotArtifact(
        path="/tmp/before.png",
        url="https://example.com/",
        viewport="1280x900",
        sha256="abc123",
    )
    assert ss.path == "/tmp/before.png"


def test_dom_snapshot():
    dom = DOMSnapshot(
        html_path="/tmp/dom.html",
        url="https://example.com/",
        key_elements={"h1": "<h1>Test</h1>"},
    )
    assert dom.html_path
    assert "h1" in dom.key_elements


def test_issue_region():
    region = IssueRegion(
        finding_id="finding_001",
        selector="header > h1",
        outer_html_snippet="<h1>Test</h1>",
        description="Missing heading text",
        severity="high",
    )
    assert region.finding_id == "finding_001"
    assert region.selector == "header > h1"


def test_before_state():
    state = BeforeState(
        finding_id="f001",
        url="https://example.com/",
        status="CAPTURED",
    )
    assert state.finding_id == "f001"
    assert state.status == "CAPTURED"


def test_before_state_to_dict():
    state = BeforeState(finding_id="f001", url="https://example.com/")
    d = state.to_dict()
    assert d["finding_id"] == "f001"


def test_proposed_fix():
    fix = ProposedFix(
        finding_id="f001",
        fix_type="html_edit",
        description="Add missing alt text",
        original_value="<img src='x'>",
        proposed_value="<img src='x' alt='description'>",
        confidence=0.9,
    )
    assert fix.fix_type == "html_edit"
    assert fix.confidence == 0.9


def test_proposed_fix_to_dict():
    fix = ProposedFix(finding_id="f001", fix_type="css_change")
    d = fix.to_dict()
    assert d["fix_type"] == "css_change"


def test_after_state():
    state = AfterState(
        finding_id="f001",
        proposed_fix_id="fix_001",
        url="https://example.com/",
        status="CAPTURED",
    )
    assert state.finding_id == "f001"
    assert state.proposed_fix_id == "fix_001"


def test_verification_result():
    result = VerificationResult(
        finding_id="f001",
        proposed_fix_id="fix_001",
        verdict="FIXED",
        original_defect_present=False,
        new_defects_introduced=[],
        confidence=0.95,
    )
    assert result.verdict == "FIXED"
    assert not result.original_defect_present


def test_verification_result_to_dict():
    result = VerificationResult(
        finding_id="f001",
        proposed_fix_id="fix_001",
        verdict="NOT_FIXED",
    )
    d = result.to_dict()
    assert d["verdict"] == "NOT_FIXED"


def test_proof_package():
    before = BeforeState(finding_id="f001", url="https://example.com/", status="CAPTURED")
    after = AfterState(finding_id="f001", proposed_fix_id="fix_001", url="https://example.com/", status="CAPTURED")
    fix = ProposedFix(finding_id="f001", fix_type="html_edit")
    verification = VerificationResult(finding_id="f001", proposed_fix_id="fix_001")
    pkg = ProofPackage(
        package_id="pkg_001",
        finding_id="f001",
        url="https://example.com/",
        before=before,
        proposed_fix=fix,
        after=after,
        verification=verification,
    )
    assert pkg.package_id == "pkg_001"
    assert not pkg.is_complete()


def test_proof_package_complete():
    before = BeforeState(finding_id="f001", url="https://example.com/", status="CAPTURED")
    after = AfterState(finding_id="f001", proposed_fix_id="fix_001", url="https://example.com/", status="CAPTURED")
    fix = ProposedFix(finding_id="f001", fix_type="html_edit")
    verification = VerificationResult(finding_id="f001", proposed_fix_id="fix_001", verdict="FIXED")
    pkg = ProofPackage(
        package_id="pkg_001",
        finding_id="f001",
        url="https://example.com/",
        before=before,
        proposed_fix=fix,
        after=after,
        verification=verification,
    )
    assert pkg.is_complete()


def test_proof_package_to_dict():
    before = BeforeState(finding_id="f001", url="https://example.com/")
    after = AfterState(finding_id="f001", proposed_fix_id="fix_001", url="https://example.com/")
    fix = ProposedFix(finding_id="f001", fix_type="html_edit")
    verification = VerificationResult(finding_id="f001", proposed_fix_id="fix_001")
    pkg = ProofPackage(
        package_id="pkg_001",
        finding_id="f001",
        url="https://example.com/",
        before=before,
        proposed_fix=fix,
        after=after,
        verification=verification,
    )
    d = pkg.to_dict()
    assert d["package_id"] == "pkg_001"
