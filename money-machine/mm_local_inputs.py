"""Bounded JSON inputs owned by a selected local workspace."""
from __future__ import annotations

import json
from pathlib import Path

import mm_core as core

MAX_JSON_BYTES = 8 * 1024 * 1024


def read_json(value, *, workspace=None):
    """Reject parent/symlink escapes before opening an operator input file."""
    base = Path(workspace or core.root()).resolve()
    path = Path(value).resolve()
    if path == base or not path.is_relative_to(base) or path.suffix.lower() != '.json':
        raise ValueError('JSON_INPUT_OUTSIDE_WORKSPACE_OR_INVALID_TYPE')
    with path.open('rb') as handle:
        raw = handle.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError('JSON_INPUT_TOO_LARGE')
    return json.loads(raw)
