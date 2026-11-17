"""Owner-attested acceptance and project tracking; never executes client work."""

from __future__ import annotations

import copy

from scripts.approval_controls import HASH, actor_record, append, current_proposal
from scripts.cloud_opportunities import digest

MILESTONES = (
    ("scope", "Confirm scope and acceptance criteria"),
    ("access", "Confirm authorized access and required assets"),
    ("implementation", "Record completion of agreed tasks"),
    ("quality", "Record agreed quality and validation checks"),
    ("handover", "Prepare handover and record project closure"),
)


def evidence(value):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError("Source/completion evidence SHA-256 required")
    return value


def accept_proposal(prospect, version, *, acceptance_evidence, owner_verified, actor, reason, now):
    proposal = current_proposal(prospect, version)
    record = actor_record(actor, reason, now)
    evidence(acceptance_evidence)
    if owner_verified is not True:
        raise ValueError("Owner verification of customer acceptance required")
    approvals = [a for a in prospect.get("approvals", []) if a["action_type"] == "proposal"]
    if not approvals or approvals[-1]["decision"] != "approved" or approvals[-1]["version_sha256"] != version:
        raise ValueError("Exact proposal must have owner approval")
    project_id = digest(dict(domain=prospect["domain"], proposal_version=version))
    projects = prospect.setdefault("projects", {})
    if project_id in projects:
        if projects[project_id]["acceptance"]["evidence_sha256"] != acceptance_evidence:
            raise ValueError("Conflicting acceptance evidence; preserve original project")
        return project_id
    if len(projects) >= 100:
        raise ValueError("Project capacity reached")
    project = dict(
        project_id=project_id, domain=prospect["domain"], status="planned",
        proposal_version=version, frozen_proposal=copy.deepcopy(proposal),
        acceptance=dict(**record, evidence_sha256=acceptance_evidence,
                        source="owner_verified_customer_acceptance", independently_verified=False),
        milestones=[dict(id=key, title=title, status="pending", evidence_sha256=None)
                    for key, title in MILESTONES],
        tasks=[dict(id=str(i), finding_id=item["finding_id"], action=item["recommendation"],
                    status="pending", evidence_sha256=None)
               for i, item in enumerate(proposal.get("items", []), 1)],
        required_access=["Owner/client-approved scope of access", "Platform credentials supplied through a secure channel"],
        required_assets=["Client-approved assets and content where needed"],
        production_changes_authorized=False, automated_changes=0, automatic_invoicing=False,
    )
    append(prospect, "project_events", dict(**record, project_id=project_id, action="accepted", evidence_sha256=acceptance_evidence))
    projects[project_id] = project
    return project_id


def complete(prospect, project_id, *, kind, item_id, completion_evidence, actor, reason, now):
    record = actor_record(actor, reason, now)
    evidence(completion_evidence)
    project = prospect.get("projects", {}).get(project_id)
    if project is None or kind not in {"task", "milestone"}:
        raise ValueError("Known project and tracking item required")
    if digest({k: v for k, v in project["frozen_proposal"].items() if k != "version_sha256"}) != project["proposal_version"]:
        raise ValueError("Frozen proposal integrity check failed")
    items = project["tasks" if kind == "task" else "milestones"]
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        raise ValueError("Unknown tracking item")
    if item["status"] == "complete":
        if item["evidence_sha256"] != completion_evidence:
            raise ValueError("Completion evidence already frozen")
        return
    if kind == "task":
        if project["milestones"][1]["status"] != "complete":
            raise ValueError("Confirm scope and authorized access before recording task completion")
    else:
        index = next(i for i, m in enumerate(items) if m["id"] == item_id)
        if any(m["status"] != "complete" for m in items[:index]):
            raise ValueError("Complete preceding milestones first")
        if item_id == "implementation" and any(t["status"] != "complete" for t in project["tasks"]):
            raise ValueError("All tasks need completion evidence")
    append(prospect, "project_events", dict(
        **record, project_id=project_id, action=f"{kind}_complete", item_id=item_id,
        evidence_sha256=completion_evidence,
    ))
    item.update(status="complete", evidence_sha256=completion_evidence)
    project["status"] = "closed" if all(m["status"] == "complete" for m in project["milestones"]) else "active"
