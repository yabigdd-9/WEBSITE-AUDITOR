#!/usr/bin/env python3
"""Cross-check VERIFIED_HIGH emails against Hunter.io email_verifier."""
import json
import os
import sqlite3
import sys
from pathlib import Path

# Setup paths
PROJECT_DIR = Path("/Users/dd/WEBSITE-AUDITOR")
DB_PATH = PROJECT_DIR / "database" / "money_machine.db"
REPORT_PATH = PROJECT_DIR / "reports" / "hunter-verifier-crosscheck.md"

# Add money-machine module to path
sys.path.insert(0, str(PROJECT_DIR / "money-machine"))

# Load .env
env_path = PROJECT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# Import the hunter_enrichment module
import hunter_enrichment as he

# Cache directory for Hunter results
CACHE_DIR = PROJECT_DIR / ".cache"

def main():
    # Query VERIFIED_HIGH emails
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    d = conn.cursor()

    rows = d.execute("""
        SELECT c.id as candidate_id, c.normalized_email, c.prospect_id, b.name
        FROM email_candidates c
        JOIN email_verifications v ON v.candidate_id=c.id
        JOIN businesses b ON b.id=c.prospect_id
        WHERE v.confidence_label='VERIFIED_HIGH'
        ORDER BY b.name, c.normalized_email
    """).fetchall()

    print(f"Found {len(rows)} VERIFIED_HIGH emails to cross-check")

    results = []
    for i, row in enumerate(rows):
        email = row["normalized_email"]
        business = row["name"]
        our_label = "VERIFIED_HIGH"

        print(f"[{i+1}/{len(rows)}] Verifying: {email} ({business})...")

        try:
            hunter_result = he.email_verifier(email, cache_dir=str(CACHE_DIR))
        except Exception as e:
            print(f"  ERROR: {e}")
            hunter_result = None

        if hunter_result is None:
            result_entry = {
                "email": email,
                "business": business,
                "our_label": our_label,
                "hunter_result": "API_ERROR",
                "hunter_score": None,
                "smtp_check": None,
                "disposable": None,
                "block": None,
                "agreement": "ERROR",
                "from_cache": False,
            }
        else:
            hr = hunter_result.get("result", "unknown")
            score = hunter_result.get("score")
            smtp = hunter_result.get("smtp_check")
            disp = hunter_result.get("disposable")
            block = hunter_result.get("block")
            from_cache = hunter_result.get("from_cache", False)

            # Determine agreement
            # VERIFIED_HIGH means we're confident it's deliverable
            # Hunter: deliverable = agree, undeliverable = disagree, risky/unknown = partial
            if hr == "deliverable":
                agreement = "✅ AGREE"
            elif hr == "undeliverable":
                agreement = "❌ DISAGREE"
            elif hr == "risky":
                agreement = "⚠️ RISKY"
            elif hr == "unknown":
                agreement = "❓ UNKNOWN"
            else:
                agreement = f"❓ {hr.upper()}"

            result_entry = {
                "email": email,
                "business": business,
                "our_label": our_label,
                "hunter_result": hr,
                "hunter_score": score,
                "smtp_check": smtp,
                "disposable": disp,
                "block": block,
                "agreement": agreement,
                "from_cache": from_cache,
            }

            cache_note = " (cached)" if from_cache else ""
            print(f"  Result: {hr}, score={score}, smtp={smtp}{cache_note}")

        results.append(result_entry)

    conn.close()

    # Generate report
    report_lines = []
    report_lines.append("# Hunter.io Email Verifier Cross-Check Report")
    report_lines.append("")
    report_lines.append(f"**Generated:** {he.utcnow()}")
    report_lines.append(f"**Total VERIFIED_HIGH emails:** {len(results)}")
    report_lines.append("")

    # Summary stats
    agrees = sum(1 for r in results if "AGREE" in r["agreement"])
    disagrees = sum(1 for r in results if "DISAGREE" in r["agreement"])
    risky = sum(1 for r in results if "RISKY" in r["agreement"])
    unknown = sum(1 for r in results if "UNKNOWN" in r["agreement"] or "ERROR" in r["agreement"])

    report_lines.append("## Summary")
    report_lines.append("")
    report_lines.append(f"| Category | Count |")
    report_lines.append(f"|----------|-------|")
    report_lines.append(f"| ✅ Agree (deliverable) | {agrees} |")
    report_lines.append(f"| ❌ Disagree (undeliverable) | {disagrees} |")
    report_lines.append(f"| ⚠️ Risky | {risky} |")
    report_lines.append(f"| ❓ Unknown/Error | {unknown} |")
    report_lines.append("")

    if agrees + disagrees > 0:
        agreement_rate = agrees / (agrees + disagrees) * 100
        report_lines.append(f"**Agreement rate:** {agreement_rate:.1f}% ({agrees}/{agrees + disagrees})")
        report_lines.append("")

    # Detailed results table
    report_lines.append("## Detailed Results")
    report_lines.append("")
    report_lines.append("| Email | Business | Our Label | Hunter Result | Score | SMTP | Disposable | Block | Agreement |")
    report_lines.append("|-------|----------|-----------|---------------|-------|------|------------|-------|-----------|")

    for r in results:
        score_str = str(r["hunter_score"]) if r["hunter_score"] is not None else "N/A"
        smtp_str = "✅" if r["smtp_check"] else ("❌" if r["smtp_check"] is not None else "N/A")
        disp_str = "⚠️ Yes" if r["disposable"] else ("No" if r["disposable"] is not None else "N/A")
        block_str = "⚠️ Yes" if r["block"] else ("No" if r["block"] is not None else "N/A")

        report_lines.append(
            f"| {r['email']} | {r['business']} | {r['our_label']} | "
            f"{r['hunter_result']} | {score_str} | {smtp_str} | {disp_str} | {block_str} | {r['agreement']} |"
        )

    report_lines.append("")

    # Disagreements section (if any)
    if disagrees > 0:
        report_lines.append("## ⚠️ Disagreements (Hunter says undeliverable)")
        report_lines.append("")
        report_lines.append("These emails are marked VERIFIED_HIGH by our system but Hunter.io flags them as undeliverable.")
        report_lines.append("Manual review recommended.")
        report_lines.append("")
        for r in results:
            if "DISAGREE" in r["agreement"]:
                report_lines.append(f"- **{r['email']}** ({r['business']}) — Hunter score: {r['hunter_score']}")
        report_lines.append("")

    # Risky section
    if risky > 0:
        report_lines.append("## ⚠️ Risky Emails")
        report_lines.append("")
        report_lines.append("Hunter flagged these as risky — proceed with caution.")
        report_lines.append("")
        for r in results:
            if "RISKY" in r["agreement"]:
                report_lines.append(f"- **{r['email']}** ({r['business']}) — Hunter score: {r['hunter_score']}")
        report_lines.append("")

    # Write report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(report_lines))
    print(f"\nReport saved to: {REPORT_PATH}")

    # Also save raw results as JSON for programmatic access
    json_path = PROJECT_DIR / "reports" / "hunter-verifier-crosscheck.json"
    json_path.write_text(json.dumps(results, indent=2))
    print(f"Raw data saved to: {json_path}")

if __name__ == "__main__":
    main()
