"""P10 deterministic remediation planning and local preview artifacts.

This module never edits a target website. AUTO_SAFE/AUTO_PREVIEW describe how safely
a proposed change can be previewed; production application always remains a separate
reviewed action.
"""
from __future__ import annotations

import csv
import io
from html import escape
from pathlib import Path

from .common import atomic_write_json, atomic_write_text

CLASSES = {
    "AUTO_SAFE",
    "AUTO_PREVIEW",
    "HUMAN_REVIEW",
    "CLIENT_ACCESS_REQUIRED",
    "UNSUPPORTED",
}

DEFAULT_CLASS = {
    "viewport": "AUTO_SAFE",
    "missing_title": "AUTO_PREVIEW",
    "missing_meta_description": "AUTO_PREVIEW",
    "missing_canonical_url": "AUTO_PREVIEW",
    "missing_open_graph_tags": "AUTO_PREVIEW",
    "schema_missing": "AUTO_PREVIEW",
    "robots-missing": "AUTO_PREVIEW",
    "robots-no-sitemap": "AUTO_PREVIEW",
    "sitemap-missing": "AUTO_PREVIEW",
    "broken-internal-link": "AUTO_PREVIEW",
    "mixed-content": "AUTO_PREVIEW",
    "image-alt": "AUTO_PREVIEW",
    "header-hsts": "HUMAN_REVIEW",
    "consent_prechecked": "HUMAN_REVIEW",
}


def classify(defect: dict) -> str:
    explicit = defect.get("remediation_automation")
    if explicit:
        if explicit not in CLASSES:
            raise ValueError(f"Unknown remediation class: {explicit}")
        return explicit
    return DEFAULT_CLASS.get(defect.get("defect_key"), "HUMAN_REVIEW")


def _snippet(defect: dict) -> tuple[str, str] | None:
    key = defect.get("defect_key")
    url = str(defect.get("source_url") or "")
    if key == "viewport":
        return "viewport.html", '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    if key == "missing_canonical_url" and url:
        return "canonical.html", f'<link rel="canonical" href="{escape(url, quote=True)}">\n'
    if key == "missing_title":
        return "title.html", "<title>REVIEW_REQUIRED: page-specific title</title>\n"
    if key == "missing_meta_description":
        return (
            "meta-description.html",
            '<meta name="description" content="REVIEW_REQUIRED: page-specific description">\n',
        )
    if key == "robots-missing":
        return "robots.txt", "User-agent: *\nAllow: /\n# REVIEW_REQUIRED: add canonical sitemap URL\n"
    if key == "robots-no-sitemap":
        return "robots-sitemap.txt", "# Add to existing robots.txt after review:\nSitemap: REVIEW_REQUIRED\n"
    if key == "sitemap-missing":
        return (
            "sitemap.xml",
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            "  <!-- REVIEW_REQUIRED: populate verified canonical URLs -->\n"
            "</urlset>\n",
        )
    if key == "mixed-content":
        return "mixed-content.txt", "Replace verified http:// subresource URLs with working https:// equivalents after asset validation.\n"
    if key == "image-alt":
        return "image-alt.txt", "REVIEW_REQUIRED: describe the verified image purpose; use empty alt only when decorative.\n"
    return None


def build_remediation(report: dict, output_dir) -> dict:
    if not isinstance(report, dict) or not isinstance(report.get("defects"), list):
        raise ValueError("Audit report with defects required")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    items = []
    for index, defect in enumerate(report["defects"], 1):
        if not isinstance(defect, dict) or not defect.get("defect_key"):
            raise ValueError("Malformed defect")
        remediation_class = classify(defect)
        item = {
            "finding_id": defect.get("finding_id"),
            "defect_key": defect["defect_key"],
            "source_url": defect.get("source_url"),
            "classification": remediation_class,
            "action": defect.get("remediation_action")
            or "Review evidence and prepare a bounded platform-specific change.",
            "review_required": True,
            "production_applied": False,
            "verified_fixed": False,
            "artifact": None,
        }
        preview = _snippet(defect) if remediation_class in {"AUTO_SAFE", "AUTO_PREVIEW"} else None
        if preview:
            name, body = preview
            path = output / f"{index:03d}-{name}"
            atomic_write_text(path, body)
            item["artifact"] = str(path)
            item["artifact_kind"] = path.suffix.lstrip(".") or "text"
            item["artifact_status"] = "preview_only"
        elif defect["defect_key"] == "broken-internal-link":
            path = output / f"{index:03d}-redirect-map.csv"
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["broken_url", "replacement_url", "status"])
            writer.writerow([defect.get("impact") or defect.get("source_url"), "", "REVIEW_REQUIRED"])
            atomic_write_text(path, buffer.getvalue())
            item["artifact"] = str(path)
            item["artifact_kind"] = "redirect_map"
            item["artifact_status"] = "preview_only"
        items.append(item)

    manifest = {
        "schema_version": 1,
        "kind": "remediation_preview",
        "source_run_id": report.get("run_id"),
        "source_url": report.get("url"),
        "items": items,
        "counts": {name: sum(i["classification"] == name for i in items) for name in sorted(CLASSES)},
        "review_required": True,
        "external_dispatch": False,
        "production_changes": 0,
        "verification_rule": "Re-run the same audit profile after an independently approved implementation.",
    }
    atomic_write_json(output / "remediation.json", manifest)
    return manifest
