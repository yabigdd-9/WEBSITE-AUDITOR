#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Screenshot Worker (P2)

Replaces the placeholder with a working auditor_toolkit integration using
browser=True (auditor_toolkit.browser.run_browser_checks).
Writes ONLY to ignored state/hermes_zero_token/screenshots/ — never to production DB.

Every screenshot is stored with:
  - source URL
  - capture timestamp
  - sha256 hash
  - manifest entry (manifest_sha256.json)

No fabricated or altered proof.
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(PROJECT_ROOT)

SCREENSHOT_DIR = PROJECT_ROOT / "state" / "hermes_zero_token" / "screenshots"
MANIFEST_PATH = SCREENSHOT_DIR / "manifest_sha256.json"

os.environ["HERMES_ZERO_TOKEN_MODE"] = "ZERO_LLM"
os.environ["HERMES_ALLOW_HOSTED_LLM"] = "0"
os.environ["HERMES_ALLOW_PAID_FALLBACK"] = "0"
os.environ["WEBSITE_AUDITOR_OUTREACH_SEND"] = "0"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_pending_businesses(limit=3):
    conn = __import__("sqlite3").connect(
        f"file:{PROJECT_ROOT / 'database' / 'money_machine.db'}?mode=ro", uri=True
    )
    conn.row_factory = __import__("sqlite3").Row
    rows = conn.execute(
        "SELECT id, name, public_website FROM businesses "
        "WHERE is_dummy=0 AND public_website IS NOT NULL AND public_website != '' "
        "ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def capture_with_browser_toolkit(url, out_dir):
    """Use auditor_toolkit.browser.run_browser_checks (browser=True)."""
    code = (
        "import sys; sys.path.insert(0, r'%s')" % str(PROJECT_ROOT)
        + "\nfrom auditor_toolkit.browser import run_browser_checks\n"
        + "import json\n"
        + "result = run_browser_checks(r'%s', r'%s', enabled=True)\n" % (url, str(out_dir))
        + "print(json.dumps(result, default=str))\n"
    )
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv" / "bin" / "python"), "-c", code],
        capture_output=True, text=True, timeout=90,
    )
    return result.returncode, result.stdout, result.stderr


def load_manifest():
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {"screenshots": [], "generated_at": None}


def save_manifest(manifest):
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, default=str))
    os.replace(tmp, MANIFEST_PATH)


def main():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    manifest["generated_at"] = _now()

    businesses = get_pending_businesses(limit=3)
    report = {
        "generated_at": _now(),
        "phase": "P2",
        "screenshot_dir": str(SCREENSHOT_DIR),
        "production_written": False,
        "businesses_requested": len(businesses),
        "screenshots_captured": 0,
        "screenshots_failed": 0,
        "details": [],
    }

    for b in businesses:
        bid, name, url = b["id"], b["name"], b["public_website"]
        out_dir = SCREENSHOT_DIR / f"business-{bid}"
        if out_dir.exists() and any(out_dir.glob("*.png")):
            report["details"].append({
                "business_id": bid, "name": name, "url": url,
                "status": "already_captured", "path": str(out_dir),
            })
            continue

        try:
            rc, stdout, stderr = capture_with_browser_toolkit(url, out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            pngs = sorted(out_dir.glob("*.png"))
            if pngs:
                latest = pngs[-1]
                h = _sha256(latest)
                entry = {
                    "business_id": bid,
                    "name": name,
                    "url": url,
                    "path": str(latest),
                    "sha256": h,
                    "size_bytes": latest.stat().st_size,
                    "captured_at": _now(),
                    "status": "captured",
                }
                manifest["screenshots"].append(entry)
                report["screenshots_captured"] += 1
                report["details"].append(entry)
            else:
                report["screenshots_failed"] += 1
                report["details"].append({
                    "business_id": bid, "name": name, "url": url,
                    "status": "failed", "error": (stderr or stdout)[:300],
                })
        except Exception as ex:
            report["screenshots_failed"] += 1
            report["details"].append({
                "business_id": bid, "name": name, "url": url,
                "status": "error", "error": f"{type(ex).__name__}: {ex}",
            })

    save_manifest(manifest)
    report["manifest_path"] = str(MANIFEST_PATH)
    report["manifest_screenshot_count"] = len(manifest["screenshots"])
    report_path = SCREENSHOT_DIR / "screenshot_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
