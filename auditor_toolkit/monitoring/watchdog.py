
import ipaddress
import json
import os
import re
import socket
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


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

    @staticmethod
    def _safe_domain(domain: str) -> str:
        """Sanitise *domain* so it cannot escape the snapshot directory."""
        clean = re.sub(r'[^A-Za-z0-9._-]', '_', str(domain))
        return clean[:100] or "unknown"

    @staticmethod
    def _validate_webhook(url: str) -> None:
        """Reject non-http(s) schemes and hosts resolving to private IPs (SSRF)."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"Webhook scheme not allowed: {parts.scheme}")
        host = parts.hostname
        if not host:
            raise ValueError("Webhook URL missing host")
        try:
            if host.lower() == "localhost" or ipaddress.ip_address(host).is_private:
                raise ValueError(f"Webhook to private host rejected: {host}")
        except ValueError:
            # ip_address raises ValueError for non-IP strings (DNS names) — that's fine
            pass
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError(f"Webhook host could not be resolved: {host}") from exc
        if not infos or any(
            ipaddress.ip_address(info[4][0]).is_private for info in infos
        ):
            raise ValueError(f"Webhook resolves to private address: {host}")

    def take_snapshot(self, domain, defects):
        domain = self._safe_domain(domain)
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
        domain = self._safe_domain(domain)
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

        try:
            self._validate_webhook(self.webhook_url)
        except ValueError as e:
            return {"status": "failed", "error": f"webhook validation: {e}"}

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
            with urllib.request.urlopen(req, timeout=10) as resp:
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
