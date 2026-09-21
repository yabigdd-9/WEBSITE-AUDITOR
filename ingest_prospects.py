#!/usr/bin/env python3
"""
Enhanced prospect ingestion script with improved CSV parsing, URL normalization, and deduplication.
Addresses point 2 of the user's improvement plan.
"""

import csv
import json
import sys
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import hashlib

# Add money-machine to path for imports
sys.path.append('money-machine')
from mm_core import public_url, connect, now
from mm_pipeline import enqueue


def normalize_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize and validate a URL using the existing public_url function.
    Returns (normalized_domain, error_message)
    """
    try:
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        domain = public_url(url)
        return domain, None
    except ValueError as e:
        return None, str(e)
    except Exception as e:
        return None, f"URL parsing error: {str(e)}"


def parse_csv_file(file_path: Path) -> List[Dict[str, str]]:
    """
    Parse CSV file with robust error handling and flexible column detection.
    """
    prospects = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Try to detect dialect
            sample = f.read(1024)
            f.seek(0)
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample)
                f.seek(0)
                reader = csv.DictReader(f, dialect=dialect)
            except csv.Error:
                # Fallback to default comma-separated
                f.seek(0)
                reader = csv.DictReader(f)

            # Normalize column names (lowercase, strip whitespace)
            if reader.fieldnames:
                reader.fieldnames = [col.strip().lower() for col in reader.fieldnames]

            for row_num, row in enumerate(reader, start=2):  # Start at 2 for header row
                # Clean row data
                cleaned_row = {k.strip(): v.strip() if isinstance(v, str) else v
                             for k, v in row.items()}
                cleaned_row['_row_num'] = row_num
                prospects.append(cleaned_row)

    except Exception as e:
        print(f"Error parsing CSV file {file_path}: {e}")
        return []

    return prospects


def deduplicate_prospects(prospects: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Deduplicate prospects by normalized URL and business name.
    Returns (unique_prospects, duplicates)
    """
    seen = {}
    unique_prospects = []
    duplicates = []

    for prospect in prospects:
        # Create a key for deduplication
        url = prospect.get('url') or prospect.get('website') or prospect.get('website_url')
        name = prospect.get('name') or prospect.get('business_name') or prospect.get('company')

        if not url:
            # Skip prospects without URL
            duplicates.append({**prospect, '_dedup_reason': 'Missing URL'})
            continue

        # Normalize URL for deduplication
        normalized_domain, error = normalize_url(url)
        if error:
            duplicates.append({**prospect, '_dedup_reason': f'Invalid URL: {error}'})
            continue

        # Create deduplication key
        key = (normalized_domain, name.lower() if name else '')

        if key in seen:
            duplicates.append({**prospect, '_dedup_reason': f'Duplicate of row {seen[key]}'})
        else:
            seen[key] = prospect.get('_row_num', 'unknown')
            # Add normalized domain to prospect for later use
            prospect['normalized_domain'] = normalized_domain
            unique_prospects.append(prospect)

    return unique_prospects, duplicates


def ingest_prospects(csv_file_path: str, source: str = "csv_import") -> Dict:
    """
    Main function to ingest prospects from CSV file.
    """
    file_path = Path(csv_file_path)
    if not file_path.exists():
        return {"error": f"File not found: {csv_file_path}"}

    print(f"Loading prospects from {file_path}...")
    prospects = parse_csv_file(file_path)

    if not prospects:
        return {"error": "No prospects found in CSV file"}

    print(f"Found {len(prospects)} raw prospects")

    # Deduplicate
    unique_prospects, duplicates = deduplicate_prospects(prospects)
    print(f"After deduplication: {len(unique_prospects)} unique, {len(duplicates)} duplicates")

    if duplicates:
        print("Duplicates found:")
        for dup in duplicates[:5]:  # Show first 5 duplicates
            print(f"  Row {dup.get('_row_num', '?')}: {dup.get('_dedup_reason', 'Unknown reason')}")
        if len(duplicates) > 5:
            print(f"  ... and {len(duplicates) - 5} more")

    # Process unique prospects
    conn = connect()
    ingested = 0
    errors = []

    try:
        for prospect in unique_prospects:
            try:
                # Extract fields with flexible naming
                url = prospect.get('url') or prospect.get('website') or prospect.get('website_url')
                name = prospect.get('name') or prospect.get('business_name') or prospect.get('company')
                region = prospect.get('region') or prospect.get('location') or prospect.get('country')

                if not url or not name:
                    errors.append(f"Missing required fields for prospect: {prospect}")
                    continue

                # Normalize URL (already done in deduplication, but double-check)
                normalized_domain, error = normalize_url(url)
                if error:
                    errors.append(f"Invalid URL for {name}: {error}")
                    continue

                # Insert or update business
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO businesses (name, public_website, region, source, discovered_at, is_dummy, current_status)
                    VALUES (?, ?, ?, ?, ?, 0, 'discovered')
                """, (name, normalized_domain, region, source, now()))

                business_id = cursor.lastrowid
                if business_id == 0:
                    # Business already exists, get its ID
                    cursor = conn.execute(
                        "SELECT id FROM businesses WHERE public_website = ? AND name = ?",
                        (normalized_domain, name)
                    )
                    row = cursor.fetchone()
                    if row:
                        business_id = row[0]
                    else:
                        errors.append(f"Could not find or create business for {name}")
                        continue

                # Enqueue in pipeline at DISCOVERED state
                enqueue(conn, business_id, state='DISCOVERED',
                       payload={"source": source, "import_url": url})
                ingested += 1

            except Exception as e:
                errors.append(f"Error processing prospect {prospect.get('name', 'Unknown')}: {str(e)}")

        conn.commit()

    except Exception as e:
        conn.rollback()
        return {"error": f"Database error during ingestion: {str(e)}"}
    finally:
        conn.close()

    return {
        "ingested": ingested,
        "errors": len(errors),
        "error_details": errors[:10] if errors else [],  # Limit error details
        "duplicates_found": len(duplicates),
        "unique_prospects": len(unique_prospects),
        "total_raw": len(prospects)
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 ingest_prospects.py <csv_file> [source]")
        print("Example: python3 ingest_prospects.py prospects.csv 'weekly_upload'")
        sys.exit(1)

    csv_file = sys.argv[1]
    source = sys.argv[2] if len(sys.argv) > 2 else "csv_import"

    result = ingest_prospects(csv_file, source)

    print("\n=== INGESTION RESULTS ===")
    print(json.dumps(result, indent=2))

    if "error" in result:
        sys.exit(1)
    elif result["errors"] > 0:
        print(f"\nCompleted with {result['errors']} errors")
        sys.exit(0 if result["ingested"] > 0 else 1)
    else:
        print(f"\nSuccessfully ingested {result['ingested']} prospects")
        sys.exit(0)


if __name__ == "__main__":
    main()