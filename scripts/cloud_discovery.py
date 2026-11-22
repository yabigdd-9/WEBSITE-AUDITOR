"""Offline discovery imports using the existing MoneyMachine source adapters.

Imports are not audit authorization. No source acquisition or contact lookup is
performed; source terms must be reviewed before an export is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import ipaddress
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from scripts.pipeline_store import PipelineStore

MAX_CANDIDATES = 100
MAX_DISCOVERY_EVENTS = 10000


def canonical_domain(raw):
    """Match MoneyMachine's www alias identity, with stricter cloud intake gates."""
    if not isinstance(raw, str) or any(ord(c) < 33 for c in raw):
        raise ValueError("Invalid website")
    parts = urlsplit(raw if "://" in raw else "https://" + raw)
    host = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme != "https" or parts.username or parts.password
        or parts.port not in (None, 443) or parts.query or parts.fragment
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host)
        or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
               for label in host.split("."))
        or "." not in host
        or host.endswith((".local", ".internal", ".localhost", ".test", ".invalid"))
        or host == "localhost" or host.startswith("localhost.")
    ):
        raise ValueError("Public HTTPS domain required")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        # Reject alternate numeric IPv4 spellings too; DNS is checked at fetch.
        if host.split(".")[-1].isdigit() or host.startswith("0x"):
            raise ValueError("Numeric destination rejected")
    else:
        raise ValueError("Website discovery requires a domain, not an IP")
    return host.removeprefix("www.")


def existing_adapter():
    """Load the existing repository adapter without changing its DB or defaults."""
    directory = Path(__file__).resolve().parents[1] / "money-machine"
    sys.path.insert(0, str(directory))
    try:
        module = importlib.import_module("mm_discovery")
        if Path(module.__file__).resolve() != directory / "mm_discovery.py":
            raise ValueError("Unexpected discovery module")
        return module
    finally:
        sys.path.remove(str(directory))


def import_export(state, path, *, source, source_url, terms_reviewed, now, run_id):
    """Normalize and merge a reviewed export atomically; return counts only."""
    if source not in {"curated", "osm", "nzbn"} or terms_reviewed is not True:
        raise ValueError("Permitted export source and explicit terms review required")
    canonical_domain(source_url)
    if not run_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
        raise ValueError("Invalid run ID")
    # read_candidates supplies source-specific normalization, size/row bounds,
    # provenance, and field minimization. No new scanner or source scraper.
    normalized, rejected = existing_adapter().read_candidates(
        path, default_source=source, url_validator=canonical_domain
    )
    from scripts.cloud_prospect_pipeline import timestamp

    incoming = {}
    rejected_count = len(rejected)
    for row in normalized:
        try:
            domain = canonical_domain(row["public_website"])
        except (ValueError, TypeError):
            rejected_count += 1
            continue
        identity = hashlib.sha256(domain.encode()).hexdigest()
        candidate = incoming.setdefault(identity, dict(
            domain=domain, business_name=row["name"], region=row["region"],
            category=row["category"],
            # The existing adapter does not verify a public business identity.
            verification_status="unverified", eligibility_status="pending_policy_review",
            audit_status="not_queued", first_seen=timestamp(now), last_seen=timestamp(now),
            sources=[],
        ))
        provenance = dict(
            source=source, source_url=source_url,
            source_record_id=row["provenance"]["record_id"], terms_reviewed=True,
        )
        if provenance not in candidate["sources"]:
            candidate["sources"].append(provenance)
    candidates = state.get("discovery_candidates", {})
    if len(set(candidates) | set(incoming)) > MAX_CANDIDATES:
        raise ValueError("Discovery capacity reached; owner archive required")
    events = state.get("discovery_events", [])
    if len(events) + len(incoming) > MAX_DISCOVERY_EVENTS:
        raise ValueError("Discovery event capacity reached")
    # Prepare on a copy; validation failures never partially mutate callers.
    import copy

    working = copy.deepcopy(candidates)
    additions = []
    added = 0
    for identity, row in incoming.items():
        if identity not in working:
            working[identity] = row
            added += 1
        else:
            previous = working[identity]
            previous["last_seen"] = timestamp(now)
            for provenance in row["sources"]:
                if provenance not in previous["sources"]:
                    previous["sources"].append(provenance)
        # Same source and content is idempotent even under a new execution ID.
        digest = hashlib.sha256(json.dumps(
            {k: v for k, v in row.items() if k not in {"first_seen", "last_seen"}},
            sort_keys=True,
        ).encode()).hexdigest()
        if not any(e["candidate_id"] == identity and e["content_sha256"] == digest for e in events):
            additions.append(dict(
                candidate_id=identity, content_sha256=digest,
                timestamp_utc=timestamp(now), run_id=run_id, status="pending_policy_review",
            ))
    state["discovery_candidates"] = working
    state["discovery_events"] = [*events, *additions]
    return {"new_candidates": added, "merged_candidates": len(incoming) - added,
            "rejected_rows": rejected_count, "total_candidates": len(working)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline discovery export import; never audits")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source", choices=("curated", "osm", "nzbn"), required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--terms-reviewed", action="store_true", required=True)
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args(argv)
    try:
        import time

        with PipelineStore(args.database).transaction(bootstrap=args.bootstrap) as state:
            counts = import_export(
                state, args.input, source=args.source, source_url=args.source_url,
                terms_reviewed=args.terms_reviewed, now=int(time.time()), run_id="owner-import",
            )
        print(json.dumps(counts, sort_keys=True))
        return 0
    except Exception:
        print("Discovery import blocked; inspect input privately. No requests or audits performed.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
