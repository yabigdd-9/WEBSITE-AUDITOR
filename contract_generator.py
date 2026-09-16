#!/usr/bin/env python3
"""Contract & Invoice Generator — Turn accepted quotes into legal agreements.

Generates:
- Service Agreement HTML (scope, exclusions, payment terms, timeline, signatures)
- Matching Invoice HTML (due dates, payment instructions, line items)

Usage:
    python3 contract_generator.py <audit.json> --package performance --client "Acme Ltd"
    python3 contract_generator.py --domain example.com --package complete --client "Acme Ltd"
"""

import argparse, json, uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

# ── Service packages (mirror scope_of_work.py) ──────────────────────
PACKAGES = {
    "essential": {
        "name": "Essential Fix",
        "description": "Critical issues only — get the basics right",
        "includes": [
            "SSL certificate fix (if expired/broken)",
            "Contact form installation",
            "Basic SEO meta tags (title, description)",
            "Viewport meta tag for mobile",
            "HSTS and security headers",
            "Favicon installation",
        ],
        "excludes": [
            "Content writing",
            "Design changes",
            "Performance optimization",
            "Schema.org structured data",
            "Ongoing maintenance",
        ],
        "timeline": "48-72 hours",
        "warranty_days": 30,
    },
    "performance": {
        "name": "Performance Package",
        "description": "Everything in Essential + performance & SEO boost",
        "includes": [
            "Everything in Essential Fix",
            "Image optimization and compression",
            "CSS/JS minification",
            "Caching setup",
            "Core Web Vitals improvement",
            "Schema.org structured data",
            "XML sitemap generation",
            "Robots.txt optimization",
        ],
        "excludes": [
            "Content writing",
            "Design changes",
            "Copywriting",
            "Ongoing maintenance",
        ],
        "timeline": "1-2 weeks",
        "warranty_days": 60,
    },
    "complete": {
        "name": "Complete Overhaul",
        "description": "Full website rescue — fix everything and future-proof",
        "includes": [
            "Everything in Performance Package",
            "Broken link repair",
            "Content readability improvements",
            "Privacy policy & Terms of Service pages",
            "Google Analytics 4 setup",
            "Social media meta tags (Open Graph)",
            "Accessibility audit & fixes",
            "30-day post-launch support",
        ],
        "excludes": [
            "New page creation",
            "E-commerce functionality",
        ],
        "timeline": "2-4 weeks",
        "warranty_days": 90,
    },
}

# Base pricing per package (NZD)
BASE_PRICING = {
    "essential": {"base": 450, "per_defect": 60},
    "performance": {"base": 950, "per_defect": 80},
    "complete": {"base": 1800, "per_defect": 100},
}

# ── Company details ────────────────────────────────────────────────
COMPANY = {
    "name": "CATALYX Labs Ltd",
    "nzbn": "9429053638892",
    "email": "team@catalyxlabs.shop",
    "website": "catalyxlabs.shop",
    "address": "Auckland, New Zealand",
    "bank_account": "06-0123-0456789-00",  # example format
    "bank_name": "ANZ Bank New Zealand",
}

GST_RATE = 0.15


def calculate_package_pricing(audit: dict, package_id: str) -> dict:
    """Calculate pricing for a specific package based on audit findings."""
    defect_count = audit.get("defect_count", 0)
    score = audit.get("score", 0)

    if package_id not in PACKAGES:
        raise ValueError(f"Unknown package: {package_id}")

    pkg = PACKAGES[package_id]
    base = BASE_PRICING[package_id]
    variable = defect_count * base["per_defect"]
    subtotal = base["base"] + variable

    # Urgency premium (worse score = more urgent = slight premium)
    if score < 30:
        urgency_premium = 1.15
    elif score < 50:
        urgency_premium = 1.05
    else:
        urgency_premium = 1.0

    total = round(subtotal * urgency_premium)
    gst = round(total * GST_RATE)
    total_inc_gst = total + gst

    return {
        "id": package_id,
        "name": pkg["name"],
        "description": pkg["description"],
        "base_price": base["base"],
        "variable": variable,
        "urgency_multiplier": urgency_premium,
        "subtotal_ex_gst": total,
        "gst": gst,
        "total_inc_gst": total_inc_gst,
        "includes": pkg["includes"],
        "excludes": pkg["excludes"],
        "timeline": pkg["timeline"],
        "warranty_days": pkg["warranty_days"],
    }


def generate_contract_html(
    audit: dict,
    package_id: str,
    client_name: str,
    client_email: str = "",
    contract_id: str = None,
    deposit_pct: int = 50,
) -> str:
    """Generate professional Service Agreement HTML."""
    if contract_id is None:
        contract_id = f"CAT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    domain = audit.get("domain", "unknown")
    score = audit.get("score", 0)
    defects = audit.get("defects", [])
    meta = audit.get("meta", {})

    pricing = calculate_package_pricing(audit, package_id)
    pkg = PACKAGES[package_id]

    generated = datetime.now().strftime("%d %b %Y")
    effective_date = generated
    expiry_date = (datetime.now() + timedelta(days=30)).strftime("%d %b %Y")

    deposit_amount = round(pricing["total_inc_gst"] * deposit_pct / 100)
    balance_amount = pricing["total_inc_gst"] - deposit_amount

    # Build includes/excludes HTML
    includes_html = "\n".join(f"<li>{inc}</li>" for inc in pricing["includes"])
    excludes_html = "\n".join(f"<li>{exc}</li>" for exc in pricing["excludes"])

    # Defect summary for reference
    defect_rows = ""
    for d in defects:
        defect_rows += f"<tr><td>{d.get('defect', '')}</td><td>{d.get('impact', '')}</td></tr>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Service Agreement: {domain} — {pricing['name']}</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 2em; max-width: 900px; margin: 0 auto; line-height: 1.6; }}
.header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #003366; padding-bottom: 1em; margin-bottom: 2em; }}
.logo {{ font-size: 1.4em; font-weight: bold; color: #003366; }}
.contract-meta {{ text-align: right; font-size: 0.85em; color: #8b949e; }}
.contract-meta strong {{ color: #c9d1d9; }}
.score-card {{ background: linear-gradient(135deg, #003366, #0066cc); color: #fff; padding: 1.5em; border-radius: 8px; margin: 1.5em 0; display: flex; justify-content: space-between; align-items: center; }}
.score-big {{ font-size: 2.5em; font-weight: bold; }}
.section {{ margin: 2em 0; }}
h2 {{ color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: 0.3em; margin-bottom: 1em; }}
h3 {{ color: #c9d1d9; margin: 1em 0 0.5em; }}
h4 {{ color: #8b949e; margin: 0.8em 0 0.3em; font-weight: 600; }}
table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #21262d; }}
th {{ background: #161b22; color: #8b949e; font-size: 0.8em; font-weight: 600; }}
tr:hover {{ background: #161b22; }}
.info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1em; margin: 1em 0; }}
.info-box {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1em; }}
.info-label {{ font-size: 0.75em; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }}
.info-value {{ font-size: 1.1em; color: #c9d1d9; font-weight: 500; margin-top: 0.3em; }}
.terms {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5em; margin: 1em 0; }}
.terms ul, .terms ol {{ padding-left: 1.5em; }}
.terms li {{ margin: 0.5em 0; }}
.terms strong {{ color: #58a6ff; }}
.payment-schedule {{ background: linear-gradient(135deg, #003366, #0066cc); color: #fff; padding: 1.5em; border-radius: 8px; margin: 1.5em 0; }}
.payment-row {{ display: flex; justify-content: space-between; align-items: center; padding: 0.8em 0; border-bottom: 1px solid rgba(255,255,255,0.1); }}
.payment-row:last-child {{ border-bottom: none; }}
.payment-label {{ font-weight: 500; }}
.payment-amount {{ font-size: 1.2em; font-weight: bold; }}
.signature-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2em; margin-top: 3em; }}
.signature-box {{ border-top: 2px solid #30363d; padding-top: 1.5em; }}
.signature-line {{ margin: 1em 0; height: 1.5em; border-bottom: 1px solid #30363d; }}
.signature-label {{ font-size: 0.8em; color: #8b949e; margin-top: 0.3em; }}
.initial-boxes {{ display: flex; gap: 1em; margin: 1em 0; flex-wrap: wrap; }}
.initial-box {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 0.8em 1.2em; min-width: 120px; text-align: center; }}
.initial-label {{ font-size: 0.75em; color: #8b949e; }}
.initial-line {{ height: 1.5em; border-bottom: 1px solid #30363d; margin-top: 0.5em; }}
.footer {{ margin-top: 3em; padding-top: 1em; border-top: 2px solid #30363d; text-align: center; color: #666; font-size: 0.8em; }}
.page-break {{ page-break-before: always; }}
@media print {{ body {{ padding: 0; }} .no-print {{ display: none; }} }}
</style>
</head>
<body>
<div class="header">
    <div class="logo">{COMPANY['name']}</div>
    <div class="contract-meta">
        <strong>Service Agreement</strong><br>
        Contract ID: {contract_id}<br>
        Generated: {generated}<br>
        Valid until: {expiry_date}
    </div>
</div>

<div class="score-card">
    <div>
        <div style="opacity:0.8">Service Package</div>
        <div style="font-size:1.5em; font-weight:bold">{pricing['name']}</div>
        <div style="opacity:0.8; margin-top:0.3em">{pricing['description']}</div>
    </div>
    <div style="text-align:right">
        <div style="opacity:0.8">Client</div>
        <div style="font-size:1.2em">{client_name}</div>
        <div style="opacity:0.7; font-size:0.85em">{domain}</div>
    </div>
</div>

<div class="section">
    <h2>1. Parties</h2>
    <div class="info-grid">
        <div class="info-box">
            <div class="info-label">Service Provider</div>
            <div class="info-value">{COMPANY['name']}</div>
            <div style="font-size:0.85em; color:#8b949e; margin-top:0.3em">NZBN: {COMPANY['nzbn']}</div>
            <div style="font-size:0.85em; color:#8b949e">{COMPANY['email']}</div>
        </div>
        <div class="info-box">
            <div class="info-label">Client</div>
            <div class="info-value">{client_name}</div>
            <div style="font-size:0.85em; color:#8b949e; margin-top:0.3em">{client_email or 'Email to be provided'}</div>
            <div style="font-size:0.85em; color:#8b949e">Domain: {domain}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>2. Scope of Work</h2>
    <p>The Provider agrees to perform the following services for the Client's website (<strong>{domain}</strong>):</p>
    <ul style="padding-left: 1.5em; margin: 1em 0;">
        {includes_html}
    </ul>
    <h3>Based on Audit Findings</h3>
    <p>This scope addresses the following issues identified in the website audit (score: {score}/100, {len(defects)} defects):</p>
    <table>
        <thead><tr><th>Defect</th><th>Impact</th></tr></thead>
        <tbody>{defect_rows}</tbody>
    </table>
</div>

<div class="section">
    <h2>3. Exclusions</h2>
    <p>The following are <strong>not included</strong> in this agreement unless separately agreed in writing:</p>
    <ul style="padding-left: 1.5em; margin: 1em 0;">
        {excludes_html}
    </ul>
</div>

<div class="section">
    <h2>4. Timeline & Delivery</h2>
    <div class="info-grid">
        <div class="info-box">
            <div class="info-label">Estimated Timeline</div>
            <div class="info-value">{pricing['timeline']}</div>
        </div>
        <div class="info-box">
            <div class="info-label">Start Date</div>
            <div class="info-value">Upon deposit receipt & access</div>
        </div>
        <div class="info-box">
            <div class="info-label">Warranty Period</div>
            <div class="info-value">{pricing['warranty_days']} days</div>
        </div>
    </div>
    <div class="terms">
        <h4>Timeline Conditions</h4>
        <ul>
            <li>Timeline commences upon receipt of <strong>50% deposit</strong> and provision of all required access credentials (hosting, CMS, DNS, analytics).</li>
            <li>Client delays in providing access, content, or approvals will extend the timeline proportionally.</li>
            <li>Weekends and NZ public holidays are excluded from business-day calculations.</li>
            <li>Emergency/critical fixes (SSL, security) are prioritised and may be completed within 24-48 hours of access.</li>
        </ul>
    </div>
</div>

<div class="section">
    <h2>5. Payment Terms</h2>
    <div class="payment-schedule">
        <h3 style="color:#fff; border:none; margin-top:0">💳 Payment Schedule</h3>
        <div class="payment-row">
            <span class="payment-label">Deposit ({deposit_pct}%) — Due on signing</span>
            <span class="payment-amount">${deposit_amount:,.2f} NZD</span>
        </div>
        <div class="payment-row">
            <span class="payment-label">Balance ({100-deposit_pct}%) — Due on completion</span>
            <span class="payment-amount">${balance_amount:,.2f} NZD</span>
        </div>
        <div class="payment-row" style="border-top: 2px solid rgba(255,255,255,0.3); margin-top: 0.5em; padding-top: 1em;">
            <span class="payment-label">Total (incl. {int(GST_RATE*100)}% GST)</span>
            <span class="payment-amount">${pricing['total_inc_gst']:,.2f} NZD</span>
        </div>
    </div>

    <div class="terms">
        <h4>Payment Conditions</h4>
        <ul>
            <li>All prices in <strong>NZD</strong>. GST ({int(GST_RATE*100)}%) is included in the totals above.</li>
            <li>Deposit is non-refundable once work commences.</li>
            <li>Balance payment due within <strong>7 days</strong> of project completion notification.</li>
            <li>Late payments incur 1.5% monthly interest after 14 days overdue.</li>
            <li>Work may be paused if payments are overdue by more than 14 days.</li>
            <li>Additional work outside scope billed at <strong>$150/hour</strong> (senior rate) with prior written approval.</li>
        </ul>
    </div>

    <h4>Bank Details</h4>
    <div class="info-grid">
        <div class="info-box">
            <div class="info-label">Account Name</div>
            <div class="info-value">{COMPANY['name']}</div>
        </div>
        <div class="info-box">
            <div class="info-label">Bank</div>
            <div class="info-value">{COMPANY['bank_name']}</div>
        </div>
        <div class="info-box">
            <div class="info-label">Account Number</div>
            <div class="info-value">{COMPANY['bank_account']}</div>
        </div>
        <div class="info-box">
            <div class="info-label">Reference</div>
            <div class="info-value">Contract {contract_id}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>6. Warranty & Liability</h2>
    <div class="terms">
        <ul>
            <li><strong>Warranty Period:</strong> {pricing['warranty_days']} days from project completion.</li>
            <li><strong>Covered:</strong> Defects in workmanship related to the agreed scope (e.g., broken fixes, regressions).</li>
            <li><strong>Not Covered:</strong> New feature requests, content changes, third-party updates, hosting/server issues, client-made changes.</li>
            <li><strong>Liability Cap:</strong> Provider's total liability shall not exceed the total fees paid under this agreement.</li>
            <li><strong>No Consequential Damages:</strong> Provider not liable for lost revenue, data, or indirect damages.</li>
        </ul>
    </div>
</div>

<div class="section">
    <h2>7. Client Responsibilities</h2>
    <div class="terms">
        <ul>
            <li>Provide hosting/cPanel/FTP/CMS access within 24 hours of project start.</li>
            <li>Supply all content (text, images, logos, brand assets) in agreed formats.</li>
            <li>Respond to approval requests within 2 business days to avoid timeline delays.</li>
            <li>Maintain backups of existing site; Provider not liable for pre-existing data loss.</li>
            <li>Ensure domain/DNS control is available for necessary changes.</li>
        </ul>
    </div>
</div>

<div class="section">
    <h2>8. Intellectual Property</h2>
    <div class="terms">
        <ul>
            <li>All custom code, configurations, and deliverables created under this agreement transfer to Client upon <strong>full payment</strong>.</li>
            <li>Provider retains rights to reusable components, frameworks, and methodologies.</li>
            <li>Client grants Provider a non-exclusive license to use the project in portfolio/marketing (anonymised if requested).</li>
            <li>Third-party licences (plugins, themes, fonts) remain subject to their own terms.</li>
        </ul>
    </div>
</div>

<div class="section">
    <h2>9. Confidentiality</h2>
    <div class="terms">
        <ul>
            <li>Both parties agree to keep confidential all non-public information exchanged.</li>
            <li>Obligation survives termination for <strong>2 years</strong>.</li>
            <li>Exceptions: information already public, independently developed, or legally required to disclose.</li>
        </ul>
    </div>
</div>

<div class="section">
    <h2>10. Termination</h2>
    <div class="terms">
        <ul>
            <li>Either party may terminate with <strong>7 days written notice</strong>.</li>
            <li>On termination: Client pays for work completed to date + any non-recoverable costs.</li>
            <li>Provider returns all credentials and client materials within 5 business days.</li>
            <li>Deposit is forfeited if Client terminates after work has commenced.</li>
        </ul>
    </div>
</div>

<div class="section">
    <h2>11. Governing Law & Disputes</h2>
    <div class="terms">
        <ul>
            <li>This agreement is governed by the laws of <strong>New Zealand</strong>.</li>
            <li>Disputes to be resolved via good-faith negotiation, then mediation, then NZ courts.</li>
            <li>Jurisdiction: Auckland District Court.</li>
        </ul>
    </div>
</div>

<div class="section">
    <h2>12. Acceptance & Signatures</h2>
    <p>By signing below, both parties acknowledge they have read, understood, and agree to the terms of this Service Agreement.</p>

    <div class="initial-boxes">
        <div class="initial-box">
            <div class="initial-label">Client Initials</div>
            <div class="initial-line"></div>
            <div class="initial-label">Page 1 of 2</div>
        </div>
        <div class="initial-box">
            <div class="initial-label">Provider Initials</div>
            <div class="initial-line"></div>
            <div class="initial-label">Page 1 of 2</div>
        </div>
    </div>

    <div class="signature-grid">
        <div class="signature-box">
            <strong>{COMPANY['name']}</strong><br>
            NZBN: {COMPANY['nzbn']}<br>
            {COMPANY['email']}<br>
            {COMPANY['address']}<br><br>
            <div class="signature-line"></div>
            <div class="signature-label">Authorised Signature</div>
            <div class="signature-line"></div>
            <div class="signature-label">Name / Title</div>
            <div class="signature-line"></div>
            <div class="signature-label">Date</div>
        </div>
        <div class="signature-box">
            <strong>{client_name}</strong><br>
            {client_email or 'Email: ___________________________'}<br><br>
            <div class="signature-line"></div>
            <div class="signature-label">Authorised Signature</div>
            <div class="signature-line"></div>
            <div class="signature-label">Name / Title</div>
            <div class="signature-line"></div>
            <div class="signature-label">Date</div>
        </div>
    </div>
</div>

<div class="footer">
    <p><strong>{COMPANY['name']}</strong> | NZBN {COMPANY['nzbn']}<br>
    {COMPANY['email']} | {COMPANY['website']} | {COMPANY['address']}</p>
    <p>Contract ID: {contract_id} | Generated {generated} | Valid until {expiry_date}</p>
</div>
</body>
</html>"""
    return html


def generate_invoice_html(
    audit: dict,
    package_id: str,
    client_name: str,
    client_email: str = "",
    invoice_id: str = None,
    deposit_pct: int = 50,
    due_days: int = 7,
) -> str:
    """Generate matching Invoice HTML."""
    if invoice_id is None:
        invoice_id = f"INV-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    domain = audit.get("domain", "unknown")
    pricing = calculate_package_pricing(audit, package_id)

    invoice_date = datetime.now().strftime("%d %b %Y")
    due_date = (datetime.now() + timedelta(days=due_days)).strftime("%d %b %Y")

    deposit_amount = round(pricing["total_inc_gst"] * deposit_pct / 100)
    balance_amount = pricing["total_inc_gst"] - deposit_amount

    # Determine if this is a deposit invoice or final invoice
    # For this implementation, we'll show both line items
    line_items_html = f"""
        <tr>
            <td>1</td>
            <td>{pricing['name']} — {pricing['description']}</td>
            <td>1</td>
            <td>${pricing['subtotal_ex_gst']:,.2f}</td>
            <td>${pricing['subtotal_ex_gst']:,.2f}</td>
        </tr>
        <tr>
            <td colspan="4" style="text-align:right"><strong>Subtotal (excl. GST)</strong></td>
            <td><strong>${pricing['subtotal_ex_gst']:,.2f}</strong></td>
        </tr>
        <tr>
            <td colspan="4" style="text-align:right">GST ({int(GST_RATE*100)}%)</td>
            <td>${pricing['gst']:,.2f}</td>
        </tr>
        <tr style="background:#161b22; font-weight:bold;">
            <td colspan="4" style="text-align:right">Total (incl. GST)</td>
            <td>${pricing['total_inc_gst']:,.2f}</td>
        </tr>
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Invoice {invoice_id} — {client_name}</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 2em; max-width: 800px; margin: 0 auto; line-height: 1.6; }}
.header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #003366; padding-bottom: 1em; margin-bottom: 2em; }}
.logo {{ font-size: 1.5em; font-weight: bold; color: #003366; }}
.invoice-meta {{ text-align: right; }}
.invoice-title {{ font-size: 1.8em; font-weight: bold; color: #58a6ff; margin-bottom: 0.5em; }}
.invoice-details {{ font-size: 0.9em; color: #8b949e; }}
.invoice-details strong {{ color: #c9d1d9; }}
.billing-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2em; margin: 2em 0; }}
.billing-box {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5em; }}
.billing-box h3 {{ color: #58a6ff; margin-bottom: 1em; font-size: 1em; border-bottom: 1px solid #30363d; padding-bottom: 0.5em; }}
.billing-row {{ display: flex; justify-content: space-between; margin: 0.5em 0; }}
.billing-label {{ color: #8b949e; font-size: 0.85em; }}
.billing-value {{ color: #c9d1d9; font-weight: 500; text-align: right; }}
table {{ width: 100%; border-collapse: collapse; margin: 1.5em 0; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #21262d; }}
th {{ background: #161b22; color: #8b949e; font-size: 0.8em; font-weight: 600; text-transform: uppercase; }}
td {{ color: #c9d1d9; }}
tr:hover {{ background: #161b22; }}
.total-section {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5em; margin: 2em 0; }}
.total-row {{ display: flex; justify-content: space-between; margin: 0.5em 0; }}
.total-row.final {{ border-top: 2px solid #30363d; padding-top: 1em; margin-top: 1em; font-size: 1.2em; font-weight: bold; color: #58a6ff; }}
.payment-instructions {{ background: linear-gradient(135deg, #003366, #0066cc); color: #fff; padding: 1.5em; border-radius: 8px; margin: 2em 0; }}
.payment-instructions h3 {{ color: #fff; border: none; margin-top: 0; }}
.payment-instructions .detail {{ margin: 0.5em 0; }}
.payment-instructions .label {{ color: rgba(255,255,255,0.7); font-size: 0.85em; }}
.payment-instructions .value {{ font-weight: 500; }}
.terms {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5em; margin: 2em 0; font-size: 0.9em; }}
.terms h3 {{ color: #58a6ff; margin-bottom: 0.5em; }}
.terms ul {{ padding-left: 1.5em; }}
.terms li {{ margin: 0.4em 0; }}
.footer {{ margin-top: 3em; padding-top: 1em; border-top: 2px solid #30363d; text-align: center; color: #666; font-size: 0.8em; }}
@media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
<div class="header">
    <div class="logo">{COMPANY['name']}</div>
    <div class="invoice-meta">
        <div class="invoice-title">TAX INVOICE</div>
        <div class="invoice-details">
            <strong>Invoice #{invoice_id}</strong><br>
            Date: {invoice_date}<br>
            Due Date: {due_date}<br>
            Contract: {contract_id.replace('CAT-', 'CAT-') if 'contract_id' in locals() else 'N/A'}
        </div>
    </div>
</div>

<div class="billing-grid">
    <div class="billing-box">
        <h3>From</h3>
        <div class="billing-row"><span class="billing-label">{COMPANY['name']}</span></div>
        <div class="billing-row"><span class="billing-label">NZBN:</span> <span class="billing-value">{COMPANY['nzbn']}</span></div>
        <div class="billing-row"><span class="billing-label">Email:</span> <span class="billing-value">{COMPANY['email']}</span></div>
        <div class="billing-row"><span class="billing-label">Address:</span> <span class="billing-value">{COMPANY['address']}</span></div>
    </div>
    <div class="billing-box">
        <h3>Bill To</h3>
        <div class="billing-row"><span class="billing-label">{client_name}</span></div>
        {f'<div class="billing-row"><span class="billing-label">Email:</span> <span class="billing-value">{client_email}</span></div>' if client_email else ''}
        <div class="billing-row"><span class="billing-label">Project:</span> <span class="billing-value">{domain} — {pricing['name']}</span></div>
    </div>
</div>

<table>
    <thead>
        <tr><th>#</th><th>Description</th><th>Qty</th><th>Unit Price (excl. GST)</th><th>Total (excl. GST)</th></tr>
    </thead>
    <tbody>
        {line_items_html}
    </tbody>
</table>

<div class="total-section">
    <div class="total-row"><span>Subtotal (excl. GST)</span><span>${pricing['subtotal_ex_gst']:,.2f}</span></div>
    <div class="total-row"><span>GST ({int(GST_RATE*100)}%)</span><span>${pricing['gst']:,.2f}</span></div>
    <div class="total-row final"><span>Total Due (incl. GST)</span><span>${pricing['total_inc_gst']:,.2f} NZD</span></div>
</div>

<div class="payment-instructions">
    <h3>💳 Payment Instructions</h3>
    <div class="detail"><span class="label">Pay To:</span> <span class="value">{COMPANY['name']}</span></div>
    <div class="detail"><span class="label">Bank:</span> <span class="value">{COMPANY['bank_name']}</span></div>
    <div class="detail"><span class="label">Account:</span> <span class="value">{COMPANY['bank_account']}</span></div>
    <div class="detail"><span class="label">Reference:</span> <span class="value">Invoice {invoice_id}</span></div>
    <div class="detail" style="margin-top:1em; padding-top:1em; border-top:1px solid rgba(255,255,255,0.2);">
        <span class="label">Amount Due:</span> <span class="value" style="font-size:1.2em">${pricing['total_inc_gst']:,.2f} NZD</span>
    </div>
    <div class="detail"><span class="label">Due By:</span> <span class="value">{due_date}</span></div>
</div>

<div class="terms">
    <h3>Payment Terms</h3>
    <ul>
        <li>Payment due within <strong>{due_days} days</strong> of invoice date ({due_date}).</li>
        <li>All amounts in <strong>NZD</strong>. GST ({int(GST_RATE*100)}%) included.</li>
        <li>Late payments incur 1.5% monthly interest after 14 days overdue.</li>
        <li>Please use the invoice number as payment reference.</li>
        <li>Remittance advice appreciated: {COMPANY['email']}</li>
    </ul>
</div>

<div class="footer">
    <p><strong>{COMPANY['name']}</strong> | NZBN {COMPANY['nzbn']}<br>
    {COMPANY['email']} | {COMPANY['website']} | {COMPANY['address']}</p>
    <p>Invoice {invoice_id} | Issued {invoice_date} | Due {due_date}</p>
</div>
</body>
</html>"""
    return html


def save_output(html: str, output_path: str) -> str:
    """Save HTML to file, creating directories as needed."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html)
    return output_path


def main():
    p = argparse.ArgumentParser(description="Contract & Invoice Generator")
    p.add_argument("audit_file", nargs="?", help="Path to audit JSON file")
    p.add_argument("--batch", metavar="DIR", help="Generate for all audits in directory")
    p.add_argument("--domain", help="Domain name (for manual entry)")
    p.add_argument("--score", type=int, help="Health score (for manual entry)")
    p.add_argument("--defects", type=int, help="Number of defects (for manual entry)")
    p.add_argument("--package", choices=list(PACKAGES.keys()), default="performance",
                   help="Service package: essential, performance, complete")
    p.add_argument("--client", required=False, help="Client name (required)")
    p.add_argument("--client-email", help="Client email")
    p.add_argument("--contract-id", help="Custom contract ID")
    p.add_argument("--invoice-id", help="Custom invoice ID")
    p.add_argument("--deposit", type=int, default=50, help="Deposit percentage (default: 50)")
    p.add_argument("--due-days", type=int, default=7, help="Invoice due days (default: 7)")
    p.add_argument("--output-dir", default="outputs", help="Output directory (default: outputs)")
    p.add_argument("--contract-only", action="store_true", help="Generate only contract")
    p.add_argument("--invoice-only", action="store_true", help="Generate only invoice")
    args = p.parse_args()

    if not args.client and not args.audit_file and not args.batch and not (args.domain and args.score is not None):
        p.error("--client is required unless using --batch with audit files containing client info")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def process_audit(data: dict, domain_override: str = None):
        domain = domain_override or data.get("domain", "unknown")
        client = args.client or data.get("client_name", "Client Name")
        client_email = args.client_email or data.get("client_email", "")

        # Generate contract
        if not args.invoice_only:
            contract_id = args.contract_id or f"CAT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
            contract_html = generate_contract_html(
                data, args.package, client, client_email, contract_id, args.deposit
            )
            contract_path = save_output(contract_html, output_dir / f"contract_{domain}.html")
            print(f"✅ Contract saved: {contract_path}")

        # Generate invoice
        if not args.contract_only:
            invoice_id = args.invoice_id or f"INV-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
            invoice_html = generate_invoice_html(
                data, args.package, client, client_email, invoice_id, args.deposit, args.due_days
            )
            invoice_path = save_output(invoice_html, output_dir / f"invoice_{domain}.html")
            print(f"✅ Invoice saved: {invoice_path}")

    if args.audit_file:
        data = json.loads(Path(args.audit_file).read_text())
        process_audit(data)

    elif args.batch:
        audits_dir = Path(args.batch)
        for aj in sorted(audits_dir.glob("*.json")):
            data = json.loads(aj.read_text())
            domain = data.get("domain", aj.stem)
            print(f"Processing {domain}...")
            process_audit(data, domain)

    elif args.domain and args.score is not None:
        data = {
            "domain": args.domain,
            "score": args.score,
            "defect_count": args.defects or 0,
            "defects": [],
            "evidence": {},
            "meta": {},
        }
        process_audit(data)

    else:
        p.print_help()


if __name__ == "__main__":
    main()