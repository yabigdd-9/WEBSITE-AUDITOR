"""Audit coverage must retain its user-facing qualification text."""
from dataclasses import asdict

import pytest

from auditor_toolkit.models import REGISTRY


@pytest.mark.parametrize("check_id", ["hygiene", "links"])
def test_static_check_keeps_evidence_limitations_in_serialized_definition(check_id):
    definition = asdict(REGISTRY[check_id])
    assert definition["mode"] == "static"
    assert definition["evidence_required"] is True
    assert definition["limitation"].strip()
