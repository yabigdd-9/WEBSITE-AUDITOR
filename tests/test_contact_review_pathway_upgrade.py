"""Offline tests for safer replay, publication predicates and operator reports."""
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "money-machine"))
import mm_contact_review_pathway as pathway  # noqa: E402


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network, database, model or process operation")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setitem(sys.modules, "mm_model_router", SimpleNamespace(local_complete=forbidden))
    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    monkeypatch.setenv("MM_EXTERNAL_SEND_DISABLED", "1")
    original = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(original)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def business():
    return {"id": "business-1", "live_business_id": 1, "name": "Clear Plumbing",
            "region": "Auckland", "public_website": "https://clearplumbing.nz/",
            "pipeline_state_at_freeze": "NEEDS_REVIEW"}


def meta(raw, *, url="https://clearplumbing.nz/contact", path="page.html"):
    return {"url": url, "requested_url": url, "path": path,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(raw).hexdigest(), "content_type": "text/html"}


def row(b=None, *, supported=True):
    b = b or business()
    return {"case_id": b["id"], "live_business_id": b["live_business_id"], "company": b["name"],
            "identity": {"reasons": [], "name_suggestions": []},
            "verifier": {"selected": {"email": "info@clearplumbing.nz"} if supported else None},
            "proofer": {"checks": {}, "sources": []},
            "judge": {"route": "MACHINE_SUPPORTED_RECOMMENDATION" if supported else "CONTACT_EXCEPTION",
                      "reason": "Synthetic evidence", "next_worker": "JUDGE",
                      "pipeline_state_at_capture": "NEEDS_REVIEW"}}


def packet(tmp_path, *, engines=None, raw=None, cover_raw=True):
    folder = tmp_path / "packet"
    b = business()
    pages = []
    files = []
    if raw is not None:
        capture = folder / "evidence/page.html"
        capture.parent.mkdir(parents=True)
        capture.write_bytes(raw)
        pages = [meta(raw)]
        if cover_raw:
            files.append(capture)
    doc = {"business": b, "pages": pages, "dns": {}, "errors": []}
    files.append(write_json(folder / "evidence/cases/business-1.json", doc))
    frame = {"application_revision": "historical-revision", "cases": [b],
             "engine_hashes": pathway.current_engine_hashes() if engines is None else engines}
    sample = write_json(folder / "sample.json", frame)
    files.append(sample)
    (folder / "FRAME_SHA256.txt").write_text(pathway.digest(sample.read_bytes()))
    write_json(folder / "PACKET_MANIFEST.json", {"files": {
        str(path.relative_to(folder)): {"sha256": pathway.digest(path.read_bytes())} for path in files}})
    return folder


@pytest.mark.parametrize("status", ["REVIEW_ERROR", "INCOMPLETE", "STALE_LIVE_STATE"])
def test_report_includes_attempt_errors_without_success_row(status):
    rendered = pathway.report_html({"cases": 0}, [], [{"business_id": 1, "company": "Held business",
                                                       "status": status, "error": "<script>unsafe</script>"}])
    assert "1 cases attempted" in rendered
    assert "0 supported recommendations" in rendered
    assert "1 exceptions" in rendered
    assert "Held business" in rendered
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in rendered
    assert 'data-supported="true"' not in rendered


@pytest.mark.parametrize("status", ["REVIEW_ERROR", "INCOMPLETE", "STALE_LIVE_STATE"])
def test_report_never_counts_historical_supported_row_with_held_outcome(status):
    rendered = pathway.report_html({}, [row()], [{"business_id": 1, "status": status}])
    assert "0 supported recommendations" in rendered
    assert 'data-supported="true"' not in rendered
    assert "Captured evidence is retained" in rendered


def test_report_counts_mixed_attempts_and_preserves_two_argument_call():
    rendered = pathway.report_html({}, [row()], [{"business_id": 1, "status": "COMPLETE"},
                                                 {"business_id": 2, "status": "REVIEW_ERROR"},
                                                 {"business_id": 3, "status": "INCOMPLETE"}])
    assert "3 cases attempted" in rendered
    assert "1 completed" in rendered
    assert "1 errors" in rendered
    assert "1 incomplete" in rendered
    assert "1 supported recommendations" in rendered
    assert "2 exceptions" in rendered
    assert rendered.count("<details ") == 3
    assert "1 supported recommendations" in pathway.report_html({}, [row()])


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,unsafe", "https://user:secret@example.nz/", "https://[broken"])
def test_report_never_turns_unsafe_capture_urls_into_clickable_links(url):
    value = row()
    value["proofer"]["sources"] = [{"source_url": url, "capture_sha256": "synthetic"}]
    rendered = pathway.report_html({}, [value])
    assert "<a href=" not in rendered


@pytest.mark.parametrize("style", ["display:none", " DISPLAY : NONE !important ;", "visibility:hidden",
                                    "padding:0; visibility:collapse; color:red", "/* hidden */display:none"])
def test_inline_hidden_contact_and_heading_rejected_in_parser_and_proofer(style):
    raw = f'<div style="{style}"><h1>Hidden Company</h1><a href="mailto:info@clearplumbing.nz">Email</a></div>'.encode()
    assert pathway.publication_proof(meta(raw), raw, "info@clearplumbing.nz") is None
    parsed = pathway.verifier.parse_page(meta(raw), raw)
    assert parsed["observations"] == []
    assert parsed["headings"] == []


@pytest.mark.parametrize("raw", [b'<style>.hidden{display:none}</style><p>info@clearplumbing.nz</p>',
                                  b'<link rel="stylesheet" href="/site.css"><p>info@clearplumbing.nz</p>',
                                  b'<p class="hidden">info@clearplumbing.nz</p>',
                                  b'<p style="opacity:0">info@clearplumbing.nz</p>',
                                  b'<div id="contact"><p>info@clearplumbing.nz</p></div>',
                                  b'<title>info@clearplumbing.nz</title>',
                                  b'<!-- info@clearplumbing.nz -->'])
def test_css_dependent_text_title_and_comments_cannot_claim_visible_publication(raw):
    assert pathway.publication_proof(meta(raw), raw, "info@clearplumbing.nz") is None


def test_css_dependent_mailto_cannot_establish_publication_proof():
    raw = b'<style>.styled{color:blue}</style><a class="styled" href="mailto:info%40clearplumbing.nz">Email</a><p>info@clearplumbing.nz</p>'
    assert pathway.publication_proof(meta(raw), raw, "info@clearplumbing.nz") is None


def test_class_dependent_mailto_cannot_establish_publication_proof():
    raw = b'<a class="unknown-style" href="mailto:info@clearplumbing.nz">Email</a>'
    assert pathway.publication_proof(meta(raw), raw, "info@clearplumbing.nz") is None


def test_plain_markup_can_establish_publication_without_css_uncertainty():
    raw = b'<a href="mailto:info@clearplumbing.nz">Email</a>'
    proof = pathway.publication_proof(meta(raw), raw, "info@clearplumbing.nz")
    assert proof["mailto"]
    assert not proof["css_visibility_uncertain"]


@pytest.mark.parametrize("engines", [{}, {pathway.REQUIRED_ENGINE_FILES[0]: "partial"}])
def test_frozen_replay_rejects_empty_or_partial_engine_coverage(tmp_path, engines):
    source = packet(tmp_path, engines=engines)
    with pytest.raises(ValueError, match="required source/configuration coverage"):
        pathway.run(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_frozen_replay_rejects_covered_source_mismatch(tmp_path):
    engines = pathway.current_engine_hashes()
    engines[pathway.REQUIRED_ENGINE_FILES[0]] = "0" * 64
    source = packet(tmp_path, engines=engines)
    with pytest.raises(ValueError, match="engine/configuration changed"):
        pathway.run(source, tmp_path / "output")


@pytest.mark.parametrize("mode", ["frozen", "reevaluate"])
def test_replay_preserves_inputs_and_records_current_engine_snapshot(tmp_path, mode):
    source = packet(tmp_path, engines={} if mode == "reevaluate" else None)
    before = {str(path.relative_to(source)): pathway.digest(path.read_bytes()) for path in source.rglob("*") if path.is_file()}
    output = tmp_path / "output"
    summary = pathway.run(source, output, mode=mode)
    assert summary["evaluation_mode"] == mode
    assert summary["historical_input_revision"] == "historical-revision"
    assert summary["historical_revision_acceptance"] is False
    assert summary["frozen_engine_fingerprints_verified"] == (mode == "frozen")
    assert summary["frozen_application_revision"] == ("historical-revision" if mode == "frozen" else None)
    assert set(pathway.REQUIRED_ENGINE_FILES) <= summary["current_engine_sha256"].keys()
    assert (output / "ENGINE_SNAPSHOT.json").exists()
    assert (output / "MANIFEST.json").exists()
    report = (output / "REVIEW.html").read_text()
    assert ("does not accept the historical application revision" in report) == (mode == "reevaluate")
    assert summary["external_sends"] == summary["paid_ai_cost"] == summary["pipeline_writes"] == summary["model_calls"] == 0
    assert before == {str(path.relative_to(source)): pathway.digest(path.read_bytes()) for path in source.rglob("*") if path.is_file()}


@pytest.mark.parametrize("mode", ["frozen", "reevaluate"])
def test_replay_rejects_capture_missing_from_manifest_in_both_modes(tmp_path, mode):
    source = packet(tmp_path, raw=b"<p>Publication</p>", cover_raw=False)
    with pytest.raises(ValueError, match="manifest does not cover the raw capture"):
        pathway.run(source, tmp_path / "output", mode=mode)
    assert not (tmp_path / "output/MANIFEST.json").exists()


@pytest.mark.parametrize("mode", ["frozen", "reevaluate"])
def test_replay_rejects_tampered_evidence_in_both_modes(tmp_path, mode):
    source = packet(tmp_path, raw=b"<p>Publication</p>")
    (source / "evidence/page.html").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="manifest mismatch"):
        pathway.run(source, tmp_path / "output", mode=mode)


@pytest.mark.parametrize("mode", ["frozen", "reevaluate"])
def test_replay_detects_manifest_mutation_during_evaluation(tmp_path, monkeypatch, mode):
    source = packet(tmp_path)
    def mutate(*args, **kwargs):
        (source / "PACKET_MANIFEST.json").write_text("changed")
        return "synthetic report"
    monkeypatch.setattr(pathway, "report_html", mutate)
    with pytest.raises(ValueError, match="manifest or frame marker changed"):
        pathway.run(source, tmp_path / "output", mode=mode)
    assert not (tmp_path / "output/MANIFEST.json").exists()


@pytest.mark.parametrize("mode", ["frozen", "reevaluate"])
def test_replay_detects_current_engine_mutation_before_completion(tmp_path, monkeypatch, mode):
    source = packet(tmp_path)
    original = pathway.read_limited
    mutated = False
    def report(*args, **kwargs):
        nonlocal mutated
        mutated = True
        return "synthetic report"
    def read(path):
        data = original(path)
        return data + b"changed" if mutated and path == REPO / pathway.REQUIRED_ENGINE_FILES[0] else data
    monkeypatch.setattr(pathway, "report_html", report)
    monkeypatch.setattr(pathway, "read_limited", read)
    with pytest.raises(ValueError, match="Evaluation engine changed"):
        pathway.run(source, tmp_path / "output", mode=mode)
    assert not (tmp_path / "output/MANIFEST.json").exists()


@pytest.mark.parametrize("route", ["evidence", "identity", "contact", "proof", "supported"])
def test_judge_returns_fixed_actionable_requirements_without_release_authority(route):
    doc = {"business": business(), "pages": [] if route == "evidence" else [{}]}
    result = {"identity": {"status": "AMBIGUOUS" if route == "identity" else "HIGH"},
              "selected": None if route in {"identity", "contact", "evidence"} else {"email": "info@clearplumbing.nz"}}
    proof = {"passed": route == "supported", "checks": {"exact_publication_reconfirmed": route == "supported"}}
    assignment = pathway.judge_worker(doc, result, proof)
    assert assignment["next_worker"] in pathway.WORKERS
    assert assignment["reason_codes"]
    assert assignment["required_evidence"]
    assert assignment["permitted_action"]
    assert assignment["pipeline_action"] == "NONE"
    assert assignment["outreach_eligible"] is False
    assert assignment["human_precision_label"] is None
    assert assignment["precision_release_authority"] is False
    assert bool(assignment["blocking_checks"]) == (route != "supported")


def test_identity_candidate_requires_unique_name_and_all_identity_gates(monkeypatch, tmp_path):
    b = business()
    suggestion = {"name": "Clear Plumbing NZ", "source_urls": [b["public_website"]]}
    first = {"identity": {"name_suggestions": [suggestion]}}
    rerun = {"verifier": {"identity": {"status": "HIGH", "reasons": [],
                                       "weighted_confidence": {"conflicts": []}}},
             "proofer": {"passed": False}, "judge": {"outreach_eligible": False}}
    calls = []
    def review(proposed, doc, packet_path, at):
        calls.append(proposed)
        return first if len(calls) == 1 else rerun
    monkeypatch.setattr(pathway, "review_case", review)
    proposal = pathway.validated_identity_candidate(b, {"business": b}, tmp_path, datetime.now(timezone.utc))
    assert proposal["business"]["name"] == suggestion["name"]
    assert {key: value for key, value in proposal["business"].items() if key != "name"} == {key: value for key, value in b.items() if key != "name"}
    assert proposal["row"]["proofer"]["passed"] is False
    assert proposal["contact_approval"] is proposal["pipeline_transition_authority"] is proposal["external_send_authority"] is False
    assert b["name"] == "Clear Plumbing"


@pytest.mark.parametrize("failure", ["multiple", "ambiguous", "weighted", "conflict", "unmatched_branch", "mixed_units"])
def test_identity_candidate_rejects_ambiguous_or_conflicting_name_changes(monkeypatch, tmp_path, failure):
    suggestions = [{"name": "Clear Plumbing"}, {"name": "Other Company"}] if failure == "multiple" else [{"name": "Clear Plumbing NZ"}]
    identity = {"status": "AMBIGUOUS" if failure == "ambiguous" else "HIGH",
                "reasons": ["Location conflict"] if failure == "conflict" else [],
                "weighted_confidence": {"conflicts": ["nzbn_match"] if failure == "weighted" else []}}
    if failure in {"unmatched_branch", "mixed_units"}:
        identity.update(branch_sensitive=True, observed_branches=["auckland", "wellington"],
                        matched_branches=[] if failure == "unmatched_branch" else ["auckland"])
    calls = iter([{"identity": {"name_suggestions": suggestions}}, {"verifier": {"identity": identity}}])
    monkeypatch.setattr(pathway, "review_case", lambda *args: next(calls))
    b = business()
    assert pathway.validated_identity_candidate(b, {"business": b}, tmp_path, datetime.now(timezone.utc)) is None


def test_real_identity_correction_does_not_require_or_approve_a_contact(tmp_path):
    b = {**business(), "name": "clearplumbing.nz"}
    raw = b"<title>Clear Plumbing</title><h1>Clear Plumbing</h1><p>Clear Plumbing in Auckland</p>"
    folder = tmp_path / "captures"
    (folder / "evidence").mkdir(parents=True)
    (folder / "evidence/page.html").write_bytes(raw)
    doc = {"business": b, "pages": [meta(raw)], "dns": {}, "errors": []}
    proposal = pathway.validated_identity_candidate(b, doc, folder, datetime.now(timezone.utc))
    assert proposal["business"]["name"] == "Clear Plumbing"
    assert proposal["row"]["verifier"]["identity"]["status"] == "HIGH"
    assert proposal["row"]["verifier"]["selected"] is None
    assert proposal["row"]["judge"]["route"] == "CONTACT_EXCEPTION"
    assert proposal["contact_approval"] is False
