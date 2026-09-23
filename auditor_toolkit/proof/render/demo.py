"""Generate a self-contained demo HTML page with before/after comparison.

Creates an HTML file showing before and after screenshots side-by-side
with fix description and verification summary.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

from auditor_toolkit.proof.schema import (
    AfterState,
    BeforeState,
    ProofPackage,
    ProposedFix,
    VerificationResult,
)

_default_output_dir = tempfile.mkdtemp(prefix="website-auditor-proof-")


def generate_demo_html(
    output_dir: str = _default_output_dir,
    before_state: BeforeState | None = None,
    after_state: AfterState | None = None,
    proposed_fix: ProposedFix | None = None,
    verification: VerificationResult | None = None,
    package: ProofPackage | None = None,
    title: str = "",
) -> str:
    """Generate a self-contained HTML demo page.

    Accepts either individual components or a complete ProofPackage.
    Returns the path to the generated HTML file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Unpack from package if provided
    if package:
        before_state = package.before
        after_state = package.after
        proposed_fix = package.proposed_fix
        verification = package.verification

    before_img_path = ""
    after_img_path = ""
    diff_img_path = ""
    if package:
        before_img_path = package.before_screenshot_path
        after_img_path = package.after_screenshot_path
        diff_img_path = package.diff_path
    else:
        before_img_path = before_state.screenshot.path if before_state else ""
        after_img_path = after_state.screenshot.path if after_state else ""

    url = ""
    fix_type = ""
    fix_description = ""
    fix_original = ""
    fix_proposed = ""
    verdict = ""
    diff_summary = ""
    visual_diff_percent = 0.0
    axe_before = 0
    axe_after = 0
    console_before = 0
    console_after = 0

    if before_state:
        url = before_state.url
    if proposed_fix:
        fix_type = proposed_fix.fix_type
        fix_description = proposed_fix.description
        fix_original = proposed_fix.original_value
        fix_proposed = proposed_fix.proposed_value
    if verification:
        verdict = verification.verdict
        diff_summary = verification.diff_summary
        visual_diff_percent = verification.visual_diff_percent
        axe_before = verification.axe_violations_before
        axe_after = verification.axe_violations_after
        console_before = verification.console_errors_before
        console_after = verification.console_errors_after

    if not title:
        title = f"Proof Demo — {url}" if url else "Proof Demo"

    # Helper to embed or reference images
    def _img_tag(path: str, label: str) -> str:
        if not path:
            return f"<div class='placeholder'><p>{label}: no image</p></div>"
        # Use file path as src; the HTML can be opened locally
        return f"<div class='panel'><h3>{label}</h3><img src='{path}' alt='{label}' /></div>"

    verdict_class = verdict.lower() if verdict else "unknown"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg: #f8f9fa;
    --card: #fff;
    --border: #e0e0e0;
    --text: #1a1a2e;
    --muted: #6c757d;
    --green: #28a745;
    --red: #dc3545;
    --yellow: #ffc107;
    --blue: #007bff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
  }}
  header {{
    max-width: 1400px;
    margin: 0 auto 2rem;
  }}
  header h1 {{ font-size: 1.75rem; margin-bottom: 0.5rem; }}
  header .meta {{ color: var(--muted); font-size: 0.9rem; }}
  .comparison {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
    max-width: 1400px;
    margin: 0 auto 2rem;
  }}
  .panel {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }}
  .panel h3 {{
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border);
    font-size: 1rem;
    background: #f1f3f5;
  }}
  .panel img {{
    width: 100%;
    display: block;
  }}
  .panel .placeholder {{
    padding: 3rem;
    text-align: center;
    color: var(--muted);
  }}
  .summary {{
    max-width: 1400px;
    margin: 0 auto 2rem;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
  }}
  .summary h2 {{ font-size: 1.25rem; margin-bottom: 1rem; }}
  .summary table {{
    width: 100%;
    border-collapse: collapse;
  }}
  .summary td, .summary th {{
    padding: 0.5rem 1rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }}
  .summary th {{ width: 220px; color: var(--muted); }}
  .verdict {{
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.85rem;
    text-transform: uppercase;
  }}
  .verdict.fixed {{ background: #d4edda; color: #155724; }}
  .verdict.not_fixed {{ background: #f8d7da; color: #721c24; }}
  .verdict.regression {{ background: #fff3cd; color: #856404; }}
  .verdict.inconclusive {{ background: #e2e3e5; color: #383d41; }}
  .verdict.unknown {{ background: #e2e3e5; color: #383d41; }}
  .code {{
    background: #f1f3f5;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-family: 'SF Mono', Monaco, Consolas, monospace;
    font-size: 0.85rem;
    overflow-x: auto;
    margin: 0.5rem 0;
  }}
  .diff-section {{
    max-width: 1400px;
    margin: 0 auto 2rem;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
  }}
  footer {{
    max-width: 1400px;
    margin: 2rem auto 0;
    text-align: center;
    color: var(--muted);
    font-size: 0.8rem;
  }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">
    <span>URL: {url}</span> &middot;
    <span>Fix type: {fix_type}</span> &middot;
    <span>Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</span>
  </div>
</header>

<div class="comparison">
  {_img_tag(before_img_path, "Before")}
  {_img_tag(after_img_path, "After")}
</div>

{_img_tag(diff_img_path, "Visual Diff") if diff_img_path else ""}

<div class="summary">
  <h2>Fix Summary</h2>
  <table>
    <tr><th>Verdict</th><td><span class="verdict {verdict_class}">{verdict or "N/A"}</span></td></tr>
    <tr><th>Description</th><td>{fix_description or "N/A"}</td></tr>
    <tr><th>Original value</th><td><div class="code">{fix_original or "N/A"}</div></td></tr>
    <tr><th>Proposed value</th><td><div class="code">{fix_proposed or "N/A"}</div></td></tr>
    <tr><th>Axe violations</th><td>{axe_before} &rarr; {axe_after}</td></tr>
    <tr><th>Console errors</th><td>{console_before} &rarr; {console_after}</td></tr>
    <tr><th>Visual diff</th><td>{visual_diff_percent}%</td></tr>
    <tr><th>Diff summary</th><td>{diff_summary or "N/A"}</td></tr>
  </table>
</div>

<footer>
  Generated by WEBSITE-AUDITOR Proof Package Generator &middot;
  P2-003 / v39
</footer>
</body>
</html>"""

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    html_path = os.path.join(output_dir, f"demo_{ts}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path
