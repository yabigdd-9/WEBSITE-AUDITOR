"""Generate a self-contained demo HTML page with before/after comparison.

Creates an HTML file showing before and after screenshots side-by-side
with fix description and verification summary.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from html import escape

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

    before_state, after_state, proposed_fix, verification = _resolve_demo_states(
        package, before_state, after_state, proposed_fix, verification
    )
    before_img_path, after_img_path, diff_img_path = _demo_image_paths(
        package, before_state, after_state
    )
    values = _demo_values(before_state, proposed_fix, verification)
    url = values["url"]
    fix_type = values["fix_type"]
    fix_description = values["fix_description"]
    fix_original = values["fix_original"]
    fix_proposed = values["fix_proposed"]
    verdict = values["verdict"]
    diff_summary = values["diff_summary"]
    visual_diff_percent = values["visual_diff_percent"]
    axe_before = values["axe_before"]
    axe_after = values["axe_after"]
    console_before = values["console_before"]
    console_after = values["console_after"]

    if not title:
        title = f"Proof Demo — {url}" if url else "Proof Demo"

    # Helper to embed or reference images
    def _img_tag(path: str, label: str) -> str:
        if not path:
            return f"<div class='placeholder'><p>{escape(label)}: no image</p></div>"
        # Use file path as src; the HTML can be opened locally
        safe_label = escape(label)
        safe_path = escape(path, quote=True)
        return f"<div class='panel'><h3>{safe_label}</h3><img src='{safe_path}' alt='{safe_label}' /></div>"

    verdict_class = escape(verdict.lower() if verdict else "unknown", quote=True)
    title = escape(title)
    url = escape(url)
    fix_type = escape(fix_type)
    fix_description = escape(fix_description)
    fix_original = escape(fix_original)
    fix_proposed = escape(fix_proposed)
    verdict = escape(verdict)
    diff_summary = escape(diff_summary)

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


def _resolve_demo_states(package, before_state, after_state, proposed_fix, verification):
    if package:
        return package.before, package.after, package.proposed_fix, package.verification
    return before_state, after_state, proposed_fix, verification


def _demo_image_paths(package, before_state, after_state):
    if package:
        return (
            package.before_screenshot_path,
            package.after_screenshot_path,
            package.diff_path,
        )
    before_path = before_state.screenshot.path if before_state else ""
    after_path = after_state.screenshot.path if after_state else ""
    return before_path, after_path, ""


def _demo_values(before_state, proposed_fix, verification):
    values = {
        "url": before_state.url if before_state else "",
        "fix_type": proposed_fix.fix_type if proposed_fix else "",
        "fix_description": proposed_fix.description if proposed_fix else "",
        "fix_original": proposed_fix.original_value if proposed_fix else "",
        "fix_proposed": proposed_fix.proposed_value if proposed_fix else "",
        "verdict": verification.verdict if verification else "",
        "diff_summary": verification.diff_summary if verification else "",
        "visual_diff_percent": verification.visual_diff_percent if verification else 0.0,
        "axe_before": verification.axe_violations_before if verification else 0,
        "axe_after": verification.axe_violations_after if verification else 0,
        "console_before": verification.console_errors_before if verification else 0,
        "console_after": verification.console_errors_after if verification else 0,
    }
    return values
