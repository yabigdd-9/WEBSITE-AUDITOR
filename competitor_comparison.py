#!/usr/bin/env python3
"""Competitor Comparison Report — Side-by-side audit comparison for client vs competitors.

Usage:
    python3 competitor_comparison.py --client clyne-bennie.co.nz --competitors prodecorators.co.nz,jcconstruction.co.nz
    python3 competitor_comparison.py --client example.com --competitors comp1.com,comp2.com,comp3.com --output reports/comparison.html
    python3 competitor_comparison.py --auto  # auto-detect from audits/
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
AUDITS_DIR = ROOT / "audits"
OUTPUTS_DIR = ROOT / "outputs"

# Industry detection (reused from lead_scoring.py)
INDUSTRY_KEYWORDS = {
    "roofing": ["roof", "roofing", "roofer"],
    "plumbing": ["plumb", "plumber", "drain", "gas fitting", "drainlayer"],
    "electrical": ["electric", "electrical", "sparky", "electrician"],
    "construction": ["construct", "builder", "building", "contract", "construction"],
    "landscaping": ["landscape", "garden", "gardening"],
    "painting": ["paint", "painter", "decorator", "decorating"],
    "cleaning": ["clean", "cleaning", "cleaners"],
    "hvac": ["hvac", "air conditioning", "heating", "ventilation", "heat pump"],
    "concrete": ["concrete", "concreting"],
    "fencing": ["fenc", "fence"],
    "kitchen": ["kitchen", "benchtop", "cabinet"],
    "bathroom": ["bathroom", "renovation", "tiling", "shower"],
    "flooring": ["floor", "flooring", "carpet", "timber", "vinyl"],
    "decking": ["deck", "decking", "timber deck"],
    "glazier": ["glass", "glazier", "window", "mirror", "double glazing"],
    "security": ["security", "alarm", "cctv", "surveillance", "camera"],
    "locksmith": ["lock", "locksmith"],
    "pest": ["pest", "exterminat"],
    "moving": ["moving", "removals", "removal"],
    "accounting": ["account", "tax", "bookkeeping", "chartered accountant"],
    "dental": ["dental", "dentist", "orthodontist"],
    "medical": ["medical", "doctor", "gp", "clinic", "health"],
    "vet": ["vet", "veterinary", "animal hospital"],
    "hairdressing": ["hair", "salon", "barber", "hairdress"],
    "beauty": ["beauty", "spa", "aesthetic", "facial"],
    "fitness": ["fitness", "gym", "personal training", "physio"],
    "real estate": ["real estate", "property", "homes", "realty"],
    "automotive": ["automotive", "mechanic", "car", "vehicle", "auto repair"],
    "marine": ["marine", "boat", "yacht", "ship"],
    "hospitality": ["restaurant", "cafe", "hotel", "accommodation", "hospitality"],
    "retail": ["retail", "shop", "store", "boutique"],
    "ecommerce": ["ecommerce", "online store", "shopify"],
    "technology": ["software", "tech", "digital", "web design", "development"],
    "legal": ["legal", "lawyer", "solicitor", "law firm"],
    "insurance": ["insurance", "broker", "underwriter"],
    "finance": ["finance", "mortgage", "financial advisor", "wealth"],
    "education": ["education", "school", "training", "course", "tutor"],
    "childcare": ["childcare", "daycare", "preschool", "early learning"],
}

# Defect category mappings for "Why This Matters" section
DEFECT_CATEGORIES = {
    "security": {
        "keywords": ["ssl", "hsts", "x-frame", "x-content", "referrer-policy", "permissions-policy", "csp", "content-security"],
        "title": "🔒 Security Headers",
        "why": "Missing security headers expose visitors to clickjacking, XSS attacks, and data leakage. Modern browsers penalize sites without HSTS, CSP, and frame protection. For NZ businesses handling customer data, this is a compliance and trust issue.",
    },
    "seo": {
        "keywords": ["h1", "title", "meta description", "canonical", "noindex", "open graph", "og:", "schema", "structured data", "sitemap", "robots"],
        "title": "🔍 SEO & Search Visibility",
        "why": "These defects directly impact how Google crawls, indexes, and ranks your pages. Missing H1, title, meta description, and structured data mean lower click-through rates from search results. For local NZ businesses, this means losing leads to competitors who rank higher.",
    },
    "performance": {
        "keywords": ["slow", "performance", "tfb", "ttfb", "lcp", "cls", "fid", "core web vitals", "image optimiz", "render blocking"],
        "title": "⚡ Performance & Core Web Vitals",
        "why": "Slow sites lose visitors before they load. Google uses Core Web Vitals as a ranking factor. Each second of delay drops conversion rates by ~20%. For service businesses, a slow site means potential customers call your faster competitor instead.",
    },
    "accessibility": {
        "keywords": ["alt", "contrast", "readability", "flesch", "aria", "keyboard", "screen reader", "wcag", "accessibility"],
        "title": "♿ Accessibility & Usability",
        "why": "1 in 4 NZ adults has a disability. Sites that fail WCAG basics (alt text, contrast, readable content) exclude customers and risk Human Rights Act complaints. Accessible sites also rank better and convert higher.",
    },
    "content": {
        "keywords": ["thin content", "word count", "broken link", "duplicate", "stale copyright", "html error", "w3c", "markup"],
        "title": "📝 Content Quality & Technical Health",
        "why": "Thin content (<300 words) signals low authority to Google. Broken links frustrate users and waste crawl budget. HTML errors cause rendering bugs across browsers. Regular content audits keep your site trustworthy and competitive.",
    },
    "conversion": {
        "keywords": ["contact form", "cta", "call to action", "phone", "email", "analytics", "tracking", "privacy", "terms"],
        "title": "💰 Conversion & Trust Signals",
        "why": "No contact form = no lead capture. Missing CTA = visitors don't know what to do next. No analytics = flying blind on marketing spend. Privacy/TOS pages build trust and are legally required for NZ businesses collecting data.",
    },
}


def detect_industry(audit: dict) -> str:
    """Detect industry from title, description, and domain (from lead_scoring.py)."""
    text = " ".join(filter(None, [
        audit.get("meta", {}).get("title", ""),
        audit.get("meta", {}).get("meta_description", ""),
        audit.get("domain", ""),
        " ".join(d.get("defect", "") for d in audit.get("defects", [])),
    ])).lower()

    for industry, keywords in INDUSTRY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return industry
    return "general"


def load_audit(domain: str) -> dict | None:
    """Load audit from file, handling www. prefix variations."""
    # Normalize domain
    domain = domain.replace("www.", "").strip().rstrip("/")
    
    # Try exact match first
    for ext in [".json"]:
        path = AUDITS_DIR / f"{domain}{ext}"
        if path.exists():
            return json.loads(path.read_text())
    
    # Try with www prefix
    for ext in [".json"]:
        path = AUDITS_DIR / f"www.{domain}{ext}"
        if path.exists():
            return json.loads(path.read_text())
    
    # Try fuzzy match (filesystem safe names)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", domain)
    for f in AUDITS_DIR.glob(f"*{safe}*.json"):
        return json.loads(f.read_text())
    
    return None


def categorize_defects(defects: list) -> dict:
    """Group defects by category for analysis."""
    categorized = {cat: [] for cat in DEFECT_CATEGORIES}
    categorized["other"] = []
    
    for defect in defects:
        text = defect.get("defect", "").lower()
        matched = False
        for cat, info in DEFECT_CATEGORIES.items():
            if any(kw in text for kw in info["keywords"]):
                categorized[cat].append(defect)
                matched = True
                break
        if not matched:
            categorized["other"].append(defect)
    
    return categorized


def get_gap_analysis(client: dict, competitors: list) -> dict:
    """Calculate gaps between client and competitors."""
    client_score = client.get("score", 0)
    client_defects = client.get("defect_count", 0)
    client_cats = categorize_defects(client.get("defects", []))
    
    comp_scores = [c.get("score", 0) for c in competitors]
    comp_defects = [c.get("defect_count", 0) for c in competitors]
    
    avg_comp_score = sum(comp_scores) / len(comp_scores) if comp_scores else 0
    avg_comp_defects = sum(comp_defects) / len(comp_defects) if comp_defects else 0
    best_comp_score = max(comp_scores) if comp_scores else 0
    best_comp_defects = min(comp_defects) if comp_defects else 0
    
    # Category gaps
    cat_gaps = {}
    for cat in DEFECT_CATEGORIES:
        client_count = len(client_cats.get(cat, []))
        comp_counts = [len(categorize_defects(c.get("defects", [])).get(cat, [])) for c in competitors]
        avg_comp_cat = sum(comp_counts) / len(comp_counts) if comp_counts else 0
        cat_gaps[cat] = {
            "client": client_count,
            "avg_competitor": round(avg_comp_cat, 1),
            "gap": round(client_count - avg_comp_cat, 1),
        }
    
    return {
        "score_gap": round(client_score - avg_comp_score, 1),
        "score_gap_best": round(client_score - best_comp_score, 1),
        "defect_gap": round(client_defects - avg_comp_defects, 1),
        "defect_gap_best": round(client_defects - best_comp_defects, 1),
        "category_gaps": cat_gaps,
        "client_score": client_score,
        "avg_competitor_score": round(avg_comp_score, 1),
        "best_competitor_score": best_comp_score,
        "client_defects": client_defects,
        "avg_competitor_defects": round(avg_comp_defects, 1),
        "best_competitor_defects": best_comp_defects,
    }


def get_score_color(score: int) -> str:
    """Get color for score gradient."""
    if score >= 80:
        return "linear-gradient(135deg, #00D4A3 0%, #00CFFF 100%)"
    elif score >= 60:
        return "linear-gradient(135deg, #EFFF00 0%, #FFD700 100%)"
    elif score >= 40:
        return "linear-gradient(135deg, #FF8A00 0%, #FFB340 100%)"
    else:
        return "linear-gradient(135deg, #FF1A1A 0%, #FF6B6B 100%)"


def get_score_tier(score: int) -> tuple:
    """Get tier label and color."""
    if score >= 80:
        return ("EXCELLENT", "#00D4A3")
    elif score >= 60:
        return ("GOOD", "#EFFF00")
    elif score >= 40:
        return ("NEEDS WORK", "#FF8A00")
    else:
        return ("CRITICAL", "#FF1A1A")


def format_gap(value: float, higher_is_better: bool = True) -> str:
    """Format gap with appropriate indicator."""
    if value > 0 and higher_is_better:
        return f"<span class='gap-positive'>+{value:.1f} ✓</span>"
    elif value < 0 and not higher_is_better:
        return f"<span class='gap-positive'>{value:.1f} ✓</span>"
    elif value > 0 and not higher_is_better:
        return f"<span class='gap-negative'>+{value:.1f} ✗</span>"
    elif value < 0 and higher_is_better:
        return f"<span class='gap-negative'>{value:.1f} ✗</span>"
    return "<span class='gap-neutral'>0</span>"


def generate_comparison_html(client: dict, competitors: list, gap: dict, industry: str) -> str:
    """Generate the side-by-side comparison HTML report."""
    
    # Prepare all sites data
    all_sites = [("Client", client, True)] + [(f"Competitor {i+1}", c, False) for i, c in enumerate(competitors)]
    
    # Build score cards
    score_cards = ""
    for label, site, is_client in all_sites:
        score = site.get("score", 0)
        tier, tier_color = get_score_tier(score)
        color = get_score_color(score)
        defect_count = site.get("defect_count", 0)
        domain = site.get("domain", "unknown")
        
        score_cards += f"""
        <div class="score-card" style="background: {color};">
            <div class="score-label">{label}</div>
            <div class="score-domain">{domain}</div>
            <div class="score-big">{score}/100</div>
            <div class="score-tier" style="background: {tier_color}; color: {'#000' if tier in ['GOOD', 'EXCELLENT'] else '#fff'};">{tier}</div>
            <div class="score-defects">{defect_count} defects</div>
        </div>"""
    
    # Build detailed comparison table
    table_rows = ""
    
    # Score row
    table_rows += f"""
    <tr class="metric-row score-row">
        <td class="metric-name">🏆 Health Score</td>
        <td class="metric-client"><strong>{client.get('score', 0)}/100</strong></td>"""
    for c in competitors:
        table_rows += f'<td class="metric-comp">{c.get("score", 0)}/100</td>'
    table_rows += f"""
        <td class="metric-gap">{format_gap(gap['score_gap'])}</td>
        <td class="metric-gap-best">{format_gap(gap['score_gap_best'])}</td>
    </tr>"""
    
    # Defect count row
    table_rows += f"""
    <tr class="metric-row defect-row">
        <td class="metric-name">🐛 Total Defects</td>
        <td class="metric-client"><strong>{client.get('defect_count', 0)}</strong></td>"""
    for c in competitors:
        table_rows += f'<td class="metric-comp">{c.get("defect_count", 0)}</td>'
    table_rows += f"""
        <td class="metric-gap">{format_gap(gap['defect_gap'], higher_is_better=False)}</td>
        <td class="metric-gap-best">{format_gap(gap['defect_gap_best'], higher_is_better=False)}</td>
    </tr>"""
    
    # Category rows
    for cat, info in DEFECT_CATEGORIES.items():
        client_cat = len(categorize_defects(client.get("defects", [])).get(cat, []))
        table_rows += f"""
        <tr class="metric-row category-row">
            <td class="metric-name">{info['title']}</td>
            <td class="metric-client"><strong>{client_cat}</strong></td>"""
        for c in competitors:
            comp_cat = len(categorize_defects(c.get("defects", [])).get(cat, []))
            table_rows += f'<td class="metric-comp">{comp_cat}</td>'
        cat_gap = gap["category_gaps"].get(cat, {"gap": 0})
        table_rows += f"""
            <td class="metric-gap">{format_gap(cat_gap['gap'], higher_is_better=False)}</td>
            <td class="metric-gap-best">{format_gap(cat_gap['gap'], higher_is_better=False)}</td>
        </tr>"""
    
    # Key defect details
    defect_details = ""
    for label, site, is_client in all_sites:
        defects = site.get("defects", [])
        if not defects:
            continue
        defect_details += f"""
        <div class="defect-column">
            <h4>{label}: {site.get('domain', 'unknown')}</h4>
            <ul class="defect-list">"""
        for d in defects[:10]:  # Top 10 defects
            defect_details += f"<li>{d.get('defect', '')}<br><small>{d.get('impact', '')}</small></li>"
        if len(defects) > 10:
            defect_details += f"<li class='more-defects'>... and {len(defects) - 10} more</li>"
        defect_details += """
            </ul>
        </div>"""
    
    # Why This Matters section
    why_matters = ""
    for cat, info in DEFECT_CATEGORIES.items():
        client_count = len(categorize_defects(client.get("defects", [])).get(cat, []))
        if client_count > 0:
            why_matters += f"""
            <div class="why-card">
                <h4>{info['title']}</h4>
                <p>{info['why']}</p>
                <div class="why-client-status">
                    <strong>Your site:</strong> {client_count} issue{'s' if client_count != 1 else ''} in this category
                </div>
            </div>"""
    
    # Industry-specific insights
    industry_insights = {
        "plumbing": "Plumbing customers search with high intent (emergency leaks, blocked drains). Mobile speed and click-to-call are critical. Missing H1/meta description = lost emergency calls.",
        "roofing": "Roofing is high-ticket ($10k+ jobs). Customers research heavily. Schema.org LocalBusiness + reviews + project gallery = trust signals that close deals.",
        "electrical": "Safety-sensitive trade. SSL, security headers, and compliance badges matter. Customers verify licenses online before calling.",
        "construction": "Long sales cycle. Portfolio, testimonials, and detailed service pages build authority. Thin content hurts perceived capability.",
        "painting": "Visual trade — image optimization and gallery schema are essential. Before/after photos with alt text drive quotes.",
        "hvac": "Seasonal demand spikes. Fast mobile load + emergency CTA + service area schema capture urgent heat pump/AC calls.",
        "landscaping": "Portfolio-driven. Image-heavy sites need optimization. Service area pages + project schema win local pack.",
    }
    
    industry_insight = industry_insights.get(industry, "General business: Fix critical defects first (security, SSL, contact form). Then optimize for local SEO with schema, reviews, and service area pages.")
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Competitor Comparison: {client.get('domain', 'unknown')}</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
* {{ box-sizing: border-box; }}
body {{ 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
    background: #0d1117; 
    color: #e6edf3; 
    margin: 0; 
    padding: 2em; 
    line-height: 1.6;
}}
.container {{ max-width: 1400px; margin: 0 auto; }}

.header {{
    display: flex; 
    justify-content: space-between; 
    align-items: center; 
    border-bottom: 3px solid #30363d; 
    padding-bottom: 1em; 
    margin-bottom: 2em;
}}
.logo {{ 
    font-size: 1.5em; 
    font-weight: 700; 
    background: linear-gradient(135deg, #58a6ff 0%, #a371f7 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.report-meta {{ text-align: right; color: #8b949e; }}
.report-meta strong {{ color: #e6edf3; }}

.score-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.5em;
    margin-bottom: 2em;
}}
.score-card {{
    border-radius: 12px;
    padding: 1.5em;
    color: #fff;
    text-align: center;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    transition: transform 0.2s;
}}
.score-card:hover {{ transform: translateY(-2px); }}
.score-label {{ font-size: 0.85em; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.5em; }}
.score-domain {{ font-size: 0.9em; opacity: 0.8; margin-bottom: 0.5em; word-break: break-all; }}
.score-big {{ font-size: 3.5em; font-weight: 700; line-height: 1; margin: 0.5em 0; }}
.score-tier {{ display: inline-block; padding: 6px 16px; border-radius: 20px; font-size: 0.8em; font-weight: 600; margin-bottom: 0.5em; }}
.score-defects {{ font-size: 0.9em; opacity: 0.9; }}

.comparison-table {{
    width: 100%;
    border-collapse: collapse;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 2em;
}}
.comparison-table th,
.comparison-table td {{
    padding: 14px 16px;
    text-align: left;
    border-bottom: 1px solid #21262d;
    vertical-align: middle;
}}
.comparison-table th {{
    background: #161b22;
    color: #8b949e;
    font-size: 0.75em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
    position: sticky;
    top: 0;
    z-index: 1;
}}
.comparison-table tr:last-child td {{ border-bottom: none; }}
.comparison-table tr:hover {{ background: #1c2128; }}

.metric-name {{ 
    font-weight: 500; 
    min-width: 220px;
    background: #161b22;
}}
.metric-client {{ 
    background: rgba(88, 166, 255, 0.1);
    font-weight: 600;
}}
.metric-comp {{ text-align: center; }}
.metric-gap, .metric-gap-best {{ 
    text-align: center; 
    font-weight: 600; 
    font-size: 0.9em;
}}
.gap-positive {{ color: #3fb950; }}
.gap-negative {{ color: #f85149; }}
.gap-neutral {{ color: #8b949e; }}

.category-row .metric-name {{
    color: #8b949e;
    font-weight: 400;
    padding-left: 2em;
    font-size: 0.9em;
}}
.score-row .metric-name, .defect-row .metric-name {{
    font-weight: 700;
    color: #f0f6fc;
}}

.section {{
    margin: 2.5em 0;
}}
.section h2 {{
    color: #58a6ff;
    border-bottom: 2px solid #30363d;
    padding-bottom: 0.5em;
    margin-bottom: 1.5em;
    font-size: 1.4em;
}}

.defect-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1.5em;
}}
.defect-column {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1.5em;
}}
.defect-column h4 {{
    color: #58a6ff;
    margin-top: 0;
    margin-bottom: 1em;
    padding-bottom: 0.5em;
    border-bottom: 1px solid #30363d;
    font-size: 1em;
}}
.defect-list {{ list-style: none; padding: 0; margin: 0; }}
.defect-list li {{
    padding: 0.75em 0;
    border-bottom: 1px solid #21262d;
    font-size: 0.85em;
}}
.defect-list li:last-child {{ border-bottom: none; }}
.defect-list small {{ color: #8b949e; display: block; margin-top: 0.25em; }}
.more-defects {{ color: #8b949e; font-style: italic; }}

.why-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
    gap: 1.5em;
}}
.why-card {{
    background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 1.5em;
    border-left: 4px solid #58a6ff;
}}
.why-card h4 {{
    margin: 0 0 0.75em 0;
    color: #58a6ff;
    font-size: 1em;
}}
.why-card p {{
    margin: 0 0 1em 0;
    color: #c9d1d9;
    font-size: 0.9em;
    line-height: 1.7;
}}
.why-client-status {{
    font-size: 0.85em;
    color: #f85149;
    padding: 0.75em;
    background: rgba(248, 81, 73, 0.1);
    border-radius: 6px;
    border: 1px solid rgba(248, 81, 73, 0.2);
}}

.industry-insight {{
    background: linear-gradient(135deg, #1f2a3a 0%, #161b22 100%);
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 1.5em;
    border-left: 4px solid #a371f7;
}}
.industry-insight h3 {{
    margin: 0 0 1em 0;
    color: #a371f7;
    font-size: 1.1em;
}}
.industry-insight p {{
    margin: 0;
    color: #c9d1d9;
    line-height: 1.7;
}}

.footer {{
    margin-top: 3em;
    padding-top: 1.5em;
    border-top: 2px solid #30363d;
    text-align: center;
    color: #8b949e;
    font-size: 0.85em;
}}
.footer strong {{ color: #e6edf3; }}

@media print {{
    body {{ padding: 0; background: #fff; color: #1a1a2e; }}
    .score-card {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .comparison-table th {{ background: #f0f0f0 !important; -webkit-print-color-adjust: exact; }}
    .metric-client {{ background: #e8f0fe !important; -webkit-print-color-adjust: exact; }}
    .why-card {{ border-left-color: #003366 !important; -webkit-print-color-adjust: exact; }}
    .industry-insight {{ border-left-color: #6600cc !important; -webkit-print-color-adjust: exact; }}
}}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div class="logo">CATALYX Labs</div>
        <div class="report-meta">
            <strong>Competitor Comparison Report</strong><br>
            {datetime.now().strftime('%d %b %Y')}<br>
            Industry: {industry.title()}
        </div>
    </div>

    <div class="score-grid">
        {score_cards}
    </div>

    <div class="section">
        <h2>📊 Side-by-Side Comparison</h2>
        <table class="comparison-table">
            <thead>
                <tr>
                    <th>Metric</th>
                    <th class="metric-client">Client</th>
                    <th class="metric-comp">Competitor 1</th>
                    <th class="metric-comp">Competitor 2</th>
                    <th class="metric-comp">Competitor 3</th>
                    <th class="metric-gap">vs Avg</th>
                    <th class="metric-gap-best">vs Best</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
        <p style="color: #8b949e; font-size: 0.85em; margin-top: 1em;">
            <strong>Gap Legend:</strong> 
            <span class="gap-positive">Green = You're ahead</span> | 
            <span class="gap-negative">Red = Competitor leads</span> | 
            <span class="gap-neutral">Grey = Parity</span>
            <br>Positive score gap = you lead. Negative defect gap = you have fewer defects (good).
        </p>
    </div>

    <div class="section">
        <h2>🔍 Detailed Defect Breakdown</h2>
        <div class="defect-grid">
            {defect_details}
        </div>
    </div>

    <div class="section">
        <h2>💡 Why This Matters — Impact Analysis</h2>
        <div class="industry-insight">
            <h3>🎯 Industry Context: {industry.title()}</h3>
            <p>{industry_insight}</p>
        </div>
        <div class="why-grid">
            {why_matters}
        </div>
    </div>

    <div class="section">
        <h2>🎯 Recommended Action Priority</h2>
        <ol style="padding-left: 1.5em; color: #c9d1d9;">
            <li><strong>Fix Critical Security Gaps:</strong> SSL expiry, missing HSTS/CSP, broken links — these cause immediate trust loss and browser warnings.</li>
            <li><strong>Close SEO Gap vs Best Competitor:</strong> Add missing H1, meta descriptions, Schema.org, canonical URLs to match or exceed the leader.</li>
            <li><strong>Optimize Conversion Elements:</strong> Contact form, clear CTAs, phone/email visibility, analytics — every missing piece loses leads.</li>
            <li><strong>Improve Content Depth:</strong> Target 800+ words per service page, fix readability, add FAQ schema for rich results.</li>
            <li><strong>Performance & Accessibility:</strong> Compress images, enable caching, fix contrast/alt text — compounds SEO + conversion gains.</li>
        </ol>
    </div>

    <div class="footer">
        <p><strong>CATALYX Labs Ltd</strong> | NZBN 9429053638892<br>
        team@catalyxlabs.shop | catalyxlabs.shop</p>
        <p>Report generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Based on automated audit data — verify manually before action.</p>
    </div>
</div>
</body>
</html>"""
    return html


def run_audit(domain: str) -> dict:
    """Run audit for a domain using the existing auditor."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "website_auditor.py", domain, "--format", "json"],
        capture_output=True, text=True, cwd=ROOT, timeout=120
    )
    if result.returncode == 0:
        return json.loads(result.stdout)
    return None


def main():
    p = argparse.ArgumentParser(description="Competitor Comparison Report Generator")
    p.add_argument("--client", "-c", required=True, help="Client domain (e.g., clyne-bennie.co.nz)")
    p.add_argument("--competitors", "-comp", required=True, help="Comma-separated competitor domains (2-3)")
    p.add_argument("--output", "-o", help="Output HTML file path")
    p.add_argument("--auto", action="store_true", help="Auto-detect from audits/ (first = client, next 2-3 = competitors)")
    p.add_argument("--run-missing", action="store_true", help="Run live audit for missing domains")
    args = p.parse_args()

    if args.auto:
        audit_files = sorted(AUDITS_DIR.glob("*.json"))
        if len(audit_files) < 2:
            print("❌ Need at least 2 audit files in audits/ for auto mode")
            sys.exit(1)
        client_domain = audit_files[0].stem
        competitor_domains = [f.stem for f in audit_files[1:4]]
    else:
        client_domain = args.client.replace("www.", "").strip()
        competitor_domains = [d.strip().replace("www.", "") for d in args.competitors.split(",")][:3]
    
    if len(competitor_domains) < 2:
        print("❌ Need at least 2 competitor domains")
        sys.exit(1)

    print(f"📊 Loading audits...")
    print(f"   Client: {client_domain}")
    print(f"   Competitors: {', '.join(competitor_domains)}")

    # Load client audit
    client_audit = load_audit(client_domain)
    if not client_audit and args.run_missing:
        print(f"   Running live audit for {client_domain}...")
        client_audit = run_audit(client_domain)
    if not client_audit:
        print(f"❌ No audit found for client: {client_domain}")
        sys.exit(1)

    # Load competitor audits
    competitor_audits = []
    for comp in competitor_domains:
        audit = load_audit(comp)
        if not audit and args.run_missing:
            print(f"   Running live audit for {comp}...")
            audit = run_audit(comp)
        if audit:
            competitor_audits.append(audit)
        else:
            print(f"⚠️  No audit found for competitor: {comp} (skipping)")
    
    if len(competitor_audits) < 2:
        print("❌ Need at least 2 competitor audits to compare")
        sys.exit(1)

    # Detect industry from client
    industry = detect_industry(client_audit)
    
    # Calculate gaps
    gap = get_gap_analysis(client_audit, competitor_audits)
    
    # Generate HTML
    html = generate_comparison_html(client_audit, competitor_audits, gap, industry)
    
    # Output
    if args.output:
        output_path = Path(args.output)
    else:
        safe_client = re.sub(r"[^a-zA-Z0-9_-]", "_", client_domain)
        output_path = OUTPUTS_DIR / f"competitor_comparison_{safe_client}.html"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    
    print(f"\n✅ Comparison report saved: {output_path}")
    print(f"\n📈 Summary:")
    print(f"   Client Score: {gap['client_score']}/100 ({gap['client_defects']} defects)")
    print(f"   Avg Competitor: {gap['avg_competitor_score']}/100 ({gap['avg_competitor_defects']} defects)")
    print(f"   Best Competitor: {gap['best_competitor_score']}/100 ({gap['best_competitor_defects']} defects)")
    print(f"   Score Gap vs Avg: {gap['score_gap']:+.1f}")
    print(f"   Score Gap vs Best: {gap['score_gap_best']:+.1f}")
    print(f"   Industry: {industry}")

    return 0


if __name__ == "__main__":
    sys.exit(main())