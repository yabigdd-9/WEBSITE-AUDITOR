"""Synthetic regression fixtures only; these are never independent human labels."""

import copy
import hashlib
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from auditor_toolkit.contact_review import compare_contact_review, freeze_contact_dataset
from auditor_toolkit.identity_review import build_identity_review
from auditor_toolkit.implementation_demo import build_implementation_demo
from auditor_toolkit.structured_validation import analyse_html


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def contact_fixture(tmp_path):
    captures = tmp_path / "captures"
    cases = captures / "cases"
    cache = captures / "cache/email-v2"
    cases.mkdir(parents=True)
    cache.mkdir(parents=True)
    business = {"id": "one", "name": "sample.co.nz", "public_website": "https://sample.co.nz/"}
    pages = []
    for index, suffix in enumerate(("", "contact")):
        raw = (
            "<title>Sample Services</title><h1>Sample Services</h1>"
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@graph":[{"@type":"LocalBusiness","name":"Sample Services"}]}'
            "</script><p>Synthetic capture " + str(index) + "</p>"
        ).encode()
        digest = hashlib.sha256(raw).hexdigest()
        path = cache / (digest + ".capture")
        path.write_bytes(raw)
        pages.append(
            {
                "url": "https://sample.co.nz/" + suffix,
                "sha256": digest,
                "path": str(path.relative_to(captures)),
                "content_type": "text/html",
                "captured_at": "2026-10-03",
            }
        )
    case_path = cases / "one.json"
    doc = {
        "business": business,
        "pages": pages,
        "result": {"selected": {"email": "office@sample.co.nz"}},
    }
    write_json(case_path, doc)
    frame = tmp_path / "frame.json"
    frame_hash = write_json(frame, {"cases": [business]})
    dataset = tmp_path / "dataset.json"
    dataset_hash = write_json(dataset, freeze_contact_dataset(frame, captures))
    review = tmp_path / "synthetic-review.json"
    labels = {
        "reviewer": "SYNTHETIC TEST FIXTURE - NOT A HUMAN REVIEW",
        "review_date": "2026-10-03",
        "frame_sha256": frame_hash,
        "frozen_dataset_sha256": dataset_hash,
        "independent_human_review_attested": True,
        "cases": [
            {
                "case_id": "one",
                "identity_label": "CONFIRMED",
                "confirmed_business_name": "Sample Services",
                "publicly_attributable_emails": "office@sample.co.nz",
                "evidence_references": "Synthetic fixture bytes",
                "no_email_or_unresolved_reason": "",
            }
        ],
    }
    write_json(review, labels)
    return captures, frame, dataset, review, labels, case_path, doc


def test_identity_two_distinct_pages_is_proposal_only(contact_fixture):
    result = build_identity_review(contact_fixture[0])
    item = result["cases"][0]
    assert item["status"] == "PROPOSAL_READY_FOR_REVIEW"
    assert item["proposed_trading_name"] == "Sample Services"
    assert not item["identity_verified"] and not item["human_confirmed"]
    assert not item["canonical_database_changed"] and not item["outreach_eligible"]


@pytest.mark.parametrize(
    "mode",
    [
        "one_page",
        "same_bytes",
        "same_url",
        "different_name",
        "existing_trading_name",
        "tampered_bytes",
        "external_capture",
        "domain_mismatch",
    ],
)
def test_identity_weak_or_invalid_evidence_stays_held(contact_fixture, mode):
    captures, _, _, _, _, case_path, doc = contact_fixture
    if mode == "one_page":
        doc["pages"] = doc["pages"][:1]
    elif mode == "same_bytes":
        doc["pages"][1] = {**doc["pages"][0], "url": "https://sample.co.nz/contact"}
    elif mode == "same_url":
        doc["pages"][1]["url"] = doc["pages"][0]["url"]
    elif mode == "existing_trading_name":
        doc["business"]["trading_name"] = "Recorded name"
    elif mode == "tampered_bytes":
        (captures / doc["pages"][0]["path"]).write_text("tampered")
    elif mode == "external_capture":
        doc["pages"][0]["path"] = "../outside.capture"
    elif mode == "domain_mismatch":
        doc["pages"][0]["url"] = "https://different.co.nz/"
    else:
        path = captures / doc["pages"][1]["path"]
        raw = path.read_bytes().replace(b"Sample Services", b"Other Services")
        digest = hashlib.sha256(raw).hexdigest()
        new_path = path.parent / (digest + ".capture")
        new_path.write_bytes(raw)
        doc["pages"][1].update(sha256=digest, path=str(new_path.relative_to(captures)))
    write_json(case_path, doc)
    result = build_identity_review(captures)
    assert result["cases"][0]["status"] != "PROPOSAL_READY_FOR_REVIEW"
    assert result["cases"][0].get("proposed_trading_name") is None


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "https://localhost/",
        "https://user:password@sample.co.nz/",
        "https://sample.co.nz:8080/",
        "https://sample.test/",
        "file:///etc/passwd",
    ],
)
def test_identity_rejects_nonpublic_domain_inputs(contact_fixture, url):
    captures, _, _, _, _, path, doc = contact_fixture
    doc["business"]["public_website"] = url
    write_json(path, doc)
    assert build_identity_review(captures)["cases"][0]["status"] == "INVALID_EVIDENCE"


def test_contact_comparison_never_grants_release_or_send(contact_fixture):
    captures, frame, dataset, review, *_ = contact_fixture
    result = compare_contact_review(frame, captures, review, dataset)
    assert result["counts"]["true_positive"] == 1
    assert result["reviewed_selection_precision"] == 1
    assert result["precision_95pct_wilson_interval"][0] < 0.21
    for key in (
        "production_approved",
        "release_receipt_created",
        "outreach_permission_granted",
        "canonical_database_changed",
    ):
        assert result[key] is False
    assert result["external_sends"] == 0


def test_contact_unresolved_selection_is_not_scored_as_correct(contact_fixture):
    captures, frame, dataset, review, labels, *_ = contact_fixture
    labels["cases"][0].update(
        identity_label="UNRESOLVED",
        publicly_attributable_emails="",
        no_email_or_unresolved_reason="Cannot confirm",
    )
    write_json(review, labels)
    result = compare_contact_review(frame, captures, review, dataset)
    assert result["counts"]["selected_unresolved"] == 1
    assert result["reviewed_selection_precision"] is None
    assert result["status"] == "REVIEW_INCOMPLETE_POLICY_UNCHANGED"


@pytest.mark.parametrize("mode", ["wrong_business", "different_email"])
def test_contact_wrong_attribution_is_false_positive(contact_fixture, mode):
    captures, frame, dataset, review, labels, *_ = contact_fixture
    if mode == "wrong_business":
        labels["cases"][0].update(
            identity_label="WRONG_BUSINESS",
            no_email_or_unresolved_reason="Wrong synthetic identity",
        )
    else:
        labels["cases"][0]["publicly_attributable_emails"] = "other@sample.co.nz"
    write_json(review, labels)
    result = compare_contact_review(frame, captures, review, dataset)
    assert result["counts"]["false_positive"] == 1
    assert result["reviewed_selection_precision"] == 0


@pytest.mark.parametrize(
    "mode",
    [
        "no_attestation",
        "frame_hash",
        "dataset_hash",
        "missing_case",
        "duplicate_case",
        "no_references",
        "no_name",
        "invalid_email",
        "prediction_changed",
        "captured_bytes_changed",
    ],
)
def test_contact_comparison_rejects_invalid_or_unbound_review(contact_fixture, mode):
    captures, frame, dataset, review, labels, case_path, doc = contact_fixture
    if mode == "no_attestation":
        labels["independent_human_review_attested"] = False
    elif mode == "frame_hash":
        labels["frame_sha256"] = "0" * 64
    elif mode == "dataset_hash":
        labels["frozen_dataset_sha256"] = "0" * 64
    elif mode == "missing_case":
        labels["cases"] = []
    elif mode == "duplicate_case":
        labels["cases"] *= 2
    elif mode == "no_references":
        labels["cases"][0]["evidence_references"] = ""
    elif mode == "no_name":
        labels["cases"][0]["confirmed_business_name"] = ""
    elif mode == "invalid_email":
        labels["cases"][0]["publicly_attributable_emails"] = "not-an-email"
    elif mode == "prediction_changed":
        doc["result"]["selected"]["email"] = "changed@sample.co.nz"
        write_json(case_path, doc)
    elif mode == "captured_bytes_changed":
        (captures / doc["pages"][0]["path"]).write_text("changed")
    write_json(review, labels)
    with pytest.raises(ValueError):
        compare_contact_review(frame, captures, review, dataset)


@pytest.mark.parametrize(
    "data",
    [
        {
            "@context": "https://schema.org",
            "@graph": [{"@type": "LocalBusiness", "name": "Sample"}],
        },
        {"@graph": {"@id": "urn:sample"}},
        [{"@type": "Organization"}, {"@id": "urn:reference"}],
        {"@value": "value"},
    ],
)
def test_metadata_valid_graph_container_has_no_missing_outer_type(data):
    findings, _ = analyse_html(
        '<script type="application/ld+json">' + json.dumps(data) + "</script>",
        "https://sample.co.nz/",
        {},
    )
    assert not findings


def test_metadata_untyped_entity_is_heuristic_not_verified_syntax_error():
    findings, _ = analyse_html(
        '<script type="application/ld+json">{"name":"Sample"}</script>', "https://sample.co.nz/", {}
    )
    assert findings[0].defect_key == "structured_data_missing_type"
    assert findings[0].confidence == "heuristic"


@pytest.mark.parametrize(
    "raw,key",
    [
        ("{bad", "structured_data_invalid_json"),
        ('{"@graph":42}', "structured_data_invalid_graph_shape"),
        ("42", "structured_data_not_dict_or_list"),
    ],
)
def test_metadata_actual_invalid_json_or_shape_is_retained(raw, key):
    findings, _ = analyse_html(
        '<script type="application/ld+json">' + raw + "</script>", "https://sample.co.nz/", {}
    )
    assert key in [f.defect_key for f in findings]


@pytest.fixture
def site_fixture(tmp_path):
    source = tmp_path / "site"
    source.mkdir()
    page = source / "index.html"
    page.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Original sample</title><meta name="viewport" content="width=device-width,maximum-scale=1,user-scalable=no"></head><body><main><h1>Sample</h1></main></body></html>'
    )
    plan = {
        "schema_version": 1,
        "edits": [
            {
                "path": "index.html",
                "expected_sha256": hashlib.sha256(page.read_bytes()).hexdigest(),
                "replacements": [
                    {"old": "Original sample", "new": "Patched sample", "expected_count": 1}
                ],
            }
        ],
    }
    return source, plan, tmp_path / "comparison"


@pytest.mark.parametrize(
    "mode",
    [
        "hash",
        "occurrences",
        "escape",
        "hidden",
        "duplicate_edit",
        "empty_edits",
        "existing_output",
        "source_symlink",
        "script",
        "event_handler",
        "iframe",
        "refresh",
    ],
)
def test_implementation_rejects_mismatched_or_unsafe_source(site_fixture, mode):
    source, plan, output = site_fixture
    if mode == "hash":
        plan["edits"][0]["expected_sha256"] = "0" * 64
    elif mode == "occurrences":
        plan["edits"][0]["replacements"][0]["expected_count"] = 2
    elif mode == "escape":
        plan["edits"][0]["path"] = "../index.html"
    elif mode == "hidden":
        plan["edits"][0]["path"] = ".env"
    elif mode == "duplicate_edit":
        plan["edits"].append(copy.deepcopy(plan["edits"][0]))
    elif mode == "empty_edits":
        plan["edits"] = []
    elif mode == "existing_output":
        output.mkdir()
    elif mode == "source_symlink":
        (source / "linked.html").symlink_to(source / "index.html")
    else:
        extra = {
            "script": "<script>alert(1)</script>",
            "event_handler": '<p onclick="alert(1)">x</p>',
            "iframe": '<iframe src="https://sample.co.nz/"></iframe>',
            "refresh": '<meta http-equiv="refresh" content="0;url=https://sample.co.nz">',
        }[mode]
        page = source / "index.html"
        page.write_text(page.read_text() + extra)
        plan["edits"][0]["expected_sha256"] = hashlib.sha256(page.read_bytes()).hexdigest()
    original = (source / "index.html").read_bytes()
    with pytest.raises(ValueError):
        build_implementation_demo(source, plan, output)
    assert (source / "index.html").read_bytes() == original
    assert not output.exists() or mode == "existing_output"


def fake_report(url, options, count, severity="medium"):
    run_dir = options.output_root / (
        str(count) + "-" + str(len(list(options.output_root.glob("*"))))
    )
    run_dir.mkdir(parents=True)
    report = {
        "run_id": run_dir.name,
        "url": url,
        "profile": "rendered",
        "status": "complete",
        "defect_count": count,
        "coverage": {"required": 1, "passed": 1},
        "defects": [
            {"defect_key": "finding-" + str(i), "selector": "#item-" + str(i), "severity": severity}
            for i in range(count)
        ],
        "artifacts": {"json": str(run_dir / "report.json")},
        "manifest": {},
    }
    write_json(run_dir / "report.json", report)
    return report


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("improved", "LOCAL_IMPROVEMENT_OBSERVED"),
        ("new_finding", "REVIEW_REQUIRED"),
        ("partial", "REVIEW_REQUIRED"),
    ],
)
def test_implementation_compare_does_not_promote_or_claim_live_site(
    site_fixture, monkeypatch, mode, expected
):
    source, plan, output = site_fixture
    calls = []

    def audit(url, options):
        calls.append(url)
        result = fake_report(url, options, 2 if len(calls) == 1 else 1)
        if len(calls) == 2 and mode == "new_finding":
            result["defects"].append({"defect_key": "new", "selector": "#new", "severity": "high"})
        if len(calls) == 2 and mode == "partial":
            result["status"] = "partial"
        write_json(Path(result["artifacts"]["json"]), result)
        return result

    monkeypatch.setattr("auditor_toolkit.implementation_demo.run_audit", audit)
    original = (source / "index.html").read_bytes()
    result = build_implementation_demo(source, plan, output)
    assert result["status"] == expected
    assert len(calls) == 2 and calls[0] == calls[1]
    assert result["source_unchanged"] and result["local_server_closed"]
    assert not result["production_changed"] and not result["external_deploy"]
    assert (source / "index.html").read_bytes() == original
    assert "Patched sample" in (output / "after/index.html").read_text()
    assert "Original sample" in (output / "before/index.html").read_text()


def test_implementation_closes_owned_server_after_audit_failure(site_fixture, monkeypatch):
    source, plan, output = site_fixture

    def fail(url, options):
        raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr("auditor_toolkit.implementation_demo.run_audit", fail)
    with pytest.raises(RuntimeError):
        build_implementation_demo(source, plan, output)
    result = json.loads((output / "implementation-demo.json").read_text())
    assert result["status"] == "INCOMPLETE" and result["local_server_closed"]
    address = urlsplit(result["audit_url"])
    with pytest.raises(OSError):
        socket.create_connection((address.hostname, address.port), timeout=0.2)


def test_implementation_real_rendered_pair_preserves_mobile_evidence(site_fixture):
    source, plan, output = site_fixture
    plan["edits"][0]["replacements"].append(
        {
            "old": "width=device-width,maximum-scale=1,user-scalable=no",
            "new": "width=device-width,initial-scale=1",
            "expected_count": 1,
        }
    )
    result = build_implementation_demo(source, plan, output)
    assert result["status"] == "LOCAL_IMPROVEMENT_OBSERVED"
    assert any(item["defect_key"] == "axe-meta-viewport" for item in result["removed_findings"])
    for side in ("before", "after"):
        assert result[side]["status"] == "complete"
        assert result[side]["coverage"]["passed"] == result[side]["coverage"]["required"]
        for shot in result[side]["screenshots"].values():
            assert hashlib.sha256(Path(shot["path"]).read_bytes()).hexdigest() == shot["sha256"]
    assert result["source_unchanged"] and result["local_server_closed"]


@pytest.mark.parametrize("replacement", [None, "bad", 42])
def test_implementation_malformed_replacement_fails_with_clear_validation(
    site_fixture, replacement
):
    source, plan, output = site_fixture
    plan["edits"][0]["replacements"] = [replacement]
    with pytest.raises(ValueError, match="Replacement"):
        build_implementation_demo(source, plan, output)
    assert not output.exists()


def test_implementation_rejects_non_html_entrypoint(site_fixture):
    source, plan, output = site_fixture
    (source / "active.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    )
    with pytest.raises(ValueError, match="HTML"):
        build_implementation_demo(source, plan, output, entrypoint="active.svg")
    assert not output.exists()


def test_implementation_severity_regression_is_not_success(site_fixture, monkeypatch):
    source, plan, output = site_fixture
    calls = []

    def audit(url, options):
        calls.append(url)
        result = fake_report(url, options, 2 if len(calls) == 1 else 1)
        if len(calls) == 2:
            result["defects"][0]["severity"] = "critical"
            write_json(Path(result["artifacts"]["json"]), result)
        return result

    monkeypatch.setattr("auditor_toolkit.implementation_demo.run_audit", audit)
    result = build_implementation_demo(source, plan, output)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["worsened_findings"]


def test_implementation_blocks_wrong_host_and_form_post(site_fixture, monkeypatch):
    import urllib.error
    import urllib.request

    source, plan, output = site_fixture
    calls = []

    def audit(url, options):
        calls.append(url)
        with urllib.request.urlopen(url, timeout=2) as response:
            assert response.status == 200
            assert "connect-src 'none'" in response.headers["Content-Security-Policy"]
        for request in (
            urllib.request.Request(url, headers={"Host": "foreign.example"}),
            urllib.request.Request(url, data=b"no-form-send"),
        ):
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=2)
            assert error.value.code in (403, 501)
        return fake_report(url, options, 2 if len(calls) == 1 else 1)

    monkeypatch.setattr("auditor_toolkit.implementation_demo.run_audit", audit)
    assert build_implementation_demo(source, plan, output)["local_server_closed"]


def test_implementation_does_not_copy_hidden_credentials(site_fixture, monkeypatch):
    source, plan, output = site_fixture
    (source / ".env").write_text("SYNTHETIC_PLACEHOLDER_ONLY=true")
    calls = []

    def audit(url, options):
        calls.append(url)
        return fake_report(url, options, 2 if len(calls) == 1 else 1)

    monkeypatch.setattr("auditor_toolkit.implementation_demo.run_audit", audit)
    build_implementation_demo(source, plan, output)
    assert not (output / "before/.env").exists()
    assert not (output / "after/.env").exists()


@pytest.mark.parametrize(
    "command", ["identity-review", "implementation-demo", "freeze-contact-review"]
)
def test_candidate_cli_rejects_paths_outside_workspace(tmp_path, monkeypatch, command):
    from auditor_toolkit.cli import main

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(workspace)
    if command == "identity-review":
        args = [command, str(outside), "--output", "result.json"]
    elif command == "implementation-demo":
        args = [command, str(outside), "plan.json", "--output-dir", "demo"]
    else:
        args = [command, str(outside / "frame.json"), str(outside), "--output", "result.json"]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert not list(workspace.iterdir())


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("less_severe", "LOCAL_IMPROVEMENT_OBSERVED"),
        ("different_profile", "REVIEW_REQUIRED"),
        ("different_url", "REVIEW_REQUIRED"),
    ],
)
def test_implementation_handles_reduced_severity_and_requires_matching_scope(
    site_fixture, monkeypatch, mode, expected
):
    source, plan, output = site_fixture
    calls = []

    def audit(url, options):
        calls.append(url)
        result = fake_report(url, options, 1)
        if len(calls) == 2:
            if mode == "less_severe":
                result["defects"][0]["severity"] = "low"
            if mode == "different_profile":
                result["profile"] = "static"
            if mode == "different_url":
                result["url"] = url + "other"
        else:
            result["defects"][0]["severity"] = "high"
        write_json(Path(result["artifacts"]["json"]), result)
        return result

    monkeypatch.setattr("auditor_toolkit.implementation_demo.run_audit", audit)
    result = build_implementation_demo(source, plan, output)
    assert result["status"] == expected
    if mode == "less_severe":
        assert result["improved_findings"]
        assert (
            not result["removed_findings"]
            and not result["new_findings"]
            and not result["worsened_findings"]
        )
