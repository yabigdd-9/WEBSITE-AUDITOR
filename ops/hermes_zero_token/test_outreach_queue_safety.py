"""Approval preservation and idempotency on disposable YAML queues."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def draft(tmp_path, monkeypatch):
    specification = importlib.util.spec_from_file_location(
        "synthetic_outreach", Path(__file__).with_name("outreach_draft.py")
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    monkeypatch.setattr(module, "APPROVAL_QUEUE_PATH", tmp_path / "approval.yaml")
    monkeypatch.setattr(module, "DRAFTS_DIR", tmp_path / "drafts")
    return module


def details(business_id=1):
    return [{"business_id": business_id, "name": "Synthetic fixture", "evidence_id": 7,
             "draft_sha256": "f" * 64, "draft_path": "/fixture/draft.md"}]


def test_preserves_unrelated_fields_and_approved_items(draft):
    existing = {"policy": {"limit": 10}, "items": [{"id": "other", "status": "APPROVED"}],
                "requires_dion_approval": [{"id": "existing", "status": "APPROVED"}],
                "owner_notes": "preserve"}
    draft.APPROVAL_QUEUE_PATH.write_text(yaml.safe_dump(existing))
    draft.append_review_items(details())
    result = yaml.safe_load(draft.APPROVAL_QUEUE_PATH.read_text())
    for key in ("policy", "items", "owner_notes"):
        assert result[key] == existing[key]
    assert result["requires_dion_approval"][0] == existing["requires_dion_approval"][0]
    assert result["requires_dion_approval"][1]["status"] == "NOT_SENT_AWAITING_APPROVAL"


def test_same_content_never_duplicates_or_resets_approval(draft):
    draft.append_review_items(details())
    queue = yaml.safe_load(draft.APPROVAL_QUEUE_PATH.read_text())
    queue["requires_dion_approval"][0]["status"] = "REJECTED_BY_OWNER"
    draft.APPROVAL_QUEUE_PATH.write_text(yaml.safe_dump(queue))
    draft.append_review_items(details())
    result = yaml.safe_load(draft.APPROVAL_QUEUE_PATH.read_text())
    assert len(result["requires_dion_approval"]) == 1
    assert result["requires_dion_approval"][0]["status"] == "REJECTED_BY_OWNER"


@pytest.mark.parametrize("content", ["[unrelated]\n", "requires_dion_approval: invalid\n",
                                     "requires_dion_approval: [invalid]\n", "invalid: [\n"])
def test_invalid_queue_fails_without_overwriting(draft, content):
    draft.APPROVAL_QUEUE_PATH.write_text(content)
    with pytest.raises((ValueError, yaml.YAMLError)):
        draft.append_review_items(details())
    assert draft.APPROVAL_QUEUE_PATH.read_text() == content


def test_empty_batch_leaves_existing_queue_byte_identical(draft):
    original = "# owner note\nitems: []\n"
    draft.APPROVAL_QUEUE_PATH.write_text(original)
    draft.append_review_items([])
    assert draft.APPROVAL_QUEUE_PATH.read_text() == original


def test_repeated_worker_runs_reuse_exact_draft_and_approval(draft, monkeypatch):
    business = {"business_id": 1, "name": "Synthetic fixture", "evidence_id": 7,
                "public_website": "https://fixture.example", "observation": "Fixture only"}
    monkeypatch.setattr(draft, "get_businesses_with_evidence", lambda limit: [business])
    assert draft.main() == 0
    assert draft.main() == 0
    assert len(list(draft.DRAFTS_DIR.glob("business-*.md"))) == 1
    queue = yaml.safe_load(draft.APPROVAL_QUEUE_PATH.read_text())
    assert len(queue["requires_dion_approval"]) == 1


def test_concurrent_queue_updates_preserve_all_items(draft, tmp_path):
    code = (
        "import importlib.util,json,pathlib,sys;"
        "spec=importlib.util.spec_from_file_location('draft',sys.argv[1]);"
        "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);"
        "module.APPROVAL_QUEUE_PATH=pathlib.Path(sys.argv[2]);"
        "module.append_review_items(json.loads(sys.argv[3]))"
    )
    processes = [subprocess.Popen(
        [sys.executable, "-c", code, str(Path(draft.__file__).resolve()),
         str(draft.APPROVAL_QUEUE_PATH), json.dumps(details(business_id))]
    ) for business_id in range(4)]
    try:
        for process in processes:
            assert process.wait(timeout=10) == 0
        queue = yaml.safe_load(draft.APPROVAL_QUEUE_PATH.read_text())
        assert len(queue["requires_dion_approval"]) == 4
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
