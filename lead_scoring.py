#!/usr/bin/env python3
"""Lead Scoring & Prioritization Engine — Rank prospects by conversion probability.

Scoring signals (0-100 each):
- Urgency (health score defects: expired SSL, no contact form, broken stuff)
- Revenue potential (domain age, word count, social presence, page count)
- Accessibility (email found, phone found, contact page exists)
- Pain level (number of defects, performance issues)
- Digital awareness (has analytics, social profiles, blog)

Output tiers:
🔥 HOT (80-100): Call today — clear pain + reachable + budget
⚡ WARM (60-79): Call this week — good potential, may need nurturing
🌱 NURTURE (40-59): Email sequence — not urgent but worth tracking
❄️ COLD (0-39): Low priority — no email, low pain, hard to reach

Usage:
    python3 lead_scoring.py
    python3 lead_scoring.py --min-score 60
    python3 lead_scoring.py --export call-list.json
    python3 lead_scoring.py --web
"""
import argparse, json, re
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"
PROSPECTS_CSV = ROOT / "prospects.csv"

# Industry weights (higher = easier to close)
INDUSTRY_WEIGHTS = {
    "construction": 1.2,
    "roofing": 1.3,
    "plumbing": 1.2,
    "electrical": 1.2,
    "landscaping": 1.1,
    "painting": 1.1,
    "cleaning": 1.0,
    "hvac": 1.2,
    "concrete": 1.1,
    "fencing": 1.0,
    "kitchen": 1.3,
    "bathroom": 1.3,
    "flooring": 1.2,
    "decking": 1.1,
    "plastering": 1.0,
    "tiling": 1.0,
    "glass": 1.1,
    "security": 1.2,
    "locksmith": 1.2,
    "pest": 1.1,
    "moving": 1.0,
    "storage": 1.0,
    "accounting": 0.9,
    "legal": 0.8,
    "dental": 1.1,
    "medical": 1.0,
    "vet": 1.0,
    "hairdressing": 1.0,
    "beauty": 1.0,
    "fitness": 1.1,
    "real estate": 1.2,
    "property": 1.1,
    "insurance": 0.9,
    "finance": 0.8,
    "education": 0.8,
    "childcare": 0.9,
    "automotive": 1.1,
    "marine": 1.0,
    "travel": 0.9,
    "hospitality": 1.0,
    "retail": 1.0,
    "ecommerce": 1.1,
    "technology": 0.9,
}

# NZ regions (higher = more affluent/easier to close)
REGION_WEIGHTS = {
    "auckland": 1.2,
    "wellington": 1.1,
    "christchurch": 1.1,
    "queenstown": 1.3,
    "hamilton": 1.0,
    "tauranga": 1.1,
    "dunedin": 0.9,
    "nelson": 1.0,
    "napier": 1.0,
    "palmerston north": 0.9,
    "new plymouth": 0.9,
    "whangarei": 0.9,
    "invercargill": 0.8,
}


def load_prospects():
    """Load prospect metadata from CSV."""
    prospects = {}
    if PROSPECTS_CSV.exists():
        for line in PROSPECTS_CSV.read_text().splitlines()[1:]:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                _id, name, url = parts[0], parts[1], parts[2]
                m = re.search(r'(?:https?://)?(?:www\.)?([^/]+)', url)
                if m:
                    domain = m.group(1).replace("www.", "")
                    prospects[domain] = {
                        "id": _id,
                        "name": name,
                        "url": url,
                        "phone": parts[3] if len(parts) > 3 else "",
                        "email": parts[4] if len(parts) > 4 else "",
                        "notes": parts[5] if len(parts) > 5 else "",
                    }
    return prospects


def detect_industry(audit: dict) -> str:
    """Detect industry from title, description, and domain."""
    text = " ".join(filter(None, [
        audit.get("meta", {}).get("title", ""),
        audit.get("meta", {}).get("meta_description", ""),
        audit.get("domain", ""),
        " ".join(d.get("defect", "") for d in audit.get("defects", [])),
    ])).lower()
    
    industries = {
        "roofing": ["roof", "roofing", "roofer"],
        "plumbing": ["plumb", "plumber", "drain"],
        "electrical": ["electric", "electrical", "sparky"],
        "construction": ["construct", "builder", "building", "contract"],
        "landscaping": ["landscape", "garden", "gardening"],
        "painting": ["paint", "painter"],
        "cleaning": ["clean", "cleaning", "cleaners"],
        "hvac": ["hvac", "air conditioning", "heating", "ventilation"],
        "concrete": ["concrete", "concreting"],
        "fencing": ["fenc", "fence"],
        "kitchen": ["kitchen", "benchtop", "cabinet"],
        "bathroom": ["bathroom", "renovation", "tiling"],
        "flooring": ["floor", "flooring", "carpet", "timber"],
        "decking": ["deck", "decking", "timber deck"],
        "glazier": ["glass", "glazier", "window", "mirror"],
        "security": ["security", "alarm", "cctv", "surveillance"],
        "locksmith": ["lock", "locksmith"],
        "pest": ["pest", "exterminat"],
        "moving": ["moving", "removals", "removal"],
        "accounting": ["account", "tax", "bookkeeping"],
        "dental": ["dental", "dentist"],
        "hairdressing": ["hair", "salon", "barber"],
        "fitness": ["fitness", "gym", "personal training"],
        "real estate": ["real estate", "property", "homes"],
        "automotive": ["automotive", "mechanic", "car", "vehicle"],
        "dental": ["dental", "dentist", "orthodontist"],
    }
    
    for industry, keywords in industries.items():
        if any(kw in text for kw in keywords):
            return industry
    return "general"


def score_urgency(audit: dict) -> tuple:
    """Score urgency (0-100). Higher = more urgent = call first."""
    score = 0
    reasons = []
    defects = audit.get("defects", [])
    evidence = audit.get("evidence", {})
    
    # Critical defects (immediate pain)
    for d in defects:
        text = d.get("defect", "").lower()
        if "expired ssl" in text:
            score += 25
            reasons.append("🔴 Expired SSL")
        elif "no contact form" in text:
            score += 20
            reasons.append("🔴 No contact form")
        elif "broken link" in text:
            score += 10
            reasons.append("🟠 Broken links")
        elif "slow performance" in text:
            score += 15
            reasons.append("🔴 Slow site")
        elif "noindex" in text:
            score += 25
            reasons.append("🔴 Noindexed from search")
        elif "thin content" in text:
            score += 10
            reasons.append("🟠 Thin content")
        elif "missing privacy" in text:
            score += 5
            reasons.append("🟡 No privacy policy")
    
    # Scale by number of defects (more defects = more pain)
    defect_count = audit.get("defect_count", 0)
    if defect_count >= 10:
        score += 15
    elif defect_count >= 5:
        score += 10
    elif defect_count >= 3:
        score += 5
    
    return min(score, 100), reasons


def score_revenue_potential(audit: dict) -> tuple:
    """Score revenue potential (0-100). Higher = more $ to be made."""
    score = 0
    reasons = []
    evidence = audit.get("evidence", {})
    
    # Social presence (active businesses have budget)
    social = evidence.get("social_links", [])
    if len(social) >= 4:
        score += 25
        reasons.append(f"🟢 {len(social)} social profiles (active)")
    elif len(social) >= 2:
        score += 15
        reasons.append(f"🟢 {len(social)} social profiles")
    elif len(social) >= 1:
        score += 5
    
    # Word count (content-rich sites = bigger businesses)
    wc = evidence.get("word_count", 0)
    if wc > 2000:
        score += 20
        reasons.append(f"🟢 {wc} words (content-rich)")
    elif wc > 500:
        score += 10
        reasons.append(f"🟢 {wc} words")
    elif wc > 200:
        score += 5
    
    # Has analytics (digitally aware)
    # Can't detect from audit data alone, but infer from social + content
    
    # Schema.org (savvy site owners)
    schema = evidence.get("schema_org", {})
    if schema.get("count", 0) > 0:
        score += 15
        reasons.append("🟢 Has structured data")
    
    # Sitemap exists (organized)
    if evidence.get("sitemap", {}).get("exists"):
        score += 10
        reasons.append("🟢 Has sitemap")
    
    # Domain signals
    domain = audit.get("domain", "")
    if any(tld in domain for tld in [".co.nz", ".nz"]):
        score += 10
        reasons.append("🟢 NZ domain (local market)")
    
    # Email found (business legitimacy)
    emails = evidence.get("emails", [])
    if len(emails) >= 2:
        score += 15
        reasons.append(f"🟢 {len(emails)} emails found")
    elif len(emails) >= 1:
        score += 10
        reasons.append(f"🟢 {len(emails)} email found")
    
    return min(score, 100), reasons


def score_accessibility(audit: dict, prospect: dict) -> tuple:
    """Score how easy they are to reach (0-100). Higher = easier contact."""
    score = 0
    reasons = []
    evidence = audit.get("evidence", {})
    
    # Has email from audit
    emails = evidence.get("emails", [])
    if emails:
        score += 40
        reasons.append(f"📧 {emails[0]}")
    
    # Prospect metadata has phone
    if prospect.get("phone"):
        score += 30
        reasons.append(f"📞 {prospect['phone']}")
    
    # Prospect metadata has email
    if prospect.get("email"):
        score += 20
        reasons.append(f"📧 {prospect['email']}")
    
    # Has social (can DM them)
    social = evidence.get("social_links", [])
    if social:
        score += 10
        reasons.append(f"📱 {', '.join(social[:3])}")
    
    return min(score, 100), reasons


def score_digital_awareness(audit: dict) -> tuple:
    """Score how digitally aware the business is (0-100). Higher = they'll get it."""
    score = 0
    reasons = []
    evidence = audit.get("evidence", {})
    
    # Has analytics-like setup
    social = evidence.get("social_links", [])
    if len(social) >= 3:
        score += 25
        reasons.append("Active on social media")
    
    # Has structured data
    schema = evidence.get("schema_org", {})
    if schema.get("count", 0) > 0:
        score += 25
        reasons.append("Uses Schema.org (tech-savvy)")
    
    # Has sitemap
    if evidence.get("sitemap", {}).get("exists"):
        score += 15
        reasons.append("Has sitemap (organized)")
    
    # Has multiple emails
    emails = evidence.get("emails", [])
    if len(emails) >= 3:
        score += 15
        reasons.append("Multiple team emails")
    
    # Domain age proxy
    domain = audit.get("domain", "")
    if domain and not domain.startswith("www."):
        score += 5
    
    # HTTPS working
    defects = audit.get("defects", [])
    has_ssl_issues = any("ssl" in d.get("defect", "").lower() for d in defects)
    if not has_ssl_issues:
        score += 15
        reasons.append("SSL properly configured")
    
    return min(score, 100), reasons


def calculate_lead_score(audit: dict, prospect: dict) -> dict:
    """Calculate composite lead score with component breakdowns."""
    urgency, urgency_reasons = score_urgency(audit)
    revenue, revenue_reasons = score_revenue_potential(audit)
    accessibility, access_reasons = score_accessibility(audit, prospect)
    awareness, awareness_reasons = score_digital_awareness(audit)
    
    # Industry weight
    industry = detect_industry(audit)
    industry_weight = INDUSTRY_WEIGHTS.get(industry, 1.0)
    
    # Composite score (weighted)
    composite = (
        urgency * 0.35 +          # Pain matters most
        revenue * 0.25 +          # Budget matters
        accessibility * 0.25 +    # Can we reach them?
        awareness * 0.15          # Will they understand?
    ) * industry_weight
    
    composite = min(composite, 100)
    
    # Tier assignment
    if composite >= 70:
        tier = "HOT"
        emoji = "🔥"
        action = "CALL TODAY"
        color = "#FF1A1A"
    elif composite >= 50:
        tier = "WARM"
        emoji = "⚡"
        action = "CALL THIS WEEK"
        color = "#FF8A00"
    elif composite >= 30:
        tier = "NURTURE"
        emoji = "🌱"
        action = "EMAIL SEQUENCE"
        color = "#EFFF00"
    else:
        tier = "COLD"
        emoji = "❄️"
        action = "LOW PRIORITY"
        color = "#8b949e"
    
    return {
        "domain": audit.get("domain", ""),
        "prospect_name": prospect.get("name", ""),
        "url": audit.get("url", ""),
        "industry": industry,
        "health_score": audit.get("score", 0),
        "defect_count": audit.get("defect_count", 0),
        "composite_score": round(composite, 1),
        "tier": tier,
        "tier_emoji": emoji,
        "action": action,
        "color": color,
        "breakdown": {
            "urgency": round(urgency, 1),
            "revenue_potential": round(revenue, 1),
            "accessibility": round(accessibility, 1),
            "digital_awareness": round(awareness, 1),
        },
        "industry_weight": industry_weight,
        "evidence": {
            "urgency": urgency_reasons,
            "revenue": revenue_reasons,
            "accessibility": access_reasons,
            "awareness": awareness_reasons,
        },
        "top_defects": [d.get("defect") for d in audit.get("defects", [])[:5]],
        "emails": audit.get("evidence", {}).get("emails", []),
        "social": audit.get("evidence", {}).get("social_links", []),
        "phone": prospect.get("phone", ""),
    }


def score_all(min_score: float = 0) -> list:
    """Score all audited prospects."""
    prospects = load_prospects()
    leads = []
    
    for aj in sorted(AUDITS.glob("*.json")):
        try:
            audit = json.loads(aj.read_text())
            domain = audit.get("domain", "").replace("www.", "")
            
            # Find matching prospect
            prospect = prospects.get(domain, {
                "id": "",
                "name": domain,
                "url": audit.get("url", ""),
                "phone": "",
                "email": "",
                "notes": "",
            })
            
            lead = calculate_lead_score(audit, prospect)
            
            if lead["composite_score"] >= min_score:
                leads.append(lead)
        except Exception:
            continue
    
    # Sort by composite score descending (highest = call first)
    leads.sort(key=lambda x: x["composite_score"], reverse=True)
    return leads


def print_leads(leads: list):
    """Print formatted lead list."""
    print("\n" + "="*80)
    print("  📊 LEAD SCORING & PRIORITIZATION")
    print("="*80)
    print(f"\n  Total scored: {len(leads)} leads\n")
    
    for i, lead in enumerate(leads, 1):
        print(f"  {lead['tier_emoji']} #{i} {lead['domain']} — {lead['composite_score']}/100 ({lead['tier']})")
        print(f"     Health: {lead['health_score']}/100 | Defects: {lead['defect_count']} | Industry: {lead['industry']}")
        print(f"     Action: {lead['action']}")
        
        # Top evidence
        evidence_parts = []
        if lead["evidence"]["urgency"]:
            evidence_parts.append(lead["evidence"]["urgency"][0])
        if lead["evidence"]["accessibility"]:
            evidence_parts.append(lead["evidence"]["accessibility"][0])
        if evidence_parts:
            print(f"     Key signals: {' | '.join(evidence_parts[:2])}")
        
        if lead["emails"]:
            print(f"     📧 {lead['emails'][0]}")
        if lead["phone"]:
            print(f"     📞 {lead['phone']}")
        print()
    
    # Tier distribution
    tiers = Counter(l["tier"] for l in leads)
    print("  Tier Distribution:")
    for tier in ["HOT", "WARM", "NURTURE", "COLD"]:
        count = tiers.get(tier, 0)
        emoji = {"HOT": "🔥", "WARM": "⚡", "NURTURE": "🌱", "COLD": "❄️"}[tier]
        print(f"    {emoji} {tier}: {count}")


def generate_html(leads: list, output_path: str) -> str:
    """Generate HTML lead board."""
    rows = ""
    for i, lead in enumerate(leads, 1):
        # Evidence badges
        badges = ""
        for reason in lead["evidence"]["urgency"][:2]:
            badges += f'<span class="badge urgency">{reason}</span> '
        for reason in lead["evidence"]["accessibility"][:1]:
            badges += f'<span class="badge contact">{reason}</span> '
        
        rows += f"""
        <tr>
            <td><strong>#{i}</strong></td>
            <td>
                <div class="domain">{lead['domain']}</div>
                <div class="name">{lead['prospect_name']}</div>
            </td>
            <td>
                <div class="score-pill" style="background:{lead['color']}">
                    {lead['composite_score']}
                </div>
            </td>
            <td><span class="tier-badge {lead['tier'].lower()}">{lead['tier_emoji']} {lead['tier']}</span></td>
            <td><span class="action">{lead['action']}</span></td>
            <td>
                <div class="defect-count">{lead['health_score']}/100</div>
                <small>{lead['defect_count']} defects</small>
            </td>
            <td>{badges}</td>
            <td>
                <div class="emails">{'<br>'.join(lead['emails'][:2])}</div>
                {'<div class="phone">' + lead['phone'] + '</div>' if lead['phone'] else ''}
            </td>
        </tr>"""
    
    tier_counts = Counter(l["tier"] for l in leads)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lead Board — CATALYX Labs</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; padding: 2em; }}
h1 {{ color: #58a6ff; margin-bottom: 0.2em; }}
.meta {{ color: #8b949e; margin-bottom: 2em; }}
.stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1em; margin-bottom: 2em; }}
.stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1em; text-align: center; }}
.stat-val {{ font-size: 1.8em; font-weight: bold; }}
.stat-label {{ font-size: 0.75em; color: #8b949e; }}
.hot {{ color: #FF1A1A; }}
.warm {{ color: #FF8A00; }}
.nurture {{ color: #EFFF00; }}
.cold {{ color: #8b949e; }}
table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #21262d; vertical-align: top; }}
th {{ background: #161b22; color: #8b949e; font-size: 0.8em; text-transform: uppercase; }}
tr:hover {{ background: #161b22; }}
.domain {{ font-weight: 600; color: #58a6ff; }}
.name {{ font-size: 0.8em; color: #8b949e; }}
.score-pill {{ display: inline-block; padding: 4px 10px; border-radius: 12px; font-weight: bold; color: #0d1117; font-size: 0.9em; }}
.tier-badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.75em; font-weight: bold; }}
.tier-badge.hot {{ background: #FF1A1A; color: #fff; }}
.tier-badge.warm {{ background: #FF8A00; color: #fff; }}
.tier-badge.nurture {{ background: #EFFF00; color: #1a1a2e; }}
.tier-badge.cold {{ background: #30363d; color: #8b949e; }}
.action {{ font-size: 0.85em; color: #58a6ff; font-weight: 600; }}
.defect-count {{ font-weight: bold; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.7em; margin: 1px 0; }}
.badge.urgency {{ background: #FF1A1A33; color: #FF1A1A; }}
.badge.contact {{ background: #00D4A333; color: #00D4A3; }}
.emails {{ font-family: monospace; font-size: 0.85em; }}
.phone {{ font-size: 0.85em; color: #00D4A3; }}
</style>
</head>
<body>
<h1>📊 Lead Scoring Board</h1>
<p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | {len(leads)} leads scored</p>

<div class="stats">
    <div class="stat"><div class="stat-val hot">{tier_counts.get('HOT', 0)}</div><div class="stat-label">🔥 HOT (Call Today)</div></div>
    <div class="stat"><div class="stat-val warm">{tier_counts.get('WARM', 0)}</div><div class="stat-label">⚡ WARM (This Week)</div></div>
    <div class="stat"><div class="stat-val nurture">{tier_counts.get('NURTURE', 0)}</div><div class="stat-label">🌱 NURTURE (Email)</div></div>
    <div class="stat"><div class="stat-val cold">{tier_counts.get('COLD', 0)}</div><div class="stat-label">❄️ COLD (Low Prio)</div></div>
</div>

<table>
<thead>
<tr>
    <th>#</th>
    <th>Prospect</th>
    <th>Score</th>
    <th>Tier</th>
    <th>Action</th>
    <th>Health</th>
    <th>Key Signals</th>
    <th>Contact</th>
</tr>
</thead>
<tbody>
    {rows}
</tbody>
</table>

<p style="margin-top:2em; color:#8b949e; font-size:0.8em">
    Scoring: urgency 35% + revenue 25% + accessibility 25% + awareness 15%, weighted by industry
</p>
</body>
</html>"""
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html)
    return output_path


def main():
    p = argparse.ArgumentParser(description="Lead Scoring & Prioritization")
    p.add_argument("--min-score", type=float, default=0, help="Minimum score to display")
    p.add_argument("--export", "-e", help="Export to JSON file")
    p.add_argument("--web", action="store_true", help="Generate HTML lead board")
    p.add_argument("--output", "-o", default="outputs/lead-board.html", help="HTML output path")
    args = p.parse_args()
    
    leads = score_all(args.min_score)
    print_leads(leads)
    
    if args.export:
        Path(args.export).parent.mkdir(parents=True, exist_ok=True)
        Path(args.export).write_text(json.dumps(leads, indent=2, default=str))
        print(f"\n  ✅ Exported: {args.export}")
    
    if args.web or args.output:
        generate_html(leads, args.output)
        print(f"  ✅ Lead board: {args.output}")
    
    return leads


if __name__ == "__main__":
    main()
