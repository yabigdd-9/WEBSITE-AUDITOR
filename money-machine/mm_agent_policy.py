"""P16 deterministic agent assignment policy.

This module validates work ownership only. It does not spawn agents or merge code.
"""
from __future__ import annotations

from pathlib import PurePosixPath

CODING_ROLES = {"CODER", "INTEGRATOR"}
MERGE_ROLE = "INTEGRATOR"


def _safe_path(raw: str) -> str:
    path = PurePosixPath(str(raw))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe repository path: {raw}")
    return path.as_posix()


def validate_assignments(assignments: list[dict]) -> dict:
    if not isinstance(assignments, list):
        raise ValueError("assignments must be a list")
    owners = {}
    branches = set()
    normalized = []
    for item in assignments:
        if not isinstance(item, dict):
            raise ValueError("assignment must be an object")
        role = str(item.get("role") or "").upper()
        task = str(item.get("task") or "").strip()
        branch = str(item.get("branch") or "").strip().removeprefix("refs/heads/")
        writes = [_safe_path(p) for p in item.get("write_paths", [])]
        wants_merge = bool(item.get("merge"))
        if not role or not task:
            raise ValueError("role and task are required")
        if writes and role not in CODING_ROLES:
            raise ValueError(f"{role} cannot own code writes")
        if writes and not branch:
            raise ValueError("coding assignments require isolated branch/worktree")
        if branch:
            if branch in branches:
                raise ValueError(f"branch/worktree already assigned: {branch}")
            if branch in {"master", "main"}:
                raise ValueError("direct master/main assignment forbidden")
            branches.add(branch)
        if wants_merge and role != MERGE_ROLE:
            raise ValueError("only INTEGRATOR may request merge")
        for path in writes:
            candidate = PurePosixPath(path)
            if any(
                candidate == PurePosixPath(owned)
                or candidate.is_relative_to(owned)
                or PurePosixPath(owned).is_relative_to(candidate)
                for owned in owners
            ):
                raise ValueError(f"concurrent write conflict: {path}")
            owners[path] = task
        normalized.append(
            {
                "role": role,
                "task": task,
                "branch": branch or None,
                "write_paths": writes,
                "merge_requested": wants_merge,
            }
        )
    return {
        "valid": True,
        "assignments": normalized,
        "write_owners": owners,
        "direct_master_writes": False,
        "external_send_authority": False,
        "paid_model_usage_allowed": False,
    }
