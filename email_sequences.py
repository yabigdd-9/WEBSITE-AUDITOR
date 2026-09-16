#!/usr/bin/env python3
"""Email Sequence Generator — Personalized outreach based on audit findings.

Generates multi-step email sequences:
- Day 0: Introduction + audit summary
- Day 3: Specific defect alert + ROI
- Day 7: Case study / social proof
- Day 14: Final follow-up + urgency
- Day 21: Breakup email

Usage:
    python3 email_sequences.py <audit.json>
    python3 email_sequences.py --batch audits/
    python3 email_sequences.py --domain example.com --score 45
    python3 email_sequences.py --template day3 <audit.json>
"""
import argparse, json, re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"

# ── Email Templates ──────────────────────────────────────────────
TEMPLATES = {
    "day0": {
        "subject": "Quick audit for {domain} — {defect_count} issues found",
        "preview": "Your website has {defect_count} issues costing you leads...",
        "body": "Hi {name},\n\nI ran a free audit on {domain} and found {defect_count} issues that are likely costing you leads and customers.\n\nHealth Score: {score}/100\n\nThe top 3 problems:\n{top_3_defects}\n\nThese aren't just \"nice to have\" fixes — each one directly impacts your bottom line.\n\nI've put together a free before/after mockup showing what your site could look like with these issues fixed.\n\nWorth a 10-minute call?\n\n— Dion\nCATALYX Labs\ncatalyxlabs.shop",
    },
    "day3": {
        "subject": "Re: {domain} audit — one critical issue",
        "preview": "This one issue could be costing you ${estimated_loss}/month...",
        "body": "Hi {name},\n\nQuick follow-up on the {domain} audit.\n\nThe most urgent issue: {top_defect}\n\n{top_defect_impact}\n\nBased on industry averages, this alone could be costing you approximately ${estimated_loss}/month in lost leads.\n\nFor {domain}, with {monthly_visitors} monthly visitors, even a small improvement means real revenue.\n\nThe fix typically takes {fix_time} and costs ${fix_cost}.\n\nWorth fixing?\n\n— Dion",
    },
    "day7": {
        "subject": "How we helped {similar_business} get +{improvement}% leads",
        "preview": "Real results from a similar business...",
        "body": "Hi {name},\n\nWe recently worked with a {industry} business in NZ that had similar issues to {domain}.\n\nTheir score went from {before_score}/100 to {after_score}/100.\n\nResults:\n• +{improvement}% more leads within 30 days\n• Page load time cut in half\n• Mobile conversions up {mobile_boost}%\n\nThe full case study is here: [link]\n\nI think we could get similar results for {domain}. Want to see what that would look like?\n\n— Dion",
    },
    "day14": {
        "subject": "{domain} audit expiring soon",
        "preview": "Your free quote expires in 7 days...",
        "body": "Hi {name},\n\nThe free audit and quote for {domain} expires on {expiry_date}.\n\nAfter that, the ${quote_total} estimate goes back to full price.\n\nIf you're interested, just reply and I'll lock in the current rate.\n\nNo pressure either way — if the timing isn't right, I understand.\n\n— Dion",
    },
    "day21": {
        "subject": "Last note about {domain}",
        "preview": "Should I close your file?",
        "body": "Hi {name},\n\nI don't want to be that person who keeps emailing.\n\nShould I close your file for now? If the timing isn't right, no hard feelings.\n\nIf you ever want to revisit the {domain} audit, just reach out.\n\nGood luck with the business!\n\n— Dion\n\nP.S. — The free before/after mockup is still available if you want it.",
    },
}


def generate_sequence(audit: dict, recipient_name: str = "there") -> dict:
    """Generate complete email sequence from audit data."""
    domain = audit.get("domain", "unknown")
    score = audit.get("score", 0)
    defects = audit.get("defects", [])
    defect_count = audit.get("defect_count", 0)
    
    # Top 3 defects for day 0
    top_3 = "\n".join(f"• {d.get('defect', '')} — {d.get('impact', '')}" for d in defects[:3])
    
    # Top defect for day 3
    top_defect = defects[0].get("defect", "multiple issues") if defects else "multiple issues"
    top_defect_impact = defects[0].get("impact", "") if defects else ""
    
    # Revenue estimate
    monthly_visitors = audit.get("evidence", {}).get("monthly_visitors", 500)
    avg_order = 150
    current_conversion = 0.015
    estimated_monthly_loss = int(monthly_visitors * current_conversion * avg_order * 0.15)  # 15% improvement potential
    
    # Fix time and cost
    from quote_engine import estimate_cost, calculate_roi
    fix_cost = sum(estimate_cost(d.get("defect", ""))["estimate"] for d in defects)
    fix_time = "48-72 hours" if score < 50 else "1-2 weeks"
    
    # Similar business (generic but personalized by industry)
    from lead_scoring import detect_industry
    industry = detect_industry(audit)
    
    # Generate sequence
    sequence = {}
    day_offsets = {"day0": 0, "day3": 3, "day7": 7, "day14": 14, "day21": 21}
    
    for day_key, template in TEMPLATES.items():
        send_date = datetime.now() + timedelta(days=day_offsets[day_key])
        
        # Personalize subject and body with audit data
        format_args = {
            "domain": domain,
            "defect_count": defect_count,
            "score": score,
            "name": recipient_name,
            "top_3_defects": top_3,
            "top_defect": top_defect,
            "top_defect_impact": top_defect_impact,
            "estimated_loss": estimated_monthly_loss,
            "monthly_visitors": monthly_visitors,
            "fix_time": fix_time,
            "fix_cost": fix_cost,
            "similar_business": f"a local {industry} company",
            "industry": industry,
            "before_score": score,
            "after_score": min(score + 30, 95),
            "improvement": 25,
            "mobile_boost": 40,
            "expiry_date": (datetime.now() + timedelta(days=14)).strftime('%d %b %Y'),
            "quote_total": fix_cost,
        }
        
        subject = template["subject"].format(**format_args)
        body = template["body"].format(**format_args)
        
        sequence[day_key] = {
            "day": day_offsets[day_key],
            "send_date": send_date.strftime('%Y-%m-%d'),
            "subject": subject,
            "body": body,
        }
    
    return sequence


def generate_html(sequence: dict, audit: dict, output_path: str) -> str:
    """Generate HTML preview of email sequence."""
    domain = audit.get("domain", "unknown")
    
    emails_html = ""
    for day_key, email in sequence.items():
        emails_html += f"""
        <div class="email-card">
            <div class="email-header">
                <span class="day-badge">Day {email['day']}</span>
                <span class="send-date">{email['send_date']}</span>
            </div>
            <div class="email-subject"><strong>Subject:</strong> {email['subject']}</div>
            <div class="email-body">
                <pre>{email['body']}</pre>
            </div>
        </div>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Email Sequence: {domain}</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; padding: 2em; max-width: 800px; margin: 0 auto; }}
h1 {{ color: #58a6ff; }}
.intro {{ color: #8b949e; margin-bottom: 2em; }}
.email-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; }}
.email-header {{ display: flex; justify-content: space-between; margin-bottom: 1em; }}
.day-badge {{ background: #003366; color: #fff; padding: 4px 12px; border-radius: 12px; font-size: 0.8em; }}
.send-date {{ color: #8b949e; font-size: 0.85em; }}
.email-subject {{ margin-bottom: 1em; padding-bottom: 0.5em; border-bottom: 1px solid #21262d; }}
.email-body pre {{ white-space: pre-wrap; font-family: inherit; line-height: 1.6; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>📧 Email Sequence for {domain}</h1>
<p class="intro">5-email sequence over 21 days — personalized based on audit findings</p>

{emails_html}
</body>
</html>"""
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html)
    return output_path


def main():
    p = argparse.ArgumentParser(description="Email Sequence Generator")
    p.add_argument("audit_file", nargs="?", help="Path to audit JSON file")
    p.add_argument("--batch", metavar="DIR", help="Generate sequences for all audits")
    p.add_argument("--domain", help="Domain name (for manual entry)")
    p.add_argument("--score", type=int, help="Health score")
    p.add_argument("--defects", type=int, help="Number of defects")
    p.add_argument("--name", default="there", help="Recipient first name")
    p.add_argument("--output", "-o", help="Output HTML path")
    args = p.parse_args()
    
    if args.audit_file:
        data = json.loads(Path(args.audit_file).read_text())
        domain = data.get("domain", "unknown")
        output_path = args.output or f"outputs/emails_{domain}.html"
        
        sequence = generate_sequence(data, args.name)
        generate_html(sequence, data, output_path)
        
        print(f"✅ Email sequence saved: {output_path}")
        print(f"\n   Sequence preview:")
        for day_key, email in sequence.items():
            print(f"   Day {email['day']:2d}: {email['subject'][:50]}...")
        
    elif args.batch:
        audits_dir = Path(args.batch)
        for aj in sorted(audits_dir.glob("*.json")):
            data = json.loads(aj.read_text())
            domain = data.get("domain", aj.stem)
            output_path = f"outputs/emails_{domain}.html"
            sequence = generate_sequence(data)
            generate_html(sequence, data, output_path)
            print(f"✅ Sequence: {domain} → {output_path}")
            
    else:
        p.print_help()


if __name__ == "__main__":
    main()
