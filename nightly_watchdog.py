#!/usr/bin/env python3
"""Nightly canonical audits + bounded regression intelligence."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from auditor_toolkit.pipeline import AuditOptions, run_audit
from website_auditor.monitoring.watchdog import Watchdog

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")


def _domain(url: str) -> str:
    return urlparse(url if "://" in url else f"https://{url}").hostname or url


def run_nightly():
    print("\n" + "=" * 60)
    print("Nightly Website Watchdog")
    print("=" * 60 + "\n")

    clients_file = Path("clients.txt")
    if not clients_file.exists():
        print("clients.txt not found")
        return 2

    urls = [line.strip() for line in clients_file.read_text().splitlines() if line.strip()]
    output_root = Path("outputs/nightly")
    snapshot_dir = Path("outputs/snapshots")
    output_root.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    watchdog = Watchdog(snapshot_dir=snapshot_dir)
    regressions = []
    failures = []

    for raw_url in urls:
        url = raw_url if "://" in raw_url else f"https://{raw_url}"
        domain = _domain(url)
        print(f"\nScanning: {domain}")
        try:
            report = run_audit(
                url,
                AuditOptions(
                    output_root=output_root,
                    profile="nz",
                    deep=False,
                    browser=False,
                    tls=True,
                    external_tools=False,
                ),
            )
        except Exception as exc:
            print(f"   audit failed: {exc}")
            failures.append({"domain": domain, "error": str(exc)})
            continue

        defects = report.get("defects", [])
        result = watchdog.run_check(
            domain,
            defects,
            metadata={
                "run_id": report.get("run_id"),
                "status": report.get("status"),
                "health_score": report.get("health_score"),
                "defect_count": report.get("defect_count", len(defects)),
                "schema_version": report.get("schema_version"),
            },
        )
        label = result["classification"]
        print(
            f"   {label}: +{len(result.get('regressions', []))} "
            f"-{len(result.get('resolved', []))} change_score={result.get('change_score', 0)}"
        )
        if label in {"REGRESSION", "MAJOR_REGRESSION"}:
            regressions.append({"domain": domain, **result})

    summary = {
        "regressions": regressions,
        "failures": failures,
        "sites_checked": len(urls),
    }
    Path("outputs/nightly_alerts.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )

    print("\n" + "=" * 60)
    print(
        f"Checked {len(urls)} site(s); "
        f"{len(regressions)} regression(s); {len(failures)} audit failure(s)."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_nightly())
