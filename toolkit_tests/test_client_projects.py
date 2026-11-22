import copy
import hashlib
import tempfile
from pathlib import Path

import pytest

from scripts.approval_controls import approve_proposal
from scripts.client_projects import accept_proposal, complete
from scripts.cloud_opportunities import digest
from scripts.pipeline_store import PipelineStore
from toolkit_tests.platform_helpers import commit_mutation

NOW = 1767225600
EVIDENCE = "a" * 64


@pytest.fixture
def prospect():
    body = dict(
        kind="INTERNAL_PROPOSAL_DRAFT",
        items=[dict(finding_id="fixture-1", recommendation="Agreed synthetic task")],
    )
    version = digest(body)
    return dict(
        domain="example.com",
        status="complete",
        draft="Internal scope",
        proposal_version=version,
        proposal_versions=[{**body, "version_sha256": version}],
    )


def accepted(prospect, **overrides):
    options = dict(
        actor="fixture-owner",
        reason="Verified synthetic customer acceptance",
        now=NOW,
        acceptance_evidence=EVIDENCE,
        owner_verified=True,
    )
    return accept_proposal(prospect, prospect["proposal_version"], **{**options, **overrides})


def finish(prospect, project, kind, item, proof=EVIDENCE):
    return complete(
        prospect,
        project,
        kind=kind,
        item_id=item,
        completion_evidence=proof,
        actor="fixture-owner",
        reason="Verified synthetic completion",
        now=NOW,
    )


def approve(prospect):
    approve_proposal(
        prospect,
        prospect["proposal_version"],
        actor="fixture-owner",
        reason="Scope approved",
        now=NOW,
    )


def test_acceptance_requires_exact_approval_and_explicit_customer_evidence(prospect):
    with pytest.raises(ValueError):
        accepted(prospect)
    approve(prospect)
    for changes in ({"owner_verified": False}, {"acceptance_evidence": "missing"}):
        with pytest.raises(ValueError):
            accepted(prospect, **changes)
    project = accepted(prospect)
    assert accepted(prospect) == project
    assert len(prospect["projects"]) == 1
    assert prospect["projects"][project]["frozen_proposal"] == prospect["proposal_versions"][0]
    assert prospect["projects"][project]["automated_changes"] == 0
    assert prospect["projects"][project]["automatic_invoicing"] is False
    with pytest.raises(ValueError):
        accepted(prospect, acceptance_evidence="b" * 64)


def test_delivery_requires_dependencies_and_completion_evidence(prospect):
    approve(prospect)
    project = accepted(prospect)
    with pytest.raises(ValueError):
        finish(prospect, project, "task", "1")
    with pytest.raises(ValueError):
        finish(prospect, project, "milestone", "handover")
    finish(prospect, project, "milestone", "scope")
    finish(prospect, project, "milestone", "access")
    with pytest.raises(ValueError):
        finish(prospect, project, "milestone", "implementation")
    finish(prospect, project, "task", "1")
    finish(prospect, project, "milestone", "implementation")
    finish(prospect, project, "milestone", "quality")
    assert prospect["projects"][project]["status"] == "active"
    finish(prospect, project, "milestone", "handover")
    assert prospect["projects"][project]["status"] == "closed"
    before = copy.deepcopy(prospect)
    finish(prospect, project, "milestone", "handover")
    assert prospect == before
    with pytest.raises(ValueError):
        finish(prospect, project, "milestone", "handover", proof="b" * 64)


def test_project_scope_and_history_survive_reload_and_cannot_be_rewritten(prospect):
    approve(prospect)
    with tempfile.TemporaryDirectory() as directory:
        store = PipelineStore(Path(directory) / "projects.sqlite3")
        identity = hashlib.sha256(b"example.com").hexdigest()
        with store.transaction(bootstrap=True) as state:
            state["prospects"][identity] = prospect
            project = accepted(prospect)
        frozen = store.read()["prospects"][identity]["projects"][project]["frozen_proposal"]
        with store.transaction() as state:
            p = state["prospects"][identity]
            p["proposal_version"] = (
                None  # Later marketing/proposal changes do not change accepted work.
            )
            finish(p, project, "milestone", "scope")
        saved = store.read()["prospects"][identity]
        assert saved["projects"][project]["frozen_proposal"] == frozen
        assert saved["projects"][project]["milestones"][0]["status"] == "complete"
        for mutate in (
            lambda p: p["projects"][project]["frozen_proposal"].update(items=[]),
            lambda p: p["projects"][project]["tasks"][0].update(action="Unapproved scope"),
            lambda p: p["projects"][project]["milestones"][0].update(status="pending"),
            lambda p: p["project_events"].clear(),
        ):

            def change(state):
                mutate(state["prospects"][identity])

            with pytest.raises(ValueError):
                commit_mutation(store, change)
