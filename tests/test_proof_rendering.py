"""Regression tests for generated proof artifacts."""

import pytest

from auditor_toolkit.proof.render.demo import generate_demo_html
from auditor_toolkit.proof.render.diff import generate_diff
from auditor_toolkit.proof.render.report import generate_markdown_report
from auditor_toolkit.proof.schema import (
    AfterState,
    BeforeState,
    ProofPackage,
    ProposedFix,
    ScreenshotArtifact,
    VerificationResult,
)


def _proof_package() -> ProofPackage:
    return ProofPackage(
        package_id="pkg-1",
        finding_id="finding-1",
        url="https://example.com",
        before=BeforeState(
            finding_id="finding-1",
            url="https://example.com",
            screenshot=ScreenshotArtifact(path="before.png"),
            console_errors=["old error"],
            axe_violations=[{"id": "contrast"}],
            lighthouse_scores={"performance": 71},
            status="CAPTURED",
        ),
        proposed_fix=ProposedFix(
            finding_id="finding-1",
            fix_type="html_edit",
            description="Add an accessible label",
            original_value="<input>",
            proposed_value='<input aria-label="Search">',
            confidence=0.9,
            rationale="The control had no accessible name.",
        ),
        after=AfterState(
            finding_id="finding-1",
            proposed_fix_id="fix-1",
            url="https://example.com",
            screenshot=ScreenshotArtifact(path="after.png"),
            console_errors=[],
            status="CAPTURED",
        ),
        verification=VerificationResult(
            finding_id="finding-1",
            proposed_fix_id="fix-1",
            verdict="FIXED",
            original_defect_present=False,
            diff_summary="Accessible name is present.",
            confidence=0.95,
            verifier_id="test-verifier",
            notes="Verified by independent check.",
        ),
        before_screenshot_path="before.png",
        after_screenshot_path="after.png",
        diff_path="diff.png",
        status="READY",
        created_at="2026-09-24T00:00:00Z",
    )


def test_generate_demo_html_escapes_untrusted_values(tmp_path):
    package = _proof_package()
    package.url = 'https://example.com/?q="<script>alert(1)</script>'
    package.proposed_fix.description = "<script>alert('x')</script>"
    package.before_screenshot_path = "before.png' onerror='alert(1)"

    html_path = generate_demo_html(
        output_dir=str(tmp_path),
        package=package,
        title="<script>alert('title')</script>",
    )

    html = (tmp_path / html_path.split("/")[-1]).read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "onerror=&#x27;alert(1)" in html


def test_generate_markdown_report_includes_proof_details(tmp_path):
    path = generate_markdown_report(_proof_package(), output_dir=str(tmp_path))

    report = (tmp_path / path.split("/")[-1]).read_text(encoding="utf-8")
    assert "# Proof Report — pkg-1" in report
    assert "FIXED" in report
    assert "Accessible name is present." in report
    assert "Before screenshot" in report
    assert "after.png" in report


def test_generate_diff_compares_images_and_writes_artifact(tmp_path):
    pil = pytest.importorskip("PIL.Image")
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    pil.new("RGB", (2, 2), "white").save(before)
    pil.new("RGB", (2, 2), "black").save(after)

    result = generate_diff(str(before), str(after), output_dir=str(tmp_path))

    assert result["diff_percent"] == 100.0
    assert (tmp_path / result["diff_path"].split("/")[-1]).is_file()
