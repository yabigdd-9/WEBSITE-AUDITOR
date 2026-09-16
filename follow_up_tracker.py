#!/usr/bin/env python3
"""Follow-Up Tracker — Daily call/email list + visual pipeline board.

Usage:
    python3 follow_up_tracker.py
    python3 follow_up_tracker.py --generate
    python3 follow_up_tracker.py --web
"""
import argparse, json, re
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"
FOLLOW_UP_DB = ROOT / "outputs" / "follow-up.json"


def load_follow_up_db() -> dict:
    """Load follow-up database."""
    if FOLLOW_UP_DB.exists():
        return json.loads(FOLLOW_UP_DB.read_text())
    return {"contacts": [], "last_updated": datetime.now().isoformat()}


def save_follow_up_db(data: dict):
    """Save follow-up database."""
    FOLLOW_UP_DB.parent.mkdir(parents=True, exist_ok=True)
    FOLLOW_UP_DB.write_text(json.dumps(data, indent=2, default=str))


def generate_from_leads():
    """Generate follow-up list from existing lead scoring."""
    from lead_scoring import score_all
    
    leads = score_all()
    contacts = []
    
    for lead in leads:
        # Determine last contact (simulated)
        days_ago = max(0, 21 - int(lead["composite_score"] / 5))
        last_contact = (datetime.now() - timedelta(days=days_ago)).isoformat()
        
        # Determine next action
        if lead["tier"] == "HOT":
            next_action = "Call today"
            next_date = datetime.now().isoformat()
        elif lead["tier"] == "WARM":
            next_action = "Call or email"
            next_date = (datetime.now() + timedelta(days=2)).isoformat()
        elif lead["tier"] == "NURTURE":
            next_action = "Send email"
            next_date = (datetime.now() + timedelta(days=7)).isoformat()
        else:
            next_action = "Add to newsletter"
            next_date = (datetime.now() + timedelta(days=30)).isoformat()
        
        contacts.append({
            "domain": lead["domain"],
            "name": lead["prospect_name"],
            "tier": lead["tier"],
            "score": lead["composite_score"],
            "last_contact": last_contact,
            "next_action": next_action,
            "next_date": next_date,
            "notes": f"Top defect: {lead['top_defects'][0] if lead['top_defects'] else 'N/A'}",
            "contact_info": {
                "emails": lead.get("emails", []),
                "phone": lead.get("phone", ""),
                "social": lead.get("social", []),
            },
            "history": [],
        })
    
    db = {
        "contacts": contacts,
        "last_updated": datetime.now().isoformat(),
    }
    save_follow_up_db(db)
    return db


def get_today_list(db: dict) -> list:
    """Get contacts due for follow-up today."""
    today = datetime.now().date()
    due = []
    
    for contact in db.get("contacts", []):
        next_date = datetime.fromisoformat(contact.get("next_date", "2000-01-01")).date()
        if next_date <= today:
            due.append(contact)
    
    # Sort by score descending
    due.sort(key=lambda x: x.get("score", 0), reverse=True)
    return due


def generate_html(db: dict, today_list: list) -> str:
    """Generate follow-up pipeline HTML."""
    
    # Pipeline stages
    stages = {
        "AUDIT": [],
        "CONTACTED": [],
        "QUOTED": [],
        "WON": [],
        "LOST": [],
    }
    
    for contact in db.get("contacts", []):
        # Simulate stage based on tier
        tier = contact.get("tier", "COLD")
        if tier == "HOT":
            stages["CONTACTED"].append(contact)
        elif tier == "WARM":
            stages["AUDIT"].append(contact)
        else:
            stages["AUDIT"].append(contact)
    
    # Pipeline cards
    pipeline_html = ""
    for stage, contacts in stages.items():
        cards = ""
        for c in contacts:
            cards += f"""
            <div class="pipeline-card">
                <div class="card-domain">{c['domain']}</div>
                <div class="card-tier tier-{c['tier'].lower()}">{c['tier']}</div>
                <div class="card-score">{c['score']:.0f}/100</div>
                <div class="card-next">{c['next_action']}</div>
            </div>"""
        
        pipeline_html += f"""
        <div class="pipeline-stage">
            <h3>{stage} <span class="count">({len(contacts)})</span></h3>
            <div class="stage-cards">
                {cards if cards else '<div class="empty">None</div>'}
            </div>
        </div>"""
    
    # Today's list
    today_rows = ""
    for contact in today_list:
        today_rows += f"""
        <tr>
            <td><strong>{contact['domain']}</strong></td>
            <td><span class="tier-{contact['tier'].lower()}">{contact['tier']}</span></td>
            <td>{contact['next_action']}</td>
            <td>{contact['notes']}</td>
            <td>{contact['contact_info']['emails'][0] if contact['contact_info']['emails'] else '—'}</td>
        </tr>"""
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Follow-Up Pipeline — CATALYX Labs</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; padding: 2em; max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #58a6ff; }}
h2 {{ color: #8b949e; border-bottom: 2px solid #30363d; padding-bottom: 0.3em; margin-top: 2em; }}
.pipeline {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1em; margin: 2em 0; }}
.pipeline-stage {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1em; }}
.pipeline-stage h3 {{ margin-top: 0; font-size: 0.9em; text-transform: uppercase; color: #8b949e; }}
.count {{ font-weight: normal; }}
.stage-cards {{ min-height: 100px; }}
.pipeline-card {{ background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 0.8em; margin: 0.5em 0; }}
.card-domain {{ font-weight: 600; font-size: 0.9em; }}
.card-tier {{ font-size: 0.75em; margin: 0.2em 0; }}
.tier-hot {{ color: #FF1A1A; }}
.tier-warm {{ color: #FF8A00; }}
.tier-nurture {{ color: #EFFF00; }}
.tier-cold {{ color: #8b949e; }}
.card-score {{ font-size: 0.85em; color: #58a6ff; }}
.card-next {{ font-size: 0.75em; color: #8b949e; }}
.empty {{ color: #666; font-style: italic; font-size: 0.85em; }}
.today-table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
.today-table th, .today-table td {{ padding: 10px; text-align: left; border-bottom: 1px solid #21262d; }}
.today-table th {{ background: #161b22; color: #8b949e; font-size: 0.8em; text-transform: uppercase; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1em; margin: 2em 0; }}
.stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1em; text-align: center; }}
.stat-val {{ font-size: 2em; font-weight: bold; color: #58a6ff; }}
.stat-label {{ font-size: 0.8em; color: #8b949e; }}
.footer {{ text-align: center; margin-top: 3em; padding-top: 1em; border-top: 2px solid #30363d; color: #666; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>📞 Follow-Up Pipeline</h1>
<p style="color:#8b949e">Last updated: {datetime.now().strftime('%d %b %Y %H:%M')}</p>

<div class="stats">
    <div class="stat">
        <div class="stat-val">{len(db.get('contacts', []))}</div>
        <div class="stat-label">Total Prospects</div>
    </div>
    <div class="stat">
        <div class="stat-val">{len(today_list)}</div>
        <div class="stat-label">Due Today</div>
    </div>
    <div class="stat">
        <div class="stat-val">{sum(1 for c in db.get('contacts', []) if c['tier'] == 'HOT')}</div>
        <div class="stat-label">HOT Leads</div>
    </div>
</div>

<h2>Pipeline</h2>
<div class="pipeline">
    {pipeline_html}
</div>

<h2>📋 Today's Follow-Ups</h2>
<table class="today-table">
    <thead>
        <tr>
            <th>Domain</th>
            <th>Tier</th>
            <th>Action</th>
            <th>Notes</th>
            <th>Contact</th>
        </tr>
    </thead>
    <tbody>
        {today_rows if today_rows else '<tr><td colspan="5" style="text-align:center;color:#666">Nothing due today</td></tr>'}
    </tbody>
</table>

<div class="footer">
    <p><strong>CATALYX Labs Ltd</strong> | team@catalyxlabs.shop</p>
</div>
</body>
</html>"""
    return html


def main():
    p = argparse.ArgumentParser(description="Follow-Up Tracker")
    p.add_argument("--generate", action="store_true", help="Generate from lead scoring")
    p.add_argument("--web", action="store_true", help="Generate HTML pipeline")
    p.add_argument("--output", "-o", default="outputs/follow-up.html", help="Output file")
    args = p.parse_args()
    
    if args.generate or not FOLLOW_UP_DB.exists():
        db = generate_from_leads()
        print(f"✅ Generated {len(db['contacts'])} contacts from lead scoring")
    else:
        db = load_follow_up_db()
    
    today_list = get_today_list(db)
    
    print(f"\n📞 Follow-Up Summary:")
    print(f"   Total contacts: {len(db['contacts'])}")
    print(f"   Due today: {len(today_list)}")
    
    if today_list:
        print(f"\n   Today's list:")
        for c in today_list[:5]:
            print(f"   - {c['domain']} ({c['tier']}): {c['next_action']}")
    
    output = generate_html(db, today_list)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(output)
    print(f"\n   ✅ Pipeline saved: {args.output}")


if __name__ == "__main__":
    main()
