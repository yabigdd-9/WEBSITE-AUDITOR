"""Render sub-package — visual diff, demo generation, and report assembly."""

from .demo import generate_demo_html
from .diff import generate_diff
from .package_builder import build_proof_package
from .report import generate_json_report, generate_markdown_report

__all__ = [
    "generate_diff",
    "generate_demo_html",
    "build_proof_package",
    "generate_markdown_report",
    "generate_json_report",
]
