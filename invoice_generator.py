#!/usr/bin/env python3
"""Invoice Generator — Generates professional print-ready HTML invoices from quote data.

Includes:
- Invoice number, date, due date
- Line items from quote
- Payment instructions (NZ bank deposit)
- GST breakdown (15% NZ)
- Payment terms

Usage:
    python3 invoice_generator.py <quote.json>
    python3 invoice_generator.py --quote-id INV-20260916-0001 --due-days 14
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# ── NZ GST rate ──────────────────────────────────────────────────────
GST_RATE = 0.15

# ── CATALYX Labs bank details (placeholder - update with real details) ────
BANK_DETAILS = {
    "account_name": "CATALYX Labs Ltd",
    "bank": "ASB Bank",
    "account_number": "12-3456-7890123-00",
    "reference_format": "INV-{invoice_id}",
}


def parse_quote_data(quote_json: dict) -> dict:
    """Extract and normalize data from quote JSON."""
    domain = quote_json.get("domain", "unknown")
    score = quote_json.get("score", 0)
    defects = quote_json.get("defects", [])
    meta = quote_json.get("meta", {})
    evidence = quote_json.get("evidence", {})

    # Build line items from defects
    line_items = []
    for i, d in enumerate(defects, 1):
        defect_text = d.get("defect", "")
        remediation = d.get("remediation", "")
        hours = d.get("hours", 1.0)
        rate = d.get("rate", 120)
        estimate = d.get("estimate", hours * rate)

        line_items.append({
            "number": i,
            "description": defect_text,
            "details": remediation,
            "hours": hours,
            "rate": rate,
            "amount": round(estimate, 2),
        })

    # Calculate totals
    subtotal = sum(item["amount"] for item in line_items)
    gst = round(subtotal * GST_RATE, 2)
    total = round(subtotal + gst, 2)

    return {
        "domain": domain,
        "score": score,
        "defect_count": len(defects),
        "line_items": line_items,
        "subtotal": subtotal,
        "gst": gst,
        "total": total,
        "meta": meta,
        "evidence": evidence,
    }


def generate_invoice_id(quote_id: str = None) -> str:
    """Generate invoice ID from quote ID or create new."""
    if quote_id and quote_id.startswith("CAT-"):
        # Convert CAT-YYYYMMDD-XXXX to INV-YYYYMMDD-XXXX
        return quote_id.replace("CAT-", "INV-")
    if quote_id and quote_id.startswith("INV-"):
        return quote_id
    # Generate new
    return f"INV-{datetime.now().strftime('%Y%m%d')}-{hash(str(datetime.now())) % 10000:04d}"


def generate_invoice_html(
    quote_data: dict,
    invoice_id: str = None,
    issue_date: str = None,
    due_days: int = 14,
    client_name: str = None,
    client_email: str = None,
    payment_terms: str = None,
) -> str:
    """Generate professional invoice HTML."""

    # Parse quote data
    data = parse_quote_data(quote_data)

    # Generate invoice metadata
    if invoice_id is None:
        invoice_id = generate_invoice_id(quote_data.get("quote_id"))

    if issue_date is None:
        issue_date = datetime.now().strftime("%d %b %Y")
    else:
        # Validate and format
        try:
            dt = datetime.strptime(issue_date, "%Y-%m-%d")
            issue_date = dt.strftime("%d %b %Y")
        except ValueError:
            issue_date = datetime.now().strftime("%d %b %Y")

    issue_dt = datetime.strptime(issue_date, "%d %b %Y")
    due_dt = issue_dt + timedelta(days=due_days)
    due_date = due_dt.strftime("%d %b %Y")

    # Default client info from domain if not provided
    if client_name is None:
        client_name = data["domain"]
    if client_email is None:
        client_email = f"contact@{data['domain']}"

    # Default payment terms
    if payment_terms is None:
        payment_terms = (
            f"Payment due within {due_days} days of invoice date. "
            f"Please reference invoice number {invoice_id} with your payment. "
            f"Overdue accounts may incur late fees per CATALYX Labs terms of service."
        )

    # Bank reference
    bank_ref = BANK_DETAILS["reference_format"].format(invoice_id=invoice_id)

    # Build line items HTML
    line_items_html = ""
    for item in data["line_items"]:
        line_items_html += f"""
        <tr>
            <td>{item['number']}</td>
            <td>
                <strong>{item['description']}</strong>
                <br><small style="color:#666">{item['details']}</small>
            </td>
            <td>{item['hours']}h</td>
            <td>${item['rate']:,.0f}/hr</td>
            <td>${item['amount']:,.2f}</td>
        </tr>"""

    # GST breakdown
    gst_html = f"""
        <tr>
            <td colspan="4" style="text-align:right"><strong>Subtotal</strong></td>
            <td><strong>${data['subtotal']:,.2f}</strong></td>
        </tr>
        <tr>
            <td colspan="4" style="text-align:right">GST (15%)</td>
            <td>${data['gst']:,.2f}</td>
        </tr>
        <tr class="total-row">
            <td colspan="4" style="text-align:right"><strong>Total (NZD)</strong></td>
            <td><strong>${data['total']:,.2f}</strong></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Invoice: {invoice_id}</title>
<style>
@page {{ size: A4; margin: 2cm; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1a1a2e; margin: 0; padding: 2em; max-width: 800px; margin: 0 auto; }}
.header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #003366; padding-bottom: 1em; margin-bottom: 2em; }}
.logo {{ font-size: 1.5em; font-weight: bold; color: #003366; }}
.invoice-meta {{ text-align: right; }}
.invoice-title {{ font-size: 1.5em; font-weight: bold; color: #003366; margin-bottom: 0.5em; }}
.score-card {{ background: linear-gradient(135deg, #003366 0%, #0066cc 100%); color: #fff; padding: 1.5em; border-radius: 8px; margin: 1.5em 0; display: flex; justify-content: space-between; align-items: center; }}
.score-big {{ font-size: 3em; font-weight: bold; }}
.score-details {{ text-align: right; }}
.section {{ margin: 2em 0; }}
h2 {{ color: #003366; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.3em; }}
table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
th {{ background: #f5f5f5; font-weight: 600; }}
tr:hover {{ background: #f9f9f9; }}
.total-row {{ font-size: 1.1em; font-weight: bold; background: #f0f0f0 !important; }}
.bank-card {{ background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; }}
.bank-row {{ display: flex; justify-content: space-between; margin: 0.5em 0; }}
.bank-label {{ font-weight: 600; color: #003366; }}
.bank-value {{ font-family: monospace; }}
.terms {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 1em; margin: 1.5em 0; }}
.terms h3 {{ margin-top: 0; color: #856404; }}
.footer {{ margin-top: 3em; padding-top: 1em; border-top: 2px solid #e0e0e0; text-align: center; color: #666; font-size: 0.85em; }}
.gst-badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; background: #00D4A3; color: #1a1a2e; font-weight: bold; font-size: 0.85em; }}
.status {{ display: inline-block; padding: 6px 16px; border-radius: 20px; background: #003366; color: #fff; font-size: 0.9em; }}
@media print {{ body {{ padding: 0; }} .no-print {{ display: none; }} }}
</style>
</head>
<body>
<div class="header">
    <div class="logo">CATALYX Labs</div>
    <div class="invoice-meta">
        <div class="invoice-title">TAX INVOICE</div>
        <strong>#{invoice_id}</strong><br>
        <span class="gst-badge">GST Registered</span><br>
        Issued: {issue_date}<br>
        Due: {due_date}
    </div>
</div>

<div class="section">
    <h2>Bill To</h2>
    <table>
        <tr><td><strong>Client</strong></td><td>{client_name}</td></tr>
        <tr><td><strong>Email</strong></td><td>{client_email}</td></tr>
        <tr><td><strong>Website</strong></td><td>{data['domain']}</td></tr>
        <tr><td><strong>Health Score</strong></td><td>{data['score']}/100 ({data['defect_count']} defects)</td></tr>
    </table>
</div>

<div class="section">
    <h2>Invoice Details</h2>
    <table>
        <thead>
            <tr><th>#</th><th>Description</th><th>Hours</th><th>Rate</th><th>Amount (NZD)</th>
        </thead>
        <tbody>
            {line_items_html}
            {gst_html}
        </tbody>
    </table>
</div>

<div class="bank-card">
    <h3 style="margin-top:0; color:#003366">🏦 Payment Instructions (NZ Bank Deposit)</h3>
    <div class="bank-row"><span class="bank-label">Account Name:</span><span class="bank-value">{BANK_DETAILS['account_name']}</span></div>
    <div class="bank-row"><span class="bank-label">Bank:</span><span class="bank-value">{BANK_DETAILS['bank']}</span></div>
    <div class="bank-row"><span class="bank-label">Account Number:</span><span class="bank-value">{BANK_DETAILS['account_number']}</span></div>
    <div class="bank-row"><span class="bank-label">Reference:</span><span class="bank-value">{bank_ref}</span></div>
    <p style="margin-top:1em; font-size:0.85em; color:#666">
        <strong>Important:</strong> Please use the reference above so we can match your payment immediately.
        Payment via credit card or PayPal available on request (surcharge may apply).
    </p>
</div>

<div class="terms">
    <h3>📋 Payment Terms</h3>
    <p>{payment_terms}</p>
    <ul style="margin: 0.5em 0 0 1.5em; padding: 0;">
        <li>All prices in NZD. GST included where shown.</li>
        <li>Work commences upon receipt of payment or signed purchase order.</li>
        <li>30-day warranty on all remediation work performed.</li>
        <li>Post-fix validation and performance re-scan included.</li>
    </ul>
</div>

<div class="section">
    <h2>What's Included</h2>
    <ul>
        <li>Complete defect remediation as listed above</li>
        <li>Post-fix testing and validation</li>
        <li>30-day warranty on all fixes</li>
        <li>Performance re-scan to confirm improvements</li>
    </ul>
</div>

<div class="footer">
    <p><strong>CATALYX Labs Ltd</strong> | NZBN 9429053638892 | GST Registered<br>
    team@catalyxlabs.shop | catalyxlabs.shop</p>
    <p style="font-size:0.75em">Invoice generated {datetime.now().strftime('%d %b %Y %H:%M')}. This is a computer-generated invoice; no signature required.</p>
</div>
</body>
</html>"""
    return html


def generate_invoice_json(
    quote_data: dict,
    invoice_id: str = None,
    issue_date: str = None,
    due_days: int = 14,
    client_name: str = None,
    client_email: str = None,
) -> dict:
    """Generate structured invoice JSON."""
    data = parse_quote_data(quote_data)

    if invoice_id is None:
        invoice_id = generate_invoice_id(quote_data.get("quote_id"))

    if issue_date is None:
        issue_date = datetime.now().strftime("%Y-%m-%d")
    issue_dt = datetime.strptime(issue_date, "%Y-%m-%d")
    due_date = (issue_dt + timedelta(days=due_days)).strftime("%Y-%m-%d")

    return {
        "invoice_id": invoice_id,
        "quote_id": quote_data.get("quote_id"),
        "issue_date": issue_date,
        "due_date": due_date,
        "client": {
            "name": client_name or data["domain"],
            "email": client_email or f"contact@{data['domain']}",
            "website": data["domain"],
        },
        "line_items": data["line_items"],
        "subtotal_nzd": data["subtotal"],
        "gst_nzd": data["gst"],
        "total_nzd": data["total"],
        "gst_rate": GST_RATE,
        "payment": {
            "method": "bank_deposit",
            "bank_details": BANK_DETAILS,
            "reference": BANK_DETAILS["reference_format"].format(invoice_id=invoice_id),
        },
        "terms": f"Payment due within {due_days} days. Reference: {invoice_id}",
        "status": "issued",
    }


def main():
    p = argparse.ArgumentParser(description="Invoice Generator — Professional NZ GST invoices from quotes")
    p.add_argument("quote_file", nargs="?", help="Path to quote JSON file")
    p.add_argument("--invoice-id", help="Invoice ID (default: auto-generated from quote)")
    p.add_argument("--issue-date", help="Issue date YYYY-MM-DD (default: today)")
    p.add_argument("--due-days", type=int, default=14, help="Payment terms in days (default: 14)")
    p.add_argument("--client-name", help="Client name (default: domain)")
    p.add_argument("--client-email", help="Client email (default: contact@domain)")
    p.add_argument("--output", "-o", help="Output file (default: invoice_<id>.html)")
    p.add_argument("--format", choices=["html", "json"], default="html", help="Output format")
    args = p.parse_args()

    if not args.quote_file:
        p.print_help()
        return 1

    quote_path = Path(args.quote_file)
    if not quote_path.exists():
        print(f"❌ Quote file not found: {quote_path}")
        return 1

    quote_data = json.loads(quote_path.read_text())

    if args.format == "html":
        output = generate_invoice_html(
            quote_data,
            invoice_id=args.invoice_id,
            issue_date=args.issue_date,
            due_days=args.due_days,
            client_name=args.client_name,
            client_email=args.client_email,
        )
    else:
        output = json.dumps(
            generate_invoice_json(
                quote_data,
                invoice_id=args.invoice_id,
                issue_date=args.issue_date,
                due_days=args.due_days,
                client_name=args.client_name,
                client_email=args.client_email,
            ),
            indent=2,
        )

    output_path = args.output or f"outputs/invoice_{args.invoice_id or 'auto'}.html"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(output)
    print(f"✅ Invoice saved: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())