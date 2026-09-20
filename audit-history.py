#!/usr/bin/env python3
"""Ingest audits into SQLite history and emit local regression alerts."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from auditor_core.storage import AuditHistoryStore
from auditor_core.verification import compare_audits


def load_audit(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not an audit JSON object")
    return payload


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def ingest(store: AuditHistoryStore, audit: dict, alerts_dir: Path) -> dict:
    domain = str(audit.get("domain") or "").lower()
    after_id = store.save_audit(audit)
    previous = store.latest(domain, exclude_audit_id=after_id) if domain else None

    result = {
        "domain": domain,
        "audit_id": after_id,
        "history_count": store.count(domain) if domain else store.count(),
        "verification": None,
        "regression_alert": None,
    }

    if previous:
        before_id = previous.pop("_history_audit_id")
        report = compare_audits(previous, audit)
        verification_id = store.record_verification(domain, before_id, after_id, report)
        report["verification_id"] = verification_id
        result["verification"] = report

        health = report.get("health_score") or {}
        health_delta = health.get("delta")
        regression = bool(report.get("introduced_count", 0)) or (
            isinstance(health_delta, (int, float)) and health_delta < 0
        )
        if regression:
            alerts_dir.mkdir(parents=True, exist_ok=True)
            alert = {
                "schema_version": 1,
                "domain": domain,
                "before_audit_id": before_id,
                "after_audit_id": after_id,
                "introduced_check_ids": report.get("introduced_check_ids", []),
                "health_delta": health_delta,
                "verification_id": verification_id,
            }
            path = alerts_dir / f"{safe_name(domain)}-latest-regression.json"
            path.write_text(json.dumps(alert, indent=2, sort_keys=True))
            result["regression_alert"] = str(path)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Website Auditor history/regression store")
    parser.add_argument("--db", default="outputs/history/audits.sqlite3")
    parser.add_argument("--alerts-dir", default="outputs/regressions")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest")
    p.add_argument("audit")

    p = sub.add_parser("ingest-dir")
    p.add_argument("audits_dir", nargs="?", default="audits")

    p = sub.add_parser("status")
    p.add_argument("--domain")

    p = sub.add_parser("regressions")
    p.add_argument("--domain")
    p.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    store = AuditHistoryStore(args.db)
    alerts_dir = Path(args.alerts_dir)

    if args.command == "ingest":
        print(json.dumps(ingest(store, load_audit(args.audit), alerts_dir), indent=2, default=str))
        return

    if args.command == "ingest-dir":
        results = []
        for path in sorted(Path(args.audits_dir).glob("*.json")):
            try:
                results.append(ingest(store, load_audit(path), alerts_dir))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                results.append({"file": str(path), "error": str(exc)})
        print(json.dumps({"count": len(results), "results": results}, indent=2, default=str))
        return

    if args.command == "status":
        print(json.dumps({
            "db": str(store.path),
            "audit_count": store.count(args.domain),
            "domain": args.domain,
        }, indent=2))
        return

    if args.command == "regressions":
        print(json.dumps({
            "regressions": store.recent_regressions(args.domain, args.limit)
        }, indent=2, default=str))


if __name__ == "__main__":
    main()
