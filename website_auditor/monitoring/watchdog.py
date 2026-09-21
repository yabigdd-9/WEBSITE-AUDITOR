
import json, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path

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

    def take_snapshot(self, domain, defects):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.snapshot_dir / f"{domain}_{ts}.json"
        path.write_text(json.dumps({
            "domain": domain,
            "timestamp": ts,
            "defect_keys": sorted([
                d.get("issue", d.get("defect_key", str(d))) for d in defects
            ]),
            "count": len(defects),
        }, indent=2))
        return path

    def get_previous_snapshot(self, domain):
        snapshots = sorted(self.snapshot_dir.glob(f"{domain}_*.json"))
        if len(snapshots) < 2:
            return None
        return json.loads(snapshots[-2].read_text())

    def detect_regressions(self, domain, current_defects):
        current_keys = sorted([
            d.get("issue", d.get("defect_key", str(d))) for d in current_defects
        ])
        prev = self.get_previous_snapshot(domain)
        if not prev:
            return {"regressions": [], "resolved": [], "first_audit": True}

        prev_keys = set(prev.get("defect_keys", []))
        curr_keys = set(current_keys)

        regressions = list(curr_keys - prev_keys)
        resolved = list(prev_keys - curr_keys)

        return {
            "regressions": regressions,
            "resolved": resolved,
            "first_audit": False,
            "previous_count": prev.get("count", 0),
            "current_count": len(current_defects),
        }

    def send_alert(self, domain, regressions):
        if not self.webhook_url:
            return {"status": "skipped", "reason": "ALERT_WEBHOOK_URL not set"}

        message = f"REGRESSION DETECTED: {domain}\n"
        for r in regressions[:5]:
            message += f"  - {r}\n"
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
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def run_check(self, domain, defects):
        result = self.detect_regressions(domain, defects)
        self.take_snapshot(domain, defects)

        if result["regressions"] and not result.get("first_audit"):
            alert_result = self.send_alert(domain, result["regressions"])
            result["alert"] = alert_result

        return result
