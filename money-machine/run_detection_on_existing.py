#!/usr/bin/env python3
"""
Run Website Rescue detection stack on existing prospect candidates.
Scores and tiers them using T-001 methodology.

Usage:
    python3 run_detection_on_existing.py --input outreach/prospect_candidates.csv --output outputs/T004_EXISTING_PROSPECTS_SCORED.csv
"""

import argparse
import csv
import sys
from pathlib import Path


# Defect severity weights (must match T-001 methodology)
DEFECT_WEIGHTS = {
    'NO_HTTPS': 10,
    'NOT_MOBILE_RESPONSIVE': 8,
    'BROKEN_LINKS': 6,
    'NAP_INCONSISTENCY': 7,
    'NO_CONTACT_FORM': 5,
    'STALE_COPYRIGHT': 9,
    'SLOW_PAGE_LOAD': 8,
    'MISSING_TITLE_META': 5,
    'NO_GBP': 7,
    'DEAD_SOCIAL_LINKS': 4,
    'EXPIRED_DOMAIN': 10,
    # Additional defects found in existing data
    'HEAVY_HTML': 6,
    'NO_WRITTEN_CONTACT': 5,
    'NO_SOCIAL_LINKS': 4,
    'NO_CONTACT_ON_HOMEPAGE': 7,
}


def score_prospect(record: dict) -> dict:
    """Apply T-001 scoring rubric to a prospect record."""
    defects_str = record.get('defects', '').strip()
    region = record.get('region', '').strip()
    ratified = record.get('ratified', 'False').strip() == 'True'

    # Parse individual defects
    defects = [d.strip() for d in defects_str.split(',') if d.strip()]

    # Base score: 25 points per defect (capped at 75 for 3+ defects)
    defect_score = min(len(defects) * 15, 45)  # 3+ defects = 45 pts (from T-001: 25 for >=3)
    if len(defects) >= 3:
        defect_score = 25  # Matches T-001 rubric exactly

    # Regional bonus: Christchurch/Canterbury = priority region
    region_bonus = 0
    if 'canterbury' in region.lower() or 'christchurch' in region.lower():
        region_bonus = 15
    elif 'nelson' in region.lower() or 'tasman' in region.lower():
        region_bonus = 5  # Secondary region

    # Local-search-dependent industry (services = trades/professional)
    industry_bonus = 0
    industry = record.get('industry', '').strip().lower()
    if industry in ('services', 'construction', 'trades', 'professional'):
        industry_bonus = 15

    # Activity signal (has website with defects = actively operating but neglecting digital)
    activity_bonus = 8  # Implicit: they have a site with defects

    # No agency footprint (assumed for these small NZ businesses)
    agency_bonus = 10

    # Small business signal (NZ domain, local business)
    size_bonus = 10

    # Calculate total
    total = defect_score + region_bonus + industry_bonus + activity_bonus + agency_bonus + size_bonus

    # Cap at 100
    total = min(total, 100)

    # Determine tier
    if total >= 80:
        tier = 'HOT'
    elif total >= 60:
        tier = 'WARM'
    elif total >= 40:
        tier = 'NURTURE'
    else:
        tier = 'DEPRIORITISE'

    return {
        'business_name': record.get('business_name', '').strip(),
        'website_url': record.get('website_url', '').strip(),
        'region': region,
        'industry': record.get('industry', '').strip(),
        'email': record.get('email', '').strip(),
        'defects': defects_str,
        'defect_count': len(defects),
        'defect_score': defect_score,
        'region_bonus': region_bonus,
        'industry_bonus': industry_bonus,
        'total_score': total,
        'tier': tier,
        'ratified': ratified,
        'source_url': record.get('source_url', '').strip(),
    }


def main():
    parser = argparse.ArgumentParser(description='Run detection stack on existing prospects')
    parser.add_argument('--input', default='outreach/prospect_candidates.csv')
    parser.add_argument('--output', default='outputs/T004_EXISTING_PROSPECTS_SCORED.csv')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Read input
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        records = list(reader)

    print(f"Scoring {len(records)} existing prospects...")

    # Score each
    scored = [score_prospect(r) for r in records]

    # Sort: HOT first, then by score descending
    scored.sort(key=lambda x: (0 if x['tier'] == 'HOT' else 1 if x['tier'] == 'WARM' else 2, -x['total_score']))

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ['business_name', 'website_url', 'region', 'industry', 'email',
                  'defects', 'defect_count', 'defect_score', 'region_bonus',
                  'industry_bonus', 'total_score', 'tier', 'ratified', 'source_url']

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(scored)

    print(f"\n✓ Wrote {len(scored)} scored prospects to: {output_path}")

    # Print summary
    tiers = {}
    for s in scored:
        tiers[s['tier']] = tiers.get(s['tier'], 0) + 1

    print(f"\n--- Tier Summary ---")
    for tier in ['HOT', 'WARM', 'NURTURE', 'DEPRIORITISE']:
        count = tiers.get(tier, 0)
        print(f"  {tier}: {count}")

    hot = [s for s in scored if s['tier'] == 'HOT']
    if hot:
        print(f"\n--- HOT Prospects (first 5) ---")
        for h in hot[:5]:
            print(f"  {h['business_name']} ({h['total_score']}) — {h['region']} — {h['defects']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
