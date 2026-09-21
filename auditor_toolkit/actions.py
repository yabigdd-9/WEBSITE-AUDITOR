"""Reviewable local previews. No connector is dispatched from this module."""

import hashlib
import json
from pathlib import Path

from .common import atomic_write_json, atomic_write_text
from .storage import finding_id


def import_report(path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or not isinstance(data.get("defects"), list):
        raise ValueError("Expected explicit report with a defects array")
    if data.get("schema_version") not in (1, 2):
        raise ValueError("Unsupported report schema; use an explicit legacy adapter")
    if not isinstance(data.get("url"), str) or not data.get("run_id"):
        raise ValueError("Report URL and run_id are required")
    for defect in data["defects"]:
        if (
            not isinstance(defect, dict)
            or not {"defect_key", "defect", "source_url"} <= defect.keys()
        ):
            raise ValueError("Malformed defect")
    return data


def preview_report(report, output_dir, policy=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    policy = policy or {"enabled": True, "mode": "dry_run"}
    cancelled = output_dir / "CANCELLED"
    items = []
    seen = set()
    for defect in report["defects"]:
        identity = defect.get("finding_id") or finding_id(defect)
        if identity in seen:
            continue
        seen.add(identity)
        blocked = cancelled.exists() or not policy.get("enabled", False)
        content = {
            "id": identity,
            "finding": defect,
            "run_id": report["run_id"],
            "status": "cancelled" if cancelled.exists() else "blocked" if blocked else "preview",
            "mode": "dry_run",
            "connector": "local",
            "review_required": True,
            "verification": "Run the same audit profile after the proposed fix; never infer success from a preview.",
            "fix": fix_template(defect),
            "external_dispatch": False,
        }
        items.append(content)
        if not blocked:
            atomic_write_text(
                output_dir / (identity + ".md"),
                "# Proposed remediation\n\n```json\n" + json.dumps(content, indent=2) + "\n```\n",
            )
    payload = {
        "run_id": report["run_id"],
        "status": "preview",
        "items": items,
        "count": len(items),
        "external_dispatch": False,
    }
    atomic_write_json(output_dir / "preview.json", payload)
    event_path = output_dir / "events.json"
    events = json.loads(event_path.read_text()) if event_path.exists() else []
    event_id = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if not any(e["id"] == event_id for e in events):
        events.append(
            {"id": event_id, "event": "preview", "run_id": report["run_id"], "count": len(items)}
        )
    atomic_write_json(event_path, events)
    return {"count": len(items), "status": "preview", "path": str(output_dir / "preview.json")}


def fix_template(defect):
    key = defect["defect_key"]
    templates = {
        "missing_title": "Draft a unique title matching the page purpose. Edit the CMS SEO title or HTML <title>; verify the rendered title.",
        "missing_meta_description": "Draft an accurate description in the CMS SEO fields or meta[name=description]. Verify rendered HTML.",
        "image-alt": "Review image purpose. Add descriptive alt text for informative images or empty alt for decorative images. Verify with a screen reader.",
        "header-hsts": "Review HTTPS coverage before configuring HSTS at the reverse proxy. Do not enable preload or includeSubDomains without validation.",
        "consent_prechecked": "Review marketing choice wording and remove the default selection. Recheck actual consent behavior.",
    }
    return {
        "instructions": templates.get(
            key,
            "Review the linked evidence and prepare a platform-specific change. Re-audit before marking verified.",
        ),
        "patch_kind": "instructions",
        "automatically_applicable": False,
    }
