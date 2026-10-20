#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Screenshot Worker (P2)

Replaces the placeholder with a working auditor_toolkit integration using
browser=True (auditor_toolkit.browser.run_browser_checks).
Writes ONLY to reports/hermes_zero_token/screenshots/ — never to production DB.

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
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from ops.hermes_zero_token.worker_ownership import run_owned_worker  # noqa: E402

SCREENSHOT_DIR = PROJECT_ROOT / "reports" / "hermes_zero_token" / "screenshots"
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
        "import sys; sys.path.insert(0, sys.argv[1])"
        + "\nfrom auditor_toolkit.browser import run_browser_checks\n"
        + "import json\n"
        + "result = run_browser_checks(sys.argv[2], sys.argv[3], enabled=True)\n"
        + "print(json.dumps(result, default=str))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code,
         str(PROJECT_ROOT), url, str(out_dir)],
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


def _main():
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
        cached = False
        for entry in manifest.get("screenshots", []):
            if (entry.get("business_id") != bid or entry.get("url") != url
                    or not isinstance(entry.get("path"), str)):
                continue
            cached_path = Path(entry["path"])
            if (cached_path.resolve().is_relative_to(out_dir.resolve())
                    and cached_path.is_file()
                    and not cached_path.is_symlink()
                    and cached_path.stat().st_size > 0
                    and _sha256(cached_path) == entry.get("sha256")):
                cached = True
                break
        if cached:
            report["details"].append({
                "business_id": bid, "name": name, "url": url,
                "status": "already_captured", "path": str(out_dir),
            })
            continue

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            # A fresh attempt directory prevents a stale PNG from a failed or
            # unrelated capture from being recorded as new evidence.
            attempt_dir = Path(tempfile.mkdtemp(prefix="capture-", dir=out_dir))
            rc, stdout, stderr = capture_with_browser_toolkit(url, attempt_dir)
            try:
                capture = json.loads(stdout)
            except (json.JSONDecodeError, TypeError):
                capture = None
            evidence = capture.get("evidence") if isinstance(capture, dict) else None
            screenshot_path = evidence.get("screenshot") if isinstance(evidence, dict) else None
            latest = Path(screenshot_path) if isinstance(screenshot_path, str) else None
            if (rc == 0 and isinstance(capture, dict) and capture.get("status") == "ok"
                    and latest is not None and latest.suffix.lower() == ".png"
                    and latest.resolve().is_relative_to(attempt_dir.resolve())
                    and not latest.is_symlink() and latest.is_file()
                    and latest.stat().st_size > 0):
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
    return 1 if report["screenshots_failed"] else 0


def main():
    return run_owned_worker(PROJECT_ROOT, 'screenshot_worker', _main)


if __name__ == "__main__":
    sys.exit(main())
