#!/usr/bin/env python3
"""Social Media Kit Generator — Shareable graphics as HTML/CSS.

Generates standalone HTML files optimized for screenshotting at social dimensions:
- 1200x630 (Open Graph / Facebook / LinkedIn)
- 1080x1080 (Instagram square)
- 1080x1920 (Instagram Stories / Reels)
- 1500x500 (Twitter header)

Usage:
    python3 social_media_kit.py --domain example.com --score 85
    python3 social_media_kit.py --domain example.com --score 85 --type instagram
    python3 social_media_kit.py --domain example.com --score 85 --all
"""
import argparse, json, re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"

# Social media dimensions
DIMENSIONS = {
    "og": {"width": 1200, "height": 630, "name": "Open Graph / Facebook"},
    "instagram": {"width": 1080, "height": 1080, "name": "Instagram Square"},
    "story": {"width": 1080, "height": 1920, "name": "Instagram Story / Reel"},
    "twitter": {"width": 1500, "height": 500, "name": "Twitter / X Header"},
    "linkedin": {"width": 1200, "height": 627, "name": "LinkedIn Post"},
}


def load_audit(domain: str) -> dict:
    """Load audit data."""
    domain_clean = domain.replace("www.", "")
    for p in [f"audits/{domain_clean}.json", f"audits/www.{domain_clean}.json"]:
        if Path(p).exists():
            return json.loads(Path(p).read_text())
    return {}


def generate_score_badge(domain: str, score: int, width: int = 1200, height: int = 630) -> str:
    """Generate score badge graphic."""
    color = "#00D4A3" if score >= 80 else "#EFFF00" if score >= 60 else "#FF8A00" if score >= 40 else "#FF1A1A"
    tier = "EXCELLENT" if score >= 80 else "GOOD" if score >= 60 else "NEEDS WORK" if score >= 40 else "CRITICAL"
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ 
    width: {width}px; 
    height: {height}px; 
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, sans-serif;
    color: #fff;
    overflow: hidden;
}}
.logo {{ 
    font-size: 2em; 
    font-weight: bold; 
    background: linear-gradient(135deg, #58a6ff, #a371f7);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.5em;
}}
.domain {{ font-size: 1.5em; color: #8b949e; margin-bottom: 1em; }}
.score-circle {{
    width: 200px;
    height: 200px;
    border-radius: 50%;
    background: {color}22;
    border: 8px solid {color};
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 4em;
    font-weight: bold;
    color: {color};
    margin: 0.5em 0;
}}
.tier {{ 
    font-size: 1.5em; 
    font-weight: bold; 
    color: {color};
    padding: 8px 24px;
    border: 2px solid {color};
    border-radius: 30px;
}}
.cta {{ margin-top: 1em; font-size: 1.2em; color: #58a6ff; }}
</style>
</head>
<body>
    <div class="logo">CATALYX Labs</div>
    <div class="domain">{domain}</div>
    <div class="score-circle">{score}</div>
    <div class="tier">{tier}</div>
    <div class="cta">Website Health Score</div>
</body>
</html>"""


def generate_before_after(before_score: int, after_score: int, width: int = 1200, height: int = 630) -> str:
    """Generate before/after comparison graphic."""
    before_color = "#FF1A1A" if before_score < 40 else "#FF8A00"
    after_color = "#00D4A3" if after_score >= 70 else "#EFFF00"
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ 
    width: {width}px; 
    height: {height}px; 
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, sans-serif;
    color: #fff;
    gap: 3em;
}}
.side {{ text-align: center; }}
.label {{ font-size: 1.2em; color: #8b949e; margin-bottom: 0.5em; }}
.score {{ font-size: 5em; font-weight: bold; }}
.before .score {{ color: {before_color}; }}
.after .score {{ color: {after_color}; }}
.sublabel {{ font-size: 0.9em; color: #666; }}
.arrow {{ font-size: 4em; color: #58a6ff; }}
.improvement {{ 
    position: absolute;
    bottom: 2em;
    font-size: 1.5em;
    color: #00D4A3;
    font-weight: bold;
}}
</style>
</head>
<body>
    <div class="side before">
        <div class="label">BEFORE</div>
        <div class="score">{before_score}</div>
        <div class="sublabel">/100</div>
    </div>
    <div class="arrow">→</div>
    <div class="side after">
        <div class="label">AFTER</div>
        <div class="score">{after_score}</div>
        <div class="sublabel">/100</div>
    </div>
    <div class="improvement">+{after_score - before_score} POINTS</div>
</body>
</html>"""


def generate_industry_rank(domain: str, industry: str, rank: int, total: int, width: int = 1080, height: int = 1080) -> str:
    """Generate industry ranking graphic."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ 
    width: {width}px; 
    height: {height}px; 
    background: linear-gradient(135deg, #003366 0%, #0066cc 100%);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, sans-serif;
    color: #fff;
}}
.title {{ font-size: 2em; opacity: 0.9; margin-bottom: 0.5em; }}
.industry {{ 
    font-size: 3em; 
    font-weight: bold; 
    text-transform: uppercase;
    margin-bottom: 1em;
}}
.rank-badge {{
    width: 250px;
    height: 250px;
    border-radius: 50%;
    background: rgba(255,255,255,0.1);
    border: 10px solid #FFD700;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 5em;
    font-weight: bold;
    color: #FFD700;
    margin: 1em 0;
}}
.rank-label {{ font-size: 1.5em; }}
.domain {{ font-size: 1.5em; opacity: 0.8; margin-top: 1em; }}
</style>
</head>
<body>
    <div class="title">Industry Ranking</div>
    <div class="industry">{industry}</div>
    <div class="rank-badge">#{rank}</div>
    <div class="rank-label">out of {total} businesses audited</div>
    <div class="domain">{domain}</div>
</body>
</html>"""


def generate_referral(domain: str, score: int, width: int = 1080, height: int = 1080) -> str:
    """Generate referral incentive graphic."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ 
    width: {width}px; 
    height: {height}px; 
    background: linear-gradient(135deg, #0d1117 0%, #1a1a2e 100%);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, sans-serif;
    color: #fff;
    text-align: center;
    padding: 2em;
}}
.title {{ font-size: 2.5em; margin-bottom: 0.5em; }}
.offer {{ 
    font-size: 3em; 
    font-weight: bold; 
    background: linear-gradient(135deg, #FF8A00, #FFD700);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0.5em 0;
}}
.details {{ font-size: 1.5em; color: #8b949e; margin: 1em 0; max-width: 80%; }}
.cta {{ 
    font-size: 1.8em; 
    color: #58a6ff;
    border: 3px solid #58a6ff;
    padding: 15px 40px;
    border-radius: 50px;
    margin-top: 1em;
}}
.website {{ margin-top: 2em; font-size: 1.2em; color: #666; }}
</style>
</head>
<body>
    <div class="title">🎁 Refer a Friend</div>
    <div class="offer">20% OFF</div>
    <div class="details">
        For every business you refer that signs up,<br>
        you both get 20% off your next project.
    </div>
    <div class="cta">Get Your Referral Code</div>
    <div class="website">catalyxlabs.shop</div>
</body>
</html>"""


def generate_all(domain: str, score: int, before_score: int = None, industry: str = "general"):
    """Generate all social media graphics."""
    output_dir = Path("outputs") / "social"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    files = []
    
    for graphic_type, dims in DIMENSIONS.items():
        w, h = dims["width"], dims["height"]
        
        if graphic_type == "og":
            html = generate_score_badge(domain, score, w, h)
        elif graphic_type == "instagram":
            html = generate_score_badge(domain, score, w, h)
        elif graphic_type == "story":
            html = generate_before_after(before_score or max(20, score - 40), score, w, h)
        elif graphic_type == "twitter":
            html = generate_industry_rank(domain, industry, 3, 50, w, h)
        elif graphic_type == "linkedin":
            html = generate_referral(domain, score, w, h)
        else:
            html = generate_score_badge(domain, score, w, h)
        
        output_path = output_dir / f"{domain}-{graphic_type}.html"
        output_path.write_text(html)
        files.append(str(output_path))
        print(f"  ✅ {dims['name']}: {output_path}")
    
    return files


def main():
    p = argparse.ArgumentParser(description="Social Media Kit Generator")
    p.add_argument("--domain", required=True, help="Domain name")
    p.add_argument("--score", type=int, required=True, help="Health score")
    p.add_argument("--before", type=int, help="Before score (for before/after)")
    p.add_argument("--industry", default="general", help="Industry name")
    p.add_argument("--type", choices=["og", "instagram", "story", "twitter", "linkedin", "all"], default="all")
    p.add_argument("--output", "-o", help="Output directory")
    args = p.parse_args()
    
    print(f"\n📱 Generating social media kit for {args.domain}...")
    
    if args.type == "all":
        files = generate_all(args.domain, args.score, args.before, args.industry)
        print(f"\n✅ Generated {len(files)} graphics in outputs/social/")
    else:
        dims = DIMENSIONS[args.type]
        w, h = dims["width"], dims["height"]
        
        if args.type == "og" or args.type == "instagram":
            html = generate_score_badge(args.domain, args.score, w, h)
        elif args.type == "story":
            html = generate_before_after(args.before or max(20, args.score - 40), args.score, w, h)
        elif args.type == "twitter":
            html = generate_industry_rank(args.domain, args.industry, 3, 50, w, h)
        elif args.type == "linkedin":
            html = generate_referral(args.domain, args.score, w, h)
        else:
            html = generate_score_badge(args.domain, args.score, w, h)
        
        output_dir = Path(args.output) if args.output else Path("outputs") / "social"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{args.domain}-{args.type}.html"
        output_path.write_text(html)
        print(f"✅ Generated: {output_path}")


if __name__ == "__main__":
    main()
