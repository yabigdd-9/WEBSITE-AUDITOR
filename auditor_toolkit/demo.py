"""P11 local demo factory.

A generated demo is a concept, never evidence that the source website changed.
Before/after claims remain invalid until a separately approved implementation is
re-audited with the same profile.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from html import escape
from pathlib import Path

from .common import atomic_write_json, atomic_write_text


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_demo(report: dict, remediation: dict, output_dir) -> dict:
    if remediation.get("source_run_id") != report.get("run_id"):
        raise ValueError("Remediation manifest does not match audit run")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    rows = []
    for item in remediation.get("items", []):
        rows.append(
            "<tr><td>"
            + escape(str(item.get("defect_key")))
            + "</td><td>"
            + escape(str(item.get("classification")))
            + "</td><td>"
            + escape(str(item.get("action")))
            + "</td></tr>"
        )
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'">
<title>Website improvement concept</title>
<style>
body{font:16px/1.55 system-ui;max-width:1000px;margin:32px auto;padding:24px;color:#17231f}
.notice{padding:16px;border:2px solid currentColor;border-radius:8px}
table{width:100%;border-collapse:collapse;margin-top:24px}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #bbb}
code{overflow-wrap:anywhere}
</style></head><body>
<div class="notice"><strong>LOCAL CONCEPT ONLY.</strong> Nothing on the source website has been changed.
This page is not proof of improved performance, accessibility, SEO, leads or revenue.</div>
<h1>Reviewable website improvement concept</h1>
<p>Source: <code>""" + escape(str(report.get("url") or "")) + """</code></p>
<p>Audit run: <code>""" + escape(str(report.get("run_id") or "")) + """</code></p>
<table><thead><tr><th>Finding</th><th>Preview class</th><th>Proposed action</th></tr></thead>
<tbody>""" + "".join(rows) + """</tbody></table>
<p>Verification requirement: implement only after approval, then re-run the same audit profile against the actual site.</p>
</body></html>
"""
    index = output / "index.html"
    atomic_write_text(index, html)

    before = None
    source_screenshot = (report.get("artifacts") or {}).get("screenshot")
    if source_screenshot:
        source = Path(source_screenshot)
        if source.is_file():
            target = output / "before-source.png"
            shutil.copy2(source, target)
            before = {"path": str(target), "sha256": _sha(target), "kind": "captured_source"}

    manifest = {
        "schema_version": 1,
        "kind": "local_demo_concept",
        "source_run_id": report.get("run_id"),
        "source_url": report.get("url"),
        "demo_html": str(index),
        "demo_html_sha256": _sha(index),
        "before": before,
        "after": None,
        "status": "CONCEPT_ONLY",
        "local_concept": True,
        "live_site_changed": False,
        "improvement_claim_valid": False,
        "external_deploy": False,
        "review_required": True,
        "verification_required": "Approved implementation + repeat audit of actual source website.",
    }
    atomic_write_json(output / "demo.json", manifest)
    return manifest


def render_demo(demo_manifest: dict) -> dict:
    """Render the local concept to PNG. This still is not a live-site 'after'."""
    from playwright.sync_api import sync_playwright

    path = Path(demo_manifest["demo_html"]).resolve()
    if not path.is_file():
        raise ValueError("Demo HTML missing")
    screenshot = path.parent / "concept-render.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(path.as_uri(), wait_until="load")
            page.screenshot(path=str(screenshot), full_page=True)
        finally:
            browser.close()
    updated = dict(demo_manifest)
    updated["after"] = {
        "path": str(screenshot),
        "sha256": _sha(screenshot),
        "kind": "local_concept_render",
    }
    updated["improvement_claim_valid"] = False
    atomic_write_json(path.parent / "demo.json", updated)
    return updated
