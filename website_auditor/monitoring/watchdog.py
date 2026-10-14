"""Bounded, deterministic website regression snapshots.

The watchdog stores only latest + previous baselines per domain. Historical
timestamped snapshots already in the repository remain readable as a migration
fallback, but new runs do not create unbounded Git history.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


_SEVERITY_WEIGHT = {"low": 5, "medium": 15, "high": 30, "critical": 50}


def _key(defect):
    if isinstance(defect, dict):
        return defect.get("issue", defect.get("defect_key", defect.get("finding_id", str(defect))))
    return str(defect)


def _safe_domain(domain: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", domain).strip("._") or "unknown"


class Watchdog:
    def __init__(self, output_root=None, snapshot_dir=None, webhook_url=None):
        if snapshot_dir is not None:
            self.snapshot_dir = Path(snapshot_dir)
        elif output_root is not None:
            self.snapshot_dir = Path(output_root) / "snapshots"
        else:
            self.snapshot_dir = Path("outputs/snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.webhook_url = webhook_url or os.getenv("ALERT_WEBHOOK_URL", "")

    def _latest_path(self, domain):
        return self.snapshot_dir / f"{_safe_domain(domain)}_latest.json"

    def _previous_path(self, domain):
        return self.snapshot_dir / f"{_safe_domain(domain)}_previous.json"

    def _legacy_previous(self, domain):
        candidates = [
            path for path in self.snapshot_dir.glob(f"{_safe_domain(domain)}_*.json")
            if not path.name.endswith(("_latest.json", "_previous.json"))
        ]
        if not candidates:
            return None
        return sorted(candidates)[-1]

    def take_snapshot(self, domain, defects, metadata=None):
        latest = self._latest_path(domain)
        previous = self._previous_path(domain)
        if latest.exists():
            previous.write_text(latest.read_text())

        now = datetime.now(timezone.utc)
        payload = {
            "domain": domain,
            "timestamp": now.isoformat(),
            "defect_keys": sorted(_key(d) for d in defects),
            "count": len(defects),
            "metadata": metadata or {},
        }
        latest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return latest

    def get_previous_snapshot(self, domain):
        # Before take_snapshot() rotates files, latest is the prior run.
        latest = self._latest_path(domain)
        if latest.exists():
            return json.loads(latest.read_text())
        legacy = self._legacy_previous(domain)
        if legacy is not None:
            return json.loads(legacy.read_text())
        return None

    def detect_regressions(self, domain, current_defects):
        current_keys = sorted(_key(d) for d in current_defects)
        prev = self.get_previous_snapshot(domain)
        if not prev:
            return {
                "regressions": [],
                "resolved": [],
                "first_audit": True,
                "classification": "NORMAL",
                "change_score": 0,
            }

        prev_keys = set(prev.get("defect_keys", []))
        curr_keys = set(current_keys)
        regressions = sorted(curr_keys - prev_keys)
        resolved = sorted(prev_keys - curr_keys)

        defect_by_key = {_key(d): d for d in current_defects if isinstance(d, dict)}
        change_score = min(
            100,
            sum(
                _SEVERITY_WEIGHT.get(
                    str(defect_by_key.get(key, {}).get("severity", "medium")).lower(),
                    15,
                )
                for key in regressions
            ),
        )
        if any(
            str(defect_by_key.get(key, {}).get("severity", "")).lower() in {"high", "critical"}
            for key in regressions
        ) or change_score >= 50:
            classification = "MAJOR_REGRESSION"
        elif regressions:
            classification = "REGRESSION"
        elif resolved:
            classification = "IMPROVEMENT"
        else:
            classification = "NORMAL"

        return {
            "regressions": regressions,
            "resolved": resolved,
            "first_audit": False,
            "previous_count": prev.get("count", 0),
            "current_count": len(current_defects),
            "classification": classification,
            "change_score": change_score,
        }

    def send_alert(self, domain, regressions, classification="REGRESSION"):
        if not self.webhook_url:
            return {"status": "skipped", "reason": "ALERT_WEBHOOK_URL not set"}

        message = f"{classification}: {domain}\n"
        for regression in regressions[:5]:
            message += f"  - {regression}\n"
        message += f"\nDetected: {datetime.now(timezone.utc).isoformat()}"

        payload = json.dumps({"text": message, "content": message}).encode()
        req = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return {"status": "sent", "code": resp.status}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    def run_check(self, domain, defects, metadata=None):
        result = self.detect_regressions(domain, defects)
        self.take_snapshot(domain, defects, metadata=metadata)

        if result["regressions"] and not result.get("first_audit"):
            result["alert"] = self.send_alert(
                domain,
                result["regressions"],
                classification=result["classification"],
            )
        return result
