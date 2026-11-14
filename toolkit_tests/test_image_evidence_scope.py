"""Regression cases for unsupported image-performance conclusions."""
from auditor_toolkit.images import analyse_html


def test_intentionally_eager_images_are_not_lazy_loading_defects():
    findings, evidence = analyse_html(
        '<img src="/logo.png" alt="Brand" width="160" height="40">'
        '<img src="/hero.jpg" alt="Main artwork" width="1200" height="800" fetchpriority="high">',
        "https://example.com/", {},
    )
    assert evidence["missing_loading"] == 2
    assert not findings


def test_framework_fill_requires_rendered_review_without_claiming_cls():
    findings, evidence = analyse_html(
        '<div style="position:relative;min-height:430px">'
        '<img data-nimg="fill" src="/hero.jpg" alt="Artwork" '
        'style="position:absolute;width:100%;height:100%"></div>',
        "https://example.com/", {},
    )
    assert evidence["framework_fill_images"] == 1
    finding, = findings
    assert finding.defect_key == "images-missing-dimensions"
    assert finding.confidence == "heuristic"
    assert finding.remediation_automation == "HUMAN_REVIEW"
    assert "does not establish CLS" in finding.business_impact
    assert "preserve intentional framework fill" in finding.remediation_action


def test_unreserved_image_still_requires_investigation():
    findings, evidence = analyse_html('<img src="/photo.jpg" alt="Photo">', "https://example.com/", {})
    assert evidence["missing_dimensions"] == 1
    assert [finding.defect_key for finding in findings] == ["images-missing-dimensions"]


def test_missing_alt_remains_an_observed_accessibility_finding():
    findings, _ = analyse_html('<img src="/photo.jpg" width="50" height="50">', "https://example.com/", {})
    finding, = findings
    assert finding.defect_key == "images-missing-alt"
    assert finding.confidence == "observed"


def test_invalid_dimensions_are_counted_without_claiming_attributes_absent():
    findings, evidence = analyse_html('<img src="/photo.jpg" alt="" width="0" height="auto">', "https://example.com/", {})
    assert evidence["missing_dimensions"] == 1
    assert "do not provide positive numeric" in findings[0].observed
