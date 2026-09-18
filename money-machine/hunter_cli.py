#!/usr/bin/env python3
"""Hunter.io enrichment CLI — discover, verify, and enrich business email data.

Commands:
  migrate     Create hunter_enrichment table (idempotent)
  search      Run Hunter domain search for a business
  enrich      Enrich all businesses with websites (batch)
  verify      Verify a specific email address via Hunter
  status      Show enrichment statistics
  sources     Show Hunter independent sources for an email

Usage:
  python3 hunter_cli.py migrate
  python3 hunter_cli.py search <domain> [--limit 10]
  python3 hunter_cli.py enrich [--limit 10] [--batch 5]
  python3 hunter_cli.py verify <email>
  python3 hunter_cli.py status
  python3 hunter_cli.py sources <business_id> <email>
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hunter_enrichment as hunter
import mm_core as c
from mm_email import root_domain

UTC = dt.timezone.utc


def utcnow():
    return dt.datetime.now(UTC).isoformat()


def sha256(data):
    return hashlib.sha256(
        data if isinstance(data, bytes) else data.encode()
    ).hexdigest()


def cmd_migrate(d, args):
    """Create hunter_enrichment table and tracking table."""
    sql_path = Path(__file__).resolve().parent / "006_hunter_enrichment.sql"
    sql = sql_path.read_text()
    sql_hash = sha256(sql)

    # Check if table exists
    table_exists = d.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='hunter_enrichment'"
    ).fetchone()

    if not table_exists:
        # Create tables from migration SQL
        d.executescript("""
            CREATE TABLE IF NOT EXISTS hunter_schema_migrations(
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, sql_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hunter_enrichment(
                id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id),
                email TEXT NOT NULL, normalized_email TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'hunter_enrichment',
                source_url TEXT, source_excerpt TEXT, observed_at TEXT NOT NULL,
                candidate_method TEXT NOT NULL DEFAULT 'hunter_domain_search',
                status TEXT NOT NULL CHECK(status IN ('OBSERVED','CANDIDATE','VERIFIED_HIGH','VERIFIED_MEDIUM','UNVERIFIED','REJECTED','SUPPRESSED')),
                hunter_confidence INTEGER NOT NULL DEFAULT 0 CHECK(hunter_confidence BETWEEN 0 AND 100),
                hunter_sources TEXT NOT NULL DEFAULT '[]',
                hunter_first_name TEXT, hunter_last_name TEXT,
                hunter_position TEXT, hunter_department TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(business_id, normalized_email)
            );
            CREATE INDEX IF NOT EXISTS hunter_enrichment_business ON hunter_enrichment(business_id);
            CREATE INDEX IF NOT EXISTS hunter_enrichment_email ON hunter_enrichment(normalized_email);
            CREATE INDEX IF NOT EXISTS hunter_enrichment_status ON hunter_enrichment(status);
        """)

    # Check if migration recorded
    existing = d.execute(
        "SELECT 1 FROM hunter_schema_migrations WHERE version=6"
    ).fetchone()
    if not existing:
        d.execute(
            "INSERT INTO hunter_schema_migrations VALUES(6,?,?)",
            (utcnow(), sql_hash)
        )
        d.commit()
        print("✓ Migration v6 recorded — hunter_enrichment table ready.")
    else:
        print("Migration v6 already applied.")


def cmd_search(d, args):
    """Run Hunter domain search for a single domain."""
    domain = args.domain
    limit = args.limit
    cache_dir = c.root() / "cache" / "email-v2"

    print(f"Searching Hunter.io for: {domain}")
    result = hunter.domain_search(domain, limit=limit, cache_dir=cache_dir)

    if result is None:
        print("  No results found.")
        return

    print(f"  Total emails found: {result['total']}")
    print(f"  Cached: {'yes' if result.get('from_cache') else 'no'}")
    print()

    for email in result.get("emails", []):
        print(f"  {email['value']}")
        print(f"    Confidence: {email['confidence']}%")
        print(f"    Type: {email.get('type', 'unknown')}")
        if email.get('position'):
            print(f"    Position: {email['position']}")
        if email.get('department'):
            print(f"    Department: {email['department']}")
        if email.get('sources'):
            print(f"    Sources: {len(email['sources'])}")
        print()


def cmd_enrich(d, args):
    """Enrich all businesses with websites via Hunter."""
    limit = args.limit
    batch = args.batch

    # Get businesses with websites that aren't suppressed
    businesses = [
        dict(r) for r in d.execute("""
            SELECT id, name, public_website
            FROM businesses
            WHERE public_website IS NOT NULL AND public_website != ''
              AND is_dummy = 0
              AND NOT EXISTS (
                  SELECT 1 FROM contacts c
                  WHERE c.business_id = businesses.id AND c.do_not_contact = 1
              )
            ORDER BY id
            LIMIT ?
        """, (limit,)).fetchall()
    ]

    if not businesses:
        print("No businesses to enrich.")
        return

    print(f"Enriching {len(businesses)} businesses (batch size: {batch})...")
    print()

    cache_dir = c.root() / "cache" / "email-v2"
    enriched = 0
    skipped = 0
    errors = 0

    for i, biz in enumerate(businesses):
        biz_id = biz["id"]
        website = biz["public_website"]
        domain = root_domain(website)

        # Skip if already enriched recently
        existing = d.execute(
            "SELECT COUNT(*) FROM hunter_enrichment WHERE business_id=?",
            (biz_id,)
        ).fetchone()[0]
        if existing > 0:
            skipped += 1
            continue

        try:
            result = hunter.enrich_business(d, biz_id, domain, cache_dir=cache_dir)
            if result.get("candidates"):
                hunter.store_enrichment(d, biz_id, result)
                d.commit()
                enriched += 1
                print(f"  [{i+1}/{len(businesses)}] {biz['name']} — {len(result['candidates'])} emails found")
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            print(f"  [{i+1}/{len(businesses)}] {biz['name']} — ERROR: {e}")

        # Rate limiting
        if (i + 1) % batch == 0 and i + 1 < len(businesses):
            print(f"  Pausing 1s (rate limit)...")
            import time
            time.sleep(1)

    print()
    print(f"✓ Enriched: {enriched}, Skipped: {skipped}, Errors: {errors}")


def cmd_verify(d, args):
    """Verify a specific email via Hunter."""
    email = args.email
    cache_dir = c.root() / "cache" / "email-v2"

    print(f"Verifying via Hunter.io: {email}")
    result = hunter.email_verifier(email, cache_dir=cache_dir)

    if result is None:
        print("  No result.")
        return

    print(f"  Result: {result['result']}")
    print(f"  Score: {result['score']}")
    print(f"  MX Records: {'yes' if result['mx_records'] else 'no'}")
    print(f"  SMTP Check: {'yes' if result['smtp_check'] else 'no'}")
    print(f"  Accept All: {'yes' if result['accept_all'] else 'no'}")
    print(f"  Disposable: {'yes' if result['disposable'] else 'no'}")
    print(f"  Webmail: {'yes' if result['webmail'] else 'no'}")
    print(f"  Blocked: {'yes' if result['block'] else 'no'}")
    print(f"  Sources: {len(result.get('sources', []))}")


def cmd_status(d, args):
    """Show enrichment statistics."""
    total = d.execute("SELECT COUNT(*) FROM hunter_enrichment").fetchone()[0]
    by_status = d.execute("""
        SELECT status, COUNT(*) as count FROM hunter_enrichment
        GROUP BY status ORDER BY count DESC
    """).fetchall()

    businesses = d.execute(
        "SELECT COUNT(DISTINCT business_id) FROM hunter_enrichment"
    ).fetchone()[0]

    print(f"Hunter.io Enrichment Status")
    print(f"==========================")
    print(f"Total records: {total}")
    print(f"Businesses enriched: {businesses}")
    print()
    print(f"By status:")
    for row in by_status:
        print(f"  {row['status']}: {row['count']}")


def cmd_sources(d, args):
    """Show Hunter independent sources for an email."""
    business_id = args.business_id
    email = args.email

    count = hunter.get_hunter_independent_sources(d, business_id, email)
    print(f"Hunter.io independent sources for {email}: {count}")

    rows = d.execute(
        """SELECT source_url, hunter_confidence, hunter_sources
           FROM hunter_enrichment WHERE business_id=? AND normalized_email=?""",
        (business_id, email)
    ).fetchall()

    for row in rows:
        print(f"  Confidence: {row['hunter_confidence']}%")
        if row['source_url']:
            print(f"  URL: {row['source_url']}")
        try:
            for s in json.loads(row['hunter_sources'] or '[]'):
                print(f"  Source: {s}")
        except (json.JSONDecodeError, TypeError):
            pass


def main():
    parser = argparse.ArgumentParser(
        description="Hunter.io enrichment CLI for Money Machine"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # migrate
    sub.add_parser("migrate", help="Create hunter_enrichment table")

    # search
    p_search = sub.add_parser("search", help="Domain search")
    p_search.add_argument("domain", help="Domain to search")
    p_search.add_argument("--limit", type=int, default=10, help="Max results")

    # enrich
    p_enrich = sub.add_parser("enrich", help="Batch enrich businesses")
    p_enrich.add_argument("--limit", type=int, default=10, help="Max businesses")
    p_enrich.add_argument("--batch", type=int, default=5, help="Batch size")

    # verify
    p_verify = sub.add_parser("verify", help="Verify an email")
    p_verify.add_argument("email", help="Email to verify")

    # status
    sub.add_parser("status", help="Enrichment statistics")

    # sources
    p_sources = sub.add_parser("sources", help="Show Hunter sources")
    p_sources.add_argument("business_id", type=int, help="Business ID")
    p_sources.add_argument("email", help="Email to check")

    args = parser.parse_args()

    # Load .env if available
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = value

    d = c.connect()

    commands = {
        "migrate": cmd_migrate,
        "search": cmd_search,
        "enrich": cmd_enrich,
        "verify": cmd_verify,
        "status": cmd_status,
        "sources": cmd_sources,
    }

    commands[args.command](d, args)


if __name__ == "__main__":
    main()
