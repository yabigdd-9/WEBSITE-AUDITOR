#!/usr/bin/env python3
"""Bridge static audit files into the Money Machine database.

Reads JSON audit files from /Users/dd/WEBSITE-AUDITOR/audits/ and inserts
new businesses into the businesses table with source='static_audit' and
is_dummy=0. Deduplicates by domain (canonical, www-stripped).

After insertion, runs Hunter.io enrichment on each new business
(via hunter_enrichment.enrich_business + store_enrichment).

Usage:
    cd /Users/dd/WEBSITE-AUDITOR && .venv-email/bin/python money-machine/bridge_audits.py
"""
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

UTC = dt.timezone.utc

ROOT = Path(__file__).resolve().parents[1]
AUDITS_DIR = ROOT / "audits"
DB_PATH = ROOT / "database" / "money_machine.db"
HUNTER_CACHE_DIR = ROOT / "cache" / "email-v2"


def utcnow() -> str:
    return dt.datetime.now(UTC).isoformat()


def canonical_domain(url_or_domain: str) -> str:
    """Normalize a URL or domain to a canonical domain (no www. prefix)."""
    if not url_or_domain:
        return ""
    # If it looks like a URL, parse it; otherwise treat as a domain
    if "://" in url_or_domain:
        host = urlsplit(url_or_domain).hostname or ""
    else:
        host = url_or_domain.strip().lower()
    host = host.strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def domain_to_name(domain: str) -> str:
    """Derive a human-readable business name from a domain."""
    # e.g., "clyne-bennie.co.nz" -> "Clyne Bennie"
    # e.g., "prodecorators.co.nz" -> "Prodecorators"
    name_part = domain.split(".")[0]
    # Replace hyphens with spaces and title-case
    name_part = name_part.replace("-", " ").replace("_", " ")
    return name_part.strip().title()


def existing_domains(conn: sqlite3.Connection) -> set:
    """Return set of canonical domains already in the businesses table."""
    domains = set()
    rows = conn.execute(
        "SELECT public_website FROM businesses WHERE public_website IS NOT NULL"
    ).fetchall()
    for row in rows:
        if row[0]:
            domains.add(canonical_domain(row[0]))
    return domains


def load_audit_files(audits_dir: Path) -> list[dict]:
    """Load and return all JSON audit files from the directory."""
    audits = []
    if not audits_dir.is_dir():
        print(f"Audit directory not found: {audits_dir}")
        return audits
    for path in sorted(audits_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_file"] = str(path)
            audits.append(data)
        except (json.JSONDecodeError, OSError) as ex:
            print(f"  WARN: skipping {path.name}: {ex}")
    return audits


def insert_business(
    conn: sqlite3.Connection,
    name: str,
    public_website: str,
    discovered_at: str,
) -> int:
    """Insert a new business row. Returns the new business id."""
    cursor = conn.execute(
        """INSERT INTO businesses
           (name, industry_id, region, public_website, source, discovered_at,
            current_status, is_dummy)
           VALUES (?, NULL, ?, ?, 'static_audit', ?, 'discovered', 0)""",
        (name, "NZ-wide", public_website, discovered_at),
    )
    row_id = cursor.lastrowid
    if row_id is None:
        raise RuntimeError("INSERT did not return a row id")
    return row_id


def run_hunter_enrichment(
    conn: sqlite3.Connection,
    business_id: int,
    domain: str,
) -> dict:
    """Run Hunter.io enrichment on a business. Returns result metadata."""
    # Import here so the script still works if hunter module is unavailable
    # or HUNTER_API_KEY is not set.
    hunter_path = ROOT / "money-machine"
    if str(hunter_path) not in sys.path:
        sys.path.insert(0, str(hunter_path))

    try:
        import hunter_enrichment as hunter
    except ImportError as ex:
        return {"status": "skipped", "reason": f"hunter_enrichment import failed: {ex}"}

    if not os.environ.get("HUNTER_API_KEY"):
        return {"status": "skipped", "reason": "HUNTER_API_KEY not set"}

    try:
        result = hunter.enrich_business(
            conn, business_id, domain, cache_dir=HUNTER_CACHE_DIR
        )
        hunter.store_enrichment(conn, business_id, result)
        candidates = result.get("candidates", [])
        return {
            "status": "enriched",
            "candidates": len(candidates),
            "total": result.get("total", 0),
            "domain": result.get("domain"),
            "from_cache": result.get("hunter_cached", False),
        }
    except Exception as ex:
        return {"status": "error", "reason": str(ex)}


def main() -> int:
    print(f"Audits directory: {AUDITS_DIR}")
    print(f"Database:         {DB_PATH}")
    print()

    audits = load_audit_files(AUDITS_DIR)
    print(f"Found {len(audits)} audit files")

    if not audits:
        print("Nothing to do.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Track existing domains for dedup
    existing = existing_domains(conn)
    print(f"Existing domains in DB: {len(existing)}")

    # Dedup audit files by canonical domain (keep last-seen if duplicates)
    seen_domains: dict[str, dict] = {}
    for audit in audits:
        domain = canonical_domain(audit.get("domain") or audit.get("url", ""))
        if domain:
            seen_domains[domain] = audit

    new_businesses = []
    skipped = []

    for domain, audit in sorted(seen_domains.items()):
        url = audit.get("url", "")
        name = audit.get("meta", {}).get("title") or domain_to_name(domain)
        discovered_at = audit.get("timestamp") or utcnow()

        if domain in existing:
            skipped.append({"domain": domain, "name": name})
            continue

        biz_id = insert_business(conn, name, url, discovered_at)
        new_businesses.append({
            "id": biz_id,
            "name": name,
            "domain": domain,
            "url": url,
            "discovered_at": discovered_at,
            "score": audit.get("score"),
            "defect_count": audit.get("defect_count"),
        })
        existing.add(domain)  # prevent double-insert within this run

    conn.commit()

    print(f"\nInserted {len(new_businesses)} new businesses")
    for biz in new_businesses:
        print(f"  + [{biz['id']}] {biz['name']} ({biz['domain']}) "
              f"score={biz['score']} defects={biz['defect_count']}")

    if skipped:
        print(f"\nSkipped {len(skipped)} already-present domains")
        for s in skipped:
            print(f"  ~ {s['name']} ({s['domain']})")

    # --- Hunter.io enrichment ---
    print(f"\n--- Hunter.io Enrichment ---")
    enrichment_results = []
    for biz in new_businesses:
        print(f"  Enriching [{biz['id']}] {biz['name']} ({biz['domain']})...")
        result = run_hunter_enrichment(conn, biz["id"], biz["domain"])
        result["business_id"] = biz["id"]
        result["domain"] = biz["domain"]
        enrichment_results.append(result)
        status = result.get("status")
        if status == "enriched":
            print(f"    -> {result['candidates']} candidates from "
                  f"{result.get('total', 0)} total "
                  f"(cached={result.get('from_cache', False)})")
        elif status == "skipped":
            print(f"    -> SKIPPED: {result.get('reason')}")
        else:
            print(f"    -> ERROR: {result.get('reason')}")

    conn.close()

    # --- Summary ---
    print(f"\n{'='*50}")
    print(f"BRIDGE SUMMARY")
    print(f"{'='*50}")
    print(f"Audit files scanned:    {len(audits)}")
    print(f"Unique domains:         {len(seen_domains)}")
    print(f"Already in DB:          {len(skipped)}")
    print(f"New businesses inserted:{len(new_businesses)}")

    enriched = sum(1 for r in enrichment_results if r.get("status") == "enriched")
    skipped_h = sum(1 for r in enrichment_results if r.get("status") == "skipped")
    errors = sum(1 for r in enrichment_results if r.get("status") == "error")
    print(f"Hunter enriched:        {enriched}")
    print(f"Hunter skipped:         {skipped_h}")
    print(f"Hunter errors:          {errors}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
