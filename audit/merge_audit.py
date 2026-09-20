#!/usr/bin/env python3
"""Merge deterministic Website Auditor output with browser evidence without inventing claims."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def merge(base: dict, browser: dict) -> dict:
    return {
        "schema_version": 1,
        "target": browser.get("target") or {
            "requested_url": base.get("url"),
            "final_url": base.get("url"),
            "status": None,
        },
        "website_auditor": {
            "score": base.get("score"),
            "defect_count": base.get("defect_count"),
            "defects": base.get("defects", []),
            "evidence": base.get("evidence", {}),
            "meta": base.get("meta", {}),
            "timestamp": base.get("timestamp"),
        },
        "browser_evidence": browser.get("evidence", {}),
        "lighthouse": browser.get("lighthouse", {}),
        "generated_at": browser.get("generated_at"),
        "claim_policy": {
            "evidence_only": True,
            "note": "No finding is promoted beyond the evidence present in the input artifacts.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--browser", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = merge(load_json(args.base), load_json(args.browser))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
