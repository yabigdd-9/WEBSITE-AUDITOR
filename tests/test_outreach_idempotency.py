import hashlib
import importlib.util
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def worker(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "idempotency_candidate",
        Path(__file__).resolve().parents[1] / "ops/hermes_zero_token/outreach_draft.py",
    )
    module = importlib.util.module_from_spec(spec)
    cwd = Path.cwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
    state = tmp_path / "state"
    monkeypatch.setattr(module, "DRAFTS_DIR", state / "drafts")
    monkeypatch.setattr(module, "APPROVAL_QUEUE_PATH", state / "queue.yaml")
    monkeypatch.setattr(module, "LEGACY_APPROVAL_QUEUE_PATH", tmp_path / "absent.yaml")
    business = {
        "business_id": 1,
        "evidence_id": 2,
        "name": "Synthetic",
        "public_website": "https://example.invalid",
        "observation": "Synthetic finding",
    }
    monkeypatch.setattr(module, "get_businesses_with_evidence", lambda limit: [dict(business)])
    return module, business


def queue(module):
    return yaml.safe_load(module.APPROVAL_QUEUE_PATH.read_text())


def seed(module, items):
    module.APPROVAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    module.APPROVAL_QUEUE_PATH.write_text(
        yaml.safe_dump({"owner_note": "keep", "requires_dion_approval": items})
    )


def test_repeated_worker_preserves_queue_bytes_and_draft(worker, capsys):
    module, _ = worker
    assert module.main() == 0
    first = json.loads(capsys.readouterr().out)
    draft = Path(first["details"][0]["draft_path"])
    before = draft.read_bytes()
    queue_before = module.APPROVAL_QUEUE_PATH.read_bytes()
    assert module.main() == 0
    second = json.loads(capsys.readouterr().out)
    assert second["drafts_created"] == 0
    assert second["existing_reviews_preserved"] == 1
    assert len(queue(module)["requires_dion_approval"]) == 1
    assert module.APPROVAL_QUEUE_PATH.read_bytes() == queue_before
    assert draft.read_bytes() == before
    assert stat.S_IMODE(draft.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "status", ["REJECTED", "REVOKED", "SUPPRESSED", "APPROVED", "NOT_SENT_AWAITING_APPROVAL"]
)
def test_existing_decision_and_human_edited_draft_never_reopened(worker, capsys, status):
    module, business = worker
    seed(
        module,
        [
            {
                "id": "APR-ZT-1",
                "status": status,
                "human_note": "keep this decision",
                "draft_path": "human-edit.md",
            }
        ],
    )
    before = module.APPROVAL_QUEUE_PATH.read_bytes()
    business["observation"] = "Changed evidence does not reopen decision"
    module.main()
    report = json.loads(capsys.readouterr().out)
    assert report["drafts_created"] == 0
    assert module.APPROVAL_QUEUE_PATH.read_bytes() == before
    assert not list(module.DRAFTS_DIR.glob("*.md"))


def test_multiple_evidence_rows_for_one_business_create_one_request(worker, monkeypatch, capsys):
    module, business = worker
    monkeypatch.setattr(
        module,
        "get_businesses_with_evidence",
        lambda limit: [business, dict(business, evidence_id=3)],
    )
    module.main()
    capsys.readouterr()
    assert len(queue(module)["requires_dion_approval"]) == 1
    assert len(list(module.DRAFTS_DIR.glob("*.md"))) == 1


def test_concurrent_same_business_does_not_duplicate_requests(worker, capsys):
    module, _ = worker
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(lambda _: module.main(), range(2))) == [0, 0]
    capsys.readouterr()
    assert len(queue(module)["requires_dion_approval"]) == 1
    assert len(list(module.DRAFTS_DIR.glob("*.md"))) == 1


def test_orphan_from_prepublication_crash_is_reused_without_overwrite(worker, capsys):
    module, business = worker
    module.DRAFTS_DIR.mkdir(parents=True)
    body = module.draft_body(business)
    digest = hashlib.sha256(body.encode()).hexdigest()
    draft = module.DRAFTS_DIR / f"business-1-evidence-2-{digest}.md"
    draft.write_text(body)
    before = draft.stat().st_mtime_ns
    module.main()
    result = json.loads(capsys.readouterr().out)
    assert result["drafts_created"] == 0
    assert draft.stat().st_mtime_ns == before
    assert len(queue(module)["requires_dion_approval"]) == 1


def test_changed_orphan_is_preserved_and_queue_not_published(worker):
    module, business = worker
    module.DRAFTS_DIR.mkdir(parents=True)
    digest = hashlib.sha256(module.draft_body(business).encode()).hexdigest()
    draft = module.DRAFTS_DIR / f"business-1-evidence-2-{digest}.md"
    draft.write_text("Human-edited orphan")
    with pytest.raises(ValueError, match="does not match"):
        module.main()
    assert draft.read_text() == "Human-edited orphan"
    assert not module.APPROVAL_QUEUE_PATH.exists()


def test_malformed_queue_item_fails_before_draft_creation(worker):
    module, _ = worker
    seed(module, [None])
    before = module.APPROVAL_QUEUE_PATH.read_bytes()
    with pytest.raises(ValueError, match="identities"):
        module.main()
    assert module.APPROVAL_QUEUE_PATH.read_bytes() == before
    assert not list(module.DRAFTS_DIR.glob("*.md"))
