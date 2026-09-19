#!/usr/bin/env python3
"""
NZBN Bulk Data Consumer — Canterbury Prospect List Builder
=========================================================

Consumes Companies Office bulk data CSV files (19 files, zipped, monthly snapshot)
and filters to Canterbury-region small businesses with websites.

REQUIRES: Approved NZBN bulk data access from Companies Office.
          Apply at: https://www.companiesoffice.govt.nz/data-services/ways-to-get-our-data/bulk-data/
          Files download from: Box.com shared folder (link provided after approval)

Usage:
    python3 consume_nzbn_bulk.py --zip /path/to/companies-office-bulk-data.zip --output outputs/T003_NZBN_CANTERBURY_PROSPECTS.csv

Files consumed from the zip:
    - companies_core_data.csv           (entity name, type, status)
    - companies_public_address.csv      (public delivery/office/postal address)
    - companies_trading_name.csv        (trading names)
    - companies_website.csv             (website URLs — KEY FILTER)
    - companies_business_industry_classification.csv  (BIC codes)
    - companies_trading_area.csv        (trading regions)

Filtering logic:
    1. companies_website.csv → keep only rows with non-null website
    2. companies_core_data.csv → filter to NZBNs with status='Registered', entity_type IN ('NZ Limited Company', etc.)
    3. companies_public_address.csv → join on NZBN, filter to Canterbury postcodes (80xx, 81xx, 7xx for wider Canterbury)
    4. Exclude: public_sector_entities, enterprises (multi-location), insolvent entities

Postcode regions (Canterbury):
    - Christchurch: 8011-8025, 8041-8053, 8061-8062, 8081-8083, 8140-8149
    - Wider Canterbury: 74xx-79xx (Timaru, Ashburton, Rangiora, etc.)
    - All start with 7xxx or 8xxx
"""

import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path

# Canterbury postcode prefixes (first 2 digits)
CANTERBURY_PREFIXES = {'74', '75', '76', '77', '78', '79', '80', '81', '82', '83', '84', '85', '86', '87', '88', '89'}

# Entity types that are valid targets (small businesses)
VALID_ENTITY_TYPES = {
    'NZ Limited Company',
    'NZ Overseas Company',
    'NZ Statutory Company',
    'NZ Trustee Company',
    'NZ Unlimited Company',
    'Overseas Company',
    'ASIC Company',  # sometimes NZ-registered
}

# Entity statuses to include
VALID_STATUSES = {'Registered'}

# Target BIC industry descriptions (local-search-dependent, small business fit)
# We include ALL industries but mark target sectors for scoring
TARGET_INDUSTRIES = {
    'construction', 'trade', 'plumbing', 'electrical', 'painting', 'landscaping',
    'roofing', 'flooring', 'carpentry', 'hvac', 'automotive', 'dentist', 'medical',
    'veterinary', 'legal', 'accounting', 'consulting', 'real estate', 'insurance',
    'hospitality', 'restaurant', 'cafe', 'retail', 'beauty', 'hairdressing',
    'fitness', 'photography', 'printing', 'cleaning', 'pest control',
}


def load_csv_from_zip(zip_path: Path, filename: str) -> list[dict]:
    """Read a CSV file from within the zip archive."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        # Find the file (case-insensitive match)
        matches = [n for n in zf.namelist() if n.lower().endswith(filename.lower())]
        if not matches:
            print(f"  WARNING: {filename} not found in zip", file=sys.stderr)
            return []
        with zf.open(matches[0]) as f:
            content = f.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))
            return list(reader)


def postcode_is_canterbury(postcode: str) -> bool:
    """Check if a postcode is in Canterbury region."""
    if not postcode:
        return False
    cleaned = postcode.strip().replace(' ', '')
    if len(cleaned) >= 4:
        return cleaned[:2] in CANTERBURY_PREFIXES
    return False


def consume_bulk_data(zip_path: Path, output_path: Path) -> dict:
    """
    Main consumption logic. Returns stats dict.
    """
    stats = {
        'total_companies': 0,
        'with_website': 0,
        'canterbury_with_website': 0,
        'active_small_business': 0,
        'final_candidates': 0,
    }

    print(f"Loading bulk data from: {zip_path}")

    # 1. Load core data (all companies)
    print("\n[1/6] Loading companies_core_data.csv ...")
    core_data = load_csv_from_zip(zip_path, 'companies_core_data.csv')
    stats['total_companies'] = len(core_data)
    print(f"  Total companies in bulk data: {len(core_data)}")

    # Build NZBN → core record map
    core_by_nzbn = {}
    for row in core_data:
        nzbn = row.get('NZBN', '').strip()
        if nzbn:
            core_by_nzbn[nzbn] = row

    # 2. Load websites — this is our primary filter (must have website)
    print("\n[2/6] Loading companies_website.csv ...")
    websites = load_csv_from_zip(zip_path, 'companies_website.csv')
    stats['with_website'] = len(websites)
    print(f"  Companies with website: {len(websites)}")

    # Build NZBN → website map
    websites_by_nzbn = {}
    for row in websites:
        nzbn = row.get('NZBN', '').strip()
        website = row.get('WEBSITE', '').strip() if 'WEBSITE' in row else row.get('VALUE', '').strip()
        if nzbn and website:
            websites_by_nzbn[nzbn] = website.lower().lstrip('https://').lstrip('http://').lstrip('www.')

    # 3. Load public addresses — for Canterbury filtering
    print("\n[3/6] Loading companies_public_address.csv ...")
    addresses = load_csv_from_zip(zip_path, 'companies_public_address.csv')
    print(f"  Public addresses: {len(addresses)}")

    # Build NZBN → address map
    address_by_nzbn = {}
    for row in addresses:
        nzbn = row.get('NZBN', '').strip()
        postcode = row.get('ADDRESS_POSTCODE', '').strip() if 'ADDRESS_POSTCODE' in row else ''
        city = row.get('ADDRESS_3', '').strip() if 'ADDRESS_3' in row else ''
        if nzbn:
            if nzbn not in address_by_nzbn:
                address_by_nzbn[nzbn] = {'postcode': postcode, 'city': city}

    # 4. Load trading names
    print("\n[4/6] Loading companies_trading_name.csv ...")
    trading_names = load_csv_from_zip(zip_path, 'companies_trading_name.csv')
    trading_by_nzbn = {}
    for row in trading_names:
        nzbn = row.get('NZBN', '').strip()
        name = row.get('VALUE', '').strip() if 'VALUE' in row else ''
        if nzbn and name:
            if nzbn not in trading_by_nzbn:
                trading_by_nzbn[nzbn] = name

    # 5. Load industry classifications
    print("\n[5/6] Loading companies_business_industry_classification.csv ...")
    industries = load_csv_from_zip(zip_path, 'companies_business_industry_classification.csv')
    industry_by_nzbn = {}
    for row in industries:
        nzbn = row.get('NZBN', '').strip()
        desc = row.get('INDUSTRY_CLASSIFICATION_DESCRIPTION', '').strip() if 'INDUSTRY_CLASSIFICATION_DESCRIPTION' in row else ''
        code = row.get('INDUSTRY_CLASSIFICATION_CODE', '').strip() if 'INDUSTRY_CLASSIFICATION_CODE' in row else ''
        if nzbn and desc:
            if nzbn not in industry_by_nzbn:
                industry_by_nzbn[nzbn] = {'description': desc, 'code': code}

    # 6. Filter and output
    print("\n[6/6] Filtering to Canterbury prospects with websites ...")
    candidates = []

    for nzbn, website in websites_by_nzbn.items():
        # Must have core record
        core = core_by_nzbn.get(nzbn)
        if not core:
            continue

        # Must be registered
        status = core.get('ENTITY_STATUS', '').strip()
        if status not in VALID_STATUSES:
            continue

        # Must be valid entity type
        entity_type = core.get('ENTITY_TYPE', '').strip()
        if entity_type not in VALID_ENTITY_TYPES:
            continue

        # Must be in Canterbury
        addr = address_by_nzbn.get(nzbn, {})
        if not postcode_is_canterbury(addr.get('postcode', '')):
            continue

        stats['canterbury_with_website'] += 1

        # Determine industry
        industry = industry_by_nzbn.get(nzbn, {'description': '', 'code': ''})

        # Determine if target industry
        is_target = any(t in industry.get('description', '').lower() for t in TARGET_INDUSTRIES)

        candidate = {
            'nzbn': nzbn,
            'company_name': core.get('ENTITY_NAME', '').strip(),
            'trading_name': trading_by_nzbn.get(nzbn, ''),
            'entity_type': entity_type,
            'website': website,
            'postcode': addr.get('postcode', ''),
            'city': addr.get('city', ''),
            'industry_description': industry.get('description', ''),
            'industry_code': industry.get('code', ''),
            'target_industry': 'YES' if is_target else 'NO',
            'source': 'companies_office_bulk_data',
        }
        candidates.append(candidate)
        stats['final_candidates'] += 1

    # Sort: target industry first, then by company name
    candidates.sort(key=lambda c: (0 if c['target_industry'] == 'YES' else 1, c['company_name']))

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['nzbn', 'company_name', 'trading_name', 'entity_type', 'website',
                  'postcode', 'city', 'industry_description', 'industry_code',
                  'target_industry', 'source']

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidates)

    print(f"\n✓ Wrote {len(candidates)} candidates to: {output_path}")

    # Print summary
    target_count = sum(1 for c in candidates if c['target_industry'] == 'YES')
    print(f"\n--- Summary ---")
    print(f"Total companies in bulk data: {stats['total_companies']}")
    print(f"With website: {stats['with_website']}")
    print(f"Canterbury + website: {stats['canterbury_with_website']}")
    print(f"Final candidates (active, small business): {stats['final_candidates']}")
    print(f"Target industry: {target_count}")

    return stats


def main():
    parser = argparse.ArgumentParser(description='NZBN Bulk Data Consumer — Canterbury Prospects')
    parser.add_argument('--zip', required=True, help='Path to Companies Office bulk data zip file')
    parser.add_argument('--output', default='outputs/T003_NZBN_CANTERBURY_PROSPECTS.csv',
                        help='Output CSV path')
    args = parser.parse_args()

    zip_path = Path(args.zip)
    if not zip_path.exists():
        print(f"ERROR: Zip file not found: {zip_path}", file=sys.stderr)
        sys.exit(1)

    stats = consume_bulk_data(zip_path, Path(args.output))
    return 0 if stats['final_candidates'] > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
