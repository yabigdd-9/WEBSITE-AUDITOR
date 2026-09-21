#!/usr/bin/env python3
"""Before/After Report Generator — Dramatic comparison reports showing improvement.

Usage:
    python3 before_after_report.py --domain example.com --before 35 --after 85
    python3 before_after_report.py --domain example.com --before 35 --after 85 --fixed 12 --revenue 5000
    python3 before_after_report.py --domain example.com --before 35 --after 85 --pdf
    python3 before_after_report.py --domain example.com --before 35 --after 85 --before-screenshot before.png --after-screenshot after.png --diff-output diff.png
"""
import argparse, json, re, os, subprocess, sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"


def load_audit(domain: str) -> dict:
    """Load audit data for a domain."""
    domain_clean = domain.replace("www.", "")
    for p in [f"audits/{domain_clean}.json", f"audits/www.{domain_clean}.json", f"audits/{domain}.json"]:
        if Path(p).exists():
            return json.loads(Path(p).read_text())
    return {}


def generate_html(domain: str, before_score: int, after_score: int, fixed: int = None, revenue_gain: float = None, monthly_visitors: int = 500) -> str:
    """Generate dramatic before/after comparison HTML."""
    improvement = after_score - before_score
    defect_count = 10  # default estimate
    fix_count = fixed or max(1, int(defect_count * (improvement / 100)))

    # Revenue projection
    if revenue_gain is None:
        monthly_revenue = 1125  # default NZ small business
        annual_gain = monthly_revenue * 12 * (improvement / 100)
        monthly_gain = annual_gain / 12
    else:
        annual_gain = revenue_gain
        monthly_gain = revenue_gain / 12

    # Social proof stats
    visitor_increase = int(monthly_visitors * (improvement / 100))

    # Load audit details for specific defects
    audit = load_audit(domain)
    defects = audit.get("defects", [])
    top_fixed = [d.get("defect", "") for d in defects[:5]]

    fixed_items_html = ""
    for defect in top_fixed:
        fixed_items_html += f"""
        <div class="fixed-item">
            <span class="checkmark">✅</span>
            <span class="defect-name">{defect}</span>
        </div>"""

    # Score color
    def score_color(score):
        if score >= 80: return "#00D4A3"
        elif score >= 60: return "#EFFF00"
        elif score >= 40: return "#FF8A00"
        return "#FF1A1A"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Before/After: {domain}</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; padding: 2em; max-width: 900px; margin: 0 auto; }}
.header {{ text-align: center; margin-bottom: 2em; }}
.header h1 {{ font-size: 2em; margin-bottom: 0.3em; color: #fff; }}
.subtitle {{ color: #8b949e; font-size: 1.1em; }}
.comparison {{ display: grid; grid-template-columns: 1fr auto 1fr; gap: 2em; align-items: center; margin: 2em 0; }}
.score-card {{ padding: 2em; border-radius: 16px; text-align: center; }}
.score-card.before {{ background: linear-gradient(135deg, #FF1A1A, #cc0000); color: #fff; }}
.score-card.after {{ background: linear-gradient(135deg, #00D4A3, #00CFFF); color: #0d1117; }}
.score-big {{ font-size: 4em; font-weight: bold; }}
.score-label {{ font-size: 1.2em; opacity: 0.9; margin-top: 0.5em; }}
.vs {{ font-size: 2em; font-weight: bold; color: #58a6ff; }}
.improvement-badge {{ display: inline-block; background: #003366; color: #fff; padding: 8px 20px; border-radius: 20px; font-size: 1.2em; font-weight: bold; margin: 1em 0; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5em; margin: 2em 0; }}
.stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 1.5em; text-align: center; }}
.stat-val {{ font-size: 2em; font-weight: bold; color: #58a6ff; }}
.stat-label {{ font-size: 0.85em; color: #8b949e; margin-top: 0.3em; }}
.section {{ margin: 2em 0; }}
.section h2 {{ color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: 0.3em; margin-bottom: 1em; }}
.fixed-list {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5em; }}
.fixed-item {{ display: flex; align-items: center; gap: 0.5em; padding: 0.5em 0; border-bottom: 1px solid #21262d; }}
.fixed-item:last-child {{ border-bottom: none; }}
.checkmark {{ font-size: 1.2em; }}
.defect-name {{ font-size: 0.95em; }}
.roi-card {{ background: linear-gradient(135deg, #00D4A3, #00CFFF); color: #fff; padding: 2em; border-radius: 12px; text-align: center; margin: 2em 0; }}
.roi-card h3 {{ color: #fff; border: none; margin-top: 0; }}
.roi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1em; margin-top: 1em; }}
.roi-item {{ text-align: center; }}
.roi-val {{ font-size: 1.8em; font-weight: bold; }}
.roi-label {{ font-size: 0.8em; opacity: 0.9; }}
.footer {{ text-align: center; margin-top: 3em; padding-top: 1em; border-top: 2px solid #30363d; color: #666; font-size: 0.85em; }}
@media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
<div class="header">
    <h1>🏆 Before & After</h1>
    <div class="subtitle">{domain}</div>
    <div class="improvement-badge">+{improvement} points improvement</div>
</div>

<div class="comparison">
    <div class="score-card before">
        <div class="score-label">Before</div>
        <div class="score-big">{before_score}</div>
        <div class="score-label">/100</div>
    </div>
    <div class="vs">→</div>
    <div class="score-card after">
        <div class="score-label">After</div>
        <div class="score-big">{after_score}</div>
        <div class="score-label">/100</div>
    </div>
</div>

<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-val">{fix_count}</div>
        <div class="stat-label">Issues Fixed</div>
    </div>
    <div class="stat-card">
        <div class="stat-val">{improvement}%</div>
        <div class="stat-label">Score Improvement</div>
    </div>
    <div class="stat-card">
        <div class="stat-val">{visitor_increase}</div>
        <div class="stat-label">Additional Monthly Visitors</div>
    </div>
</div>

<div class="section">
    <h2>✅ What We Fixed</h2>
    <div class="fixed-list">
        {fixed_items_html}
    </div>
</div>

<div class="roi-card">
    <h3>💰 Projected 12-Month Impact</h3>
    <div class="roi-grid">
        <div class="roi-item">
            <div class="roi-val">${annual_gain:,.0f}</div>
            <div class="roi-label">Annual Revenue Gain</div>
        </div>
        <div class="roi-item">
            <div class="roi-val">${monthly_gain:,.0f}</div>
            <div class="roi-label">Monthly Revenue Gain</div>
        </div>
        <div class="roi-item">
            <div class="roi-val">{improvement}%</div>
            <div class="roi-label">Improvement</div>
        </div>
    </div>
</div>

<div class="footer">
    <p><strong>CATALYX Labs Ltd</strong> | NZBN 9429053638892<br>
    team@catalyxlabs.shop | catalyxlabs.shop</p>
    <p>Generated: {datetime.now().strftime('%d %b %Y')}</p>
</div>
</body>
</html>"""
    return html


def generate_pdf(html_content: str, output_path: str, gotenberg_url: str = None) -> bool:
    """Generate PDF from HTML using Gotenberg service.

    Args:
        html_content: The HTML string to convert.
        output_path: Path where the PDF should be saved.
        gotenberg_url: Base URL of Gotenberg service (defaults to http://localhost:3000).

    Returns:
        True if successful, False otherwise.
    """
    if requests is None:
        print("⚠️  Requests module not available. Install with: pip install requests")
        return False

    if gotenberg_url is None:
        gotenberg_url = os.environ.get("GOTENBERG_URL", "http://localhost:3000")

    endpoint = f"{gotenberg_url}/forms/html"

    try:
        # Prepare the file for upload
        files = {
            'files': ('document.html', html_content, 'text/html')
        }
        # Optional: set proxy to None to avoid issues in some environments
        response = requests.post(endpoint, files=files, timeout=30)
        response.raise_for_status()

        # Write the PDF content
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"⚠️  Failed to generate PDF via Gotenberg: {e}")
        return False


def run_screenshot_diff(before_path: str, after_path: str, diff_output: str) -> bool:
    """Run screenshot diff using Node.js and pixelmatch.

    This function creates a temporary Node.js script that uses the pixelmatch
    library to compare two images and generate a diff image.

    Args:
        before_path: Path to the before screenshot.
        after_path: Path to the after screenshot.
        diff_output: Path where the diff image should be saved.

    Returns:
        True if successful, False otherwise.
    """
    # Check if Node.js is available
    try:
        subprocess.run(["node", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️  Node.js not found. Please install Node.js to use screenshot diff.")
        return False

    # Create a temporary Node.js script
    node_script = """
const pixelmatch = require('pixelmatch');
const PNG = require('pngjs').PNG;
const fs = require('fs');

const beforePath = process.argv[2];
const afterPath = process.argv[3];
const diffOutput = process.argv[4];

const beforeImg = PNG.sync.read(fs.readFileSync(beforePath));
const afterImg = PNG.sync.read(fs.readFileSync(afterPath));

const {width, height} = beforeImg;
const diffImg = new PNG({width, height});

const mismatchedPixels = pixelmatch(
    beforeImg.data,
    afterImg.data,
    diffImg.data,
    width, height,
    {threshold: 0.1}
);

fs.writeFileSync(diffOutput, PNG.sync.write(diffImg));

console.log(`Mismatched pixels: ${mismatchedPixels}`);
console.log(`Total pixels: ${width * height}`);
console.log(`Match percentage: ${((width * height - mismatchedPixels) / (width * height) * 100).toFixed(2)}%`);
"""
    # Write the script to a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
        f.write(node_script)
        script_path = f.name

    try:
        # Run the Node.js script
        result = subprocess.run(
            ["node", script_path, before_path, after_path, diff_output],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Clean up the temporary script
        os.unlink(script_path)

        if result.returncode != 0:
            print(f"⚠️  Screenshot diff failed: {result.stderr}")
            return False

        # Optionally print the output from the Node.js script
        print(result.stdout.strip())
        return True
    except subprocess.TimeoutExpired:
        os.unlink(script_path)
        print("⚠️  Screenshot diff timed out.")
        return False
    except Exception as e:
        if os.path.exists(script_path):
            os.unlink(script_path)
        print(f"⚠️  Failed to run screenshot diff: {e}")
        return False


def main():
    p = argparse.ArgumentParser(description="Before/After Report Generator")
    p.add_argument("--domain", required=True, help="Domain name")
    p.add_argument("--before", type=int, required=True, help="Before health score")
    p.add_argument("--after", type=int, required=True, help="After health score")
    p.add_argument("--fixed", type=int, help="Number of issues fixed")
    p.add_argument("--revenue", type=float, help="Annual revenue gain")
    p.add_argument("--output", "-o", help="Output file (HTML)")
    p.add_argument("--pdf", action="store_true", help="Also generate PDF via Gotenberg")
    p.add_argument("--gotenberg-url", help="Gotenberg service URL (default: http://localhost:3000)")
    p.add_argument("--before-screenshot", help="Path to before screenshot")
    p.add_argument("--after-screenshot", help="Path to after screenshot")
    p.add_argument("--diff-output", help="Output path for diff image (default: diff.png)")
    args = p.parse_args()

    # Generate HTML report
    html = generate_html(args.domain, args.before, args.after, args.fixed, args.revenue)

    # Determine output paths
    html_output = args.output or f"outputs/before_after_{args.domain}.html"
    Path(html_output).parent.mkdir(parents=True, exist_ok=True)
    Path(html_output).write_text(html)
    print(f"✅ Before/After report saved: {html_output}")

    # Generate PDF if requested
    if args.pdf:
        pdf_output = os.path.splitext(html_output)[0] + ".pdf"
        if generate_pdf(html, pdf_output, args.gotenberg_url):
            print(f"✅ PDF report saved: {pdf_output}")
        else:
            print("⚠️  PDF generation failed.")

    # Run screenshot diff if both screenshots provided
    if args.before_screenshot and args.after_screenshot:
        diff_output = args.diff_output or "diff.png"
        if run_screenshot_diff(args.before_screenshot, args.after_screenshot, diff_output):
            print(f"✅ Screenshot diff saved: {diff_output}")
        else:
            print("⚠️  Screenshot diff failed.")


if __name__ == "__main__":
    main()