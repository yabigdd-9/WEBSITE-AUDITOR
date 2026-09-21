#!/usr/bin/env python3
"""
Baseline metrics collection for prospect discovery through email drafting workflow.
Measures current performance to establish improvement targets.
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

def measure_prospect_discovery():
    """Measure prospect discovery and ingestion metrics."""
    print("=== PROSPECT DISCOVERY & INGESTION METRICS ===")

    # Check Money Machine database
    db_path = Path("database/money_machine.db")
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Count businesses by state
        try:
            states_query = """
                SELECT pi.state, COUNT(*) as count
                FROM pipeline_items pi
                JOIN businesses b ON pi.business_id = b.id
                WHERE b.is_dummy = 0
                GROUP BY pi.state
                ORDER BY count DESC
            """
            states = conn.execute(states_query).fetchall()

            print("Businesses by pipeline state:")
            total = 0
            for row in states:
                print(f"  {row['state']}: {row['count']}")
                total += row['count']
            print(f"Total businesses: {total}")

            # Check recent activity
            recent_query = """
                SELECT COUNT(*) as count
                FROM pipeline_items pi
                JOIN businesses b ON pi.business_id = b.id
                WHERE b.is_dummy = 0
                AND pi.updated_at > datetime('now', '-24 hours')
            """
            recent = conn.execute(recent_query).fetchone()
            print(f"Businesses updated in last 24h: {recent['count']}")

        except Exception as e:
            print(f"Error querying pipeline: {e}")
        finally:
            conn.close()
    else:
        print("Money Machine database not found")

def measure_audit_reuse():
    """Measure audit result reuse and comparison effectiveness."""
    print("\n=== AUDIT RESULT REUSE METRICS ===")

    # Check Website Auditor outputs
    outputs_dir = Path("outputs/toolkit")
    if outputs_dir.exists():
        audit_dirs = [d for d in outputs_dir.iterdir() if d.is_dir() and len(d.name) >= 20]  # Timestamped dirs
        print(f"Total audit runs: {len(audit_dirs)}")

        if audit_dirs:
            # Sort by modification time (newest first)
            audit_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # Check most recent audit for comparison data
            latest = audit_dirs[0]
            report_file = latest / "report.json"
            if report_file.exists():
                try:
                    with open(report_file) as f:
                        report = json.load(f)

                    comparison = report.get('comparison', {})
                    print(f"Latest audit run: {latest.name}")
                    print(f"  Status: {report.get('status')}")
                    print(f"  Health score: {report.get('health_score')}")
                    print(f"  Defect count: {report.get('defect_count')}")
                    print(f"  Comparison available: {'comparison' in report}")

                    if comparison:
                        print(f"  New defects: {len(comparison.get('new', []))}")
                        print(f"  Persistent defects: {len(comparison.get('persistent', []))}")
                        print(f"  Regressed defects: {len(comparison.get('regressed', []))}")
                        print(f"  Resolved defects: {len(comparison.get('resolved', []))}")

                except Exception as e:
                    print(f"Error reading audit report: {e}")
            else:
                print("No report.json found in latest audit")
        else:
            print("No audit runs found")
    else:
        print("Website Auditor outputs directory not found")

def measure_email_drafting():
    """Measure email drafting and personalization metrics."""
    print("\n=== EMAIL DRAFTING & PERSONALIZATION METRICS ===")

    # Check for draft-message.txt files in recent audit outputs
    outputs_dir = Path("outputs/toolkit")
    if outputs_dir.exists():
        draft_files = list(outputs_dir.rglob("draft-message.txt"))
        print(f"Email drafts found: {len(draft_files)}")

        if draft_files:
            # Check most recent draft
            latest_draft = max(draft_files, key=lambda x: x.stat().st_mtime)
            try:
                with open(latest_draft) as f:
                    content = f.read()

                # Basic metrics
                lines = content.count('\n')
                words = len(content.split())
                chars = len(content)

                print(f"Latest draft: {latest_draft.parent.name}")
                print(f"  Lines: {lines}")
                print(f"  Words: {words}")
                print(f"  Characters: {chars}")

                # Check for personalization markers
                personalization_markers = ['{domain}', '{defect_count}', '{score}', '{name}', '{top_3_defects}']
                found_markers = [marker for marker in personalization_markers if marker in content]
                print(f"  Personalization markers found: {len(found_markers)}/{len(personalization_markers)}")
                if found_markers:
                    print(f"    Markers: {', '.join(found_markers)}")

                # Check for evidence references
                evidence_indicators = ['I noticed', 'specific point', 'limited browser review', 'haven’t measured']
                found_evidence = [indicator for indicator in evidence_indicators if indicator.lower() in content.lower()]
                print(f"  Evidence-based language indicators: {len(found_evidence)}/{len(evidence_indicators)}")

            except Exception as e:
                print(f"Error reading draft: {e}")
        else:
            print("No email drafts found")
    else:
        print("Outputs directory not found")

def measure_quality_checks():
    """Measure current quality check coverage."""
    print("\n=== QUALITY CHECK METRICS ===")

    # Test outreach copy auditing
    try:
        # Import the audit function
        import sys
        sys.path.append('money-machine')
        from mm_outreach import audit_copy

        # Test with a basic draft
        test_draft = """Subject: Website improvement opportunity for Acme Corp

Hello Acme Corp team,

I'm reaching out because I noticed some specific points during a limited review of your website that could improve your enquiry flow.

Would it be useful to discuss these findings?

Best regards,
Dion
If this isn’t relevant, reply “no thanks” and I’ll leave it there."""

        result = audit_copy(test_draft, initial=True)
        print("Outreach copy audit test:")
        print(f"  Passed: {result['passed']}")
        print(f"  Errors: {result['errors']}")
        print(f"  Warnings: {result['warnings']}")
        print(f"  Word count: {result['word_count']}")

    except Exception as e:
        print(f"Error testing outreach audit: {e}")

def main():
    """Collect all baseline metrics."""
    print("WEBSITE AUDITOR - BASELINE METRICS COLLECTION")
    print("=" * 50)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    measure_prospect_discovery()
    measure_audit_reuse()
    measure_email_drafting()
    measure_quality_checks()

    print("\n" + "=" * 50)
    print("Baseline metrics collection complete.")
    print("Save these results to establish improvement targets.")

if __name__ == "__main__":
    main()