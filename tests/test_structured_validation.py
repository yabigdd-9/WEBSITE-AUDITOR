"""Regression coverage for JSON-LD structured data validation."""

from auditor_toolkit.structured_validation import analyse_html


def test_valid_jsonld_dict_with_type_has_no_findings():
    html = '<script type="application/ld+json">{"@type":"LocalBusiness"}</script>'
    findings, evidence = analyse_html(html, "https://example.test", {})
    assert findings == []
    assert evidence["structured_data_scripts_found"] == 1


def test_jsonld_without_type_reports_finding():
    html = '<script type="application/ld+json">{"name":"Example"}</script>'
    findings, _ = analyse_html(html, "https://example.test", {})
    assert [finding.defect_key for finding in findings] == ["structured_data_missing_type"]


def test_jsonld_list_reports_only_items_without_type():
    html = (
        '<script type="application/ld+json">'
        '[{"@type":"LocalBusiness"},{"name":"No type"},null]'
        "</script>"
    )
    findings, _ = analyse_html(html, "https://example.test", {})
    assert [finding.defect_key for finding in findings] == [
        "structured_data_item_missing_type_1",
        "structured_data_item_missing_type_2",
    ]


def test_invalid_jsonld_reports_invalid_json():
    html = '<script type="application/ld+json">{not json}</script>'
    findings, _ = analyse_html(html, "https://example.test", {})
    assert [finding.defect_key for finding in findings] == ["structured_data_invalid_json"]
