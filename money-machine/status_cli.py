#!/usr/bin/env python3
"""Money Machine Status CLI — single dashboard view of the pipeline.

Shows: businesses, websites, email verification stats, outreach-ready count,
suppression list size, and Hunter enrichment statistics.

Usage:
  python3 status_cli.py
"""
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

# Add parent to path so we can import mm_core
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mm_core as c

UTC = dt.timezone.utc


def section(title: str, width: int = 50) -> str:
    line = "═" * width
    pad = (width - len(title) - 2) // 2
    return f"\n{'═' * pad} {title} {'═' * (width - pad - len(title) - 2)}\n"


def fmt(n: int) -> str:
    return f"{n:>6}"


def fmt_pct(n: int, d: int) -> str:
    if d == 0:
        return "   n/a"
    return f"{n/d*100:5.1f}%"


def main() -> None:
    d = c.connect()

    # ── Business Overview ──────────────────────────────────────
    total_biz = d.execute(
        "SELECT COUNT(*) FROM businesses WHERE is_dummy=0"
    ).fetchone()[0]

    with_website = d.execute(
        "SELECT COUNT(*) FROM businesses WHERE is_dummy=0 AND public_website IS NOT NULL AND public_website != ''"
    ).fetchone()[0]

    # Current status breakdown
    status_rows = d.execute(
        "SELECT current_status, COUNT(*) FROM businesses WHERE is_dummy=0 GROUP BY current_status ORDER BY COUNT(*) DESC"
    ).fetchall()

    # ── Email Pipeline ─────────────────────────────────────────
    # Use the prospect_email_state table for the authoritative "current best" per business
    email_state_rows = d.execute(
        "SELECT selection_status, COUNT(*) FROM prospect_email_state GROUP BY selection_status ORDER BY COUNT(*) DESC"
    ).fetchall()

    # Verified counts from email_verifications (all historical)
    verified_high_ev = d.execute(
        "SELECT COUNT(*) FROM email_verifications WHERE confidence_label='VERIFIED_HIGH'"
    ).fetchone()[0]
    verified_med_ev = d.execute(
        "SELECT COUNT(*) FROM email_verifications WHERE confidence_label='VERIFIED_MEDIUM'"
    ).fetchone()[0]
    rejected_ev = d.execute(
        "SELECT COUNT(*) FROM email_verifications WHERE confidence_label='REJECTED'"
    ).fetchone()[0]
    unverified_ev = d.execute(
        "SELECT COUNT(*) FROM email_verifications WHERE confidence_label IN ('UNVERIFIED','OBSERVED','CANDIDATE')"
    ).fetchone()[0]
    suppressed_ev = d.execute(
        "SELECT COUNT(*) FROM email_verifications WHERE confidence_label='SUPPRESSED'"
    ).fetchone()[0]

    # Total candidates
    total_candidates = d.execute("SELECT COUNT(*) FROM email_candidates").fetchone()[0]
    total_verifications = d.execute("SELECT COUNT(*) FROM email_verifications").fetchone()[0]

    # ── Outreach Ready ─────────────────────────────────────────
    # Businesses with a VERIFIED_HIGH best email in prospect_email_state
    outreach_ready = d.execute(
        "SELECT COUNT(*) FROM prospect_email_state WHERE selection_status='VERIFIED_HIGH'"
    ).fetchone()[0]

    # Businesses that also have contact evidence and aren't suppressed
    fully_ready = d.execute(
        """
        SELECT COUNT(*) FROM prospect_email_state p
        WHERE p.selection_status='VERIFIED_HIGH'
          AND EXISTS (SELECT 1 FROM mm_contact_evidence c WHERE c.business_id = p.prospect_id)
          AND NOT EXISTS (SELECT 1 FROM mm_suppression s WHERE lower(trim(s.address)) = lower(trim(
              (SELECT ec.normalized_email FROM email_candidates ec WHERE ec.id = p.best_email_id)
          )))
        """
    ).fetchone()[0]

    # ── Suppression ────────────────────────────────────────────
    suppression_count = d.execute("SELECT COUNT(*) FROM mm_suppression").fetchone()[0]
    dnc_count = d.execute(
        "SELECT COUNT(*) FROM contacts WHERE do_not_contact=1"
    ).fetchone()[0]

    # ── Hunter Enrichment ──────────────────────────────────────
    hunter_total = d.execute("SELECT COUNT(*) FROM hunter_enrichment").fetchone()[0]
    hunter_biz = d.execute(
        "SELECT COUNT(DISTINCT business_id) FROM hunter_enrichment"
    ).fetchone()[0]

    hunter_by_status = d.execute(
        "SELECT status, COUNT(*) FROM hunter_enrichment GROUP BY status ORDER BY COUNT(*) DESC"
    ).fetchall()

    # Corroborated = businesses that have hunter_sources (real sources found)
    corroborated = d.execute(
        "SELECT COUNT(DISTINCT business_id) FROM hunter_enrichment WHERE hunter_sources IS NOT NULL AND hunter_sources != '[]'"
    ).fetchone()[0]

    # High confidence (confidence >= 70)
    hunter_high_conf = d.execute(
        "SELECT COUNT(*) FROM hunter_enrichment WHERE hunter_confidence >= 70"
    ).fetchone()[0]

    # ── Messages & Proposals ───────────────────────────────────
    msg_count = d.execute("SELECT COUNT(*) FROM mm_messages").fetchone()[0]
    sent_count = d.execute(
        "SELECT COUNT(*) FROM mm_messages WHERE sent_at IS NOT NULL"
    ).fetchone()[0]
    proposal_count = d.execute("SELECT COUNT(*) FROM mm_proposals").fetchone()[0]

    # ── Render ─────────────────────────────────────────────────
    width = 50
    now = dt.datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    print()
    print(f"  💰  MONEY MACHINE STATUS")
    print(f"  {now}")
    print(f"  {'─' * width}")

    # Business overview
    print(section("BUSINESSES"))
    print(f"  Total businesses:       {fmt(total_biz)}")
    print(f"  With website:           {fmt(with_website)}  ({fmt_pct(with_website, total_biz)})")
    print(f"  Without website:        {fmt(total_biz - with_website)}")
    print()
    print("  By pipeline stage:")
    for row in status_rows:
        print(f"    {row['current_status']:<22} {fmt(row[1])}")

    # Email pipeline
    print(section("EMAIL PIPELINE"))
    print(f"  Total candidates:       {fmt(total_candidates)}")
    print(f"  Total verifications:    {fmt(total_verifications)}")
    print()
    print("  By verification label:")
    print(f"    VERIFIED_HIGH:         {fmt(verified_high_ev)}")
    print(f"    VERIFIED_MEDIUM:       {fmt(verified_med_ev)}")
    print(f"    REJECTED:              {fmt(rejected_ev)}")
    print(f"    SUPPRESSED:            {fmt(suppressed_ev)}")
    print(f"    Other (unverified):    {fmt(unverified_ev)}")
    print()
    print("  Current best per business (prospect_email_state):")
    for row in email_state_rows:
        print(f"    {row['selection_status']:<22} {fmt(row[1])}")

    # Outreach ready
    print(section("OUTREACH-READY"))
    print(f"  VERIFIED_HIGH emails:   {fmt(outreach_ready)}")
    print(f"  Fully ready (verified + contact evidence, not suppressed): {fully_ready}")

    # Suppression
    print(section("SUPPRESSION"))
    print(f"  mm_suppression entries: {fmt(suppression_count)}")
    print(f"  Do-not-contact contacts:{fmt(dnc_count)}")

    # Hunter enrichment
    print(section("HUNTER ENRICHMENT"))
    print(f"  Total records:          {fmt(hunter_total)}")
    print(f"  Businesses enriched:    {fmt(hunter_biz)}")
    print(f"  Corroborated (sources): {fmt(corroborated)}  ({fmt_pct(corroborated, hunter_biz)} of enriched)")
    print(f"  High confidence (≥70%): {fmt(hunter_high_conf)}")
    print()
    print("  By status:")
    for row in hunter_by_status:
        print(f"    {row['status']:<22} {fmt(row[1])}")

    # Messages
    print(section("MESSAGES & PROPOSALS"))
    print(f"  Messages created:       {fmt(msg_count)}")
    print(f"  Messages sent:          {fmt(sent_count)}")
    print(f"  Proposals:              {fmt(proposal_count)}")

    print()
    print(f"  {'═' * width}")
    print()


if __name__ == "__main__":
    main()
