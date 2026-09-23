"""Tests for proof diff generation."""

from auditor_toolkit.proof.render.diff import generate_diff


def test_generate_diff_returns_dict():
    result = generate_diff(before_path="", after_path="", output_dir="/tmp")
    assert isinstance(result, dict)
