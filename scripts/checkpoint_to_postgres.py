"""One-time, transactional import of a verified encrypted queue checkpoint."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import time
from pathlib import Path

from scripts.cloud_prospect_pipeline import event, metrics, unseal
from scripts.pipeline_store import validate

COLLECTIONS = {
    "prospects", "audit_runs", "business_events", "discovery_candidates",
    "discovery_events", "report_artifacts", "audit_artifact_links",
}


def import_checkpoint(store, incoming, *, source_run, actor, now=None):
    if (not isinstance(source_run, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", source_run)
            or not isinstance(actor, str) or not actor.strip() or len(actor) > 100
            or "checkpoint_import" in incoming or "storage_authority" in incoming):
        raise ValueError("A reviewed legacy source and owner identity are required")
    fingerprint = hashlib.sha256(validate(incoming).encode()).hexdigest()
    now = time.time() if now is None else now
    with store.transaction() as current:
        receipt = current.get("checkpoint_import")
        if receipt:
            if receipt["source_run"] != source_run or receipt["state_sha256"] != fingerprint:
                raise ValueError("Existing import differs; explicit recovery is required")
            return {"already_imported": True, "source_run": source_run, **metrics(current)}
        if (any(current.get(key) for key in COLLECTIONS)
                or set(current) - COLLECTIONS - {"schema_version", "events"}
                or store.operational_summary()["reservations"]):
            raise ValueError("Import requires a private destination with no business data or reservations")
        migrated = copy.deepcopy(incoming)
        # Preserve existing setup evidence, then the source's complete ordered
        # history. Never clear opt-outs, owner decisions or historical budgets.
        migrated["events"] = copy.deepcopy(current["events"]) + migrated["events"]
        migrated["checkpoint_import"] = {
            "source_run": source_run, "state_sha256": fingerprint, "imported_at": now,
            "actor_sha256": hashlib.sha256(actor.encode()).hexdigest(),
        }
        migrated["storage_authority"] = "postgres"
        event(migrated, now, "pg-import-" + source_run, "0" * 64, "recovery", "approved")
        validate(migrated)
        current.clear()
        current.update(migrated)
        return {"already_imported": False, "source_run": source_run, **metrics(current)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--source-run", required=True)
    args = parser.parse_args(argv)
    try:
        from scripts.cloud_review_only_opportunities import _verify_safety
        from scripts.postgres_store import PostgresPipelineStore

        _verify_safety(Path(__file__).resolve().parents[1])
        incoming = unseal(args.checkpoint, os.environ.get("WA_PIPELINE_STATE_KEY", ""))
        report = import_checkpoint(
            PostgresPipelineStore(), incoming, source_run=args.source_run,
            actor=os.environ.get("GITHUB_ACTOR", "local-owner"),
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception:
        print("Private checkpoint import blocked; inspect source and configuration privately.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
