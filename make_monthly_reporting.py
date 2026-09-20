import pathlib

pathlib.Path("website_auditor/reporting").mkdir(parents=True, exist_ok=True)
pathlib.Path("website_auditor/reporting/__init__.py").touch()

# ============================================
# FILE 1: HTML Report Generator
# ============================================
generator = """
\"\"\"
Monthly Report Generator: Creates branded HTML reports ready for PDF export.
\"\"\"
import json
from pathlib import Path
from datetime import datetime, timezone


class MonthlyReportGenerator:
    def __init__(self, branding_config):
        self.agency = branding_config.get("agency", {})
        self.contact = branding_config.get("contact", {})

    def load_client_data(self, domain):
        \"\"\"Load all data sources for a client.\"\"\"
        data = {
            "domain": domain,
            "remediation": None,
            "revenue": None,
            "summary": None,
            "snapshots": [],
        }

        # Remediation data
        rem_file = Path(f"outputs/remediations/{domain}-remediation.json")
        if rem_file.exists():
            data["remediation"] = json.loads(rem_file.read_text())

        # Revenue data
        rev_file = Path(f"outputs/revenue/{domain}-revenue.json")
        if rev_file.exists():
            data["revenue"] = json.loads(rev_file.read_text())

        # AI summary
        summary_file = Path("outputs/summary.json")
        if summary_file.exists():
            data["summary"] = json.loads(summary_file.read_text())

        # Snapshots for trend
        snap_dir = Path("outputs/snapshots")
        if snap_dir.exists():
            snaps = sorted(snap_dir.glob(f"{domain}_*.json"))
            for s in snaps[-6:]:  # Last 6 months
                try:
                    data["snapshots"].append(json.loads(s.read_text()))
                except:
                    continue

        return data

    def generate_html(self, domain, client_config=None):
        \"\"\"Generate the complete branded HTML report.\"\"\"
        data = self.load_client_data(domain)
        rem = data.get("remediation", {})
        rev = data.get("revenue", {})
        defects = rem.get("defects", rem.get("issues", []))
        score = rem.get("score", 0)
        revenue_risk = rev.get("total_revenue_at_risk_nzd", 0)
        fix_cost = rev.get("total_fix_cost_nzd", 0)
        roi = rev.get("overall_roi_ratio", 0)
        now = datetime.now()
        month_year = now.strftime("%B %Y")

        # Build defect rows
        defect_rows = ""
        for d in defects[:15]:
            issue = d.get("issue", d.get("title", str(d)))
            priority = d.get("priority", 5)
            risk_class = "risk-critical" if priority <= 2 else "risk-high" if priority <= 4 else "risk-medium" if priority <= 6 else "risk-low"
            risk_label = "CRITICAL" if priority <= 2 else "HIGH" if priority <= 4 else "MEDIUM" if priority <= 6 else "LOW"
            # Try to get revenue impact for this defect
            rev_impact = ""
            if rev and "all_defects" in rev:
                for rd in rev["all_defects"]:
                    if rd.get("defect", "")[:20] in issue[:20]:
                        rev_impact = f"${rd['revenue_at_risk_nzd']:,.0f}/mo"
                        break
            defect_rows += f'''
            <tr>
              <td>{issue}</td>
              <td><span class="badge {risk_class}">{risk_label}</span></td>
              <td>{rev_impact or "—"}</td>
            </tr>'''

        # Build revenue top risks
        top_risks_html = ""
        if rev and "top_5_risks" in rev:
            for r in rev["top_5_risks"][:5]:
                top_risks_html += f'''
                <div class="risk-card">
                  <div class="risk-name">{r["defect"][:60]}</div>
                  <div class="risk-amount">${r["revenue_at_risk_nzd"]:,.0f}<span>/month</span></div>
                  <div class="risk-fix">Fix cost: ${r["fix_cost_nzd"]:,.0f} | Payback: {r["payback_months"]} months</div>
                </div>'''

        # Score trend (simple text-based)
        trend_html = ""
        if data["snapshots"]:
            counts = [s.get("count", 0) for s in data["snapshots"]]
            if len(counts) >= 2:
                direction = "improving" if counts[-1] < counts[-2] else "declining" if counts[-1] > counts[-2] else "stable"
                trend_html = f"<p>Site health is <strong>{direction}</strong> ({counts[-2]} defects last scan, {counts[-1]} this scan).</p>"

        # Executive summary
        exec_summary = "Automated monthly website health report."
        if data.get("summary"):
            exec_summary = data["summary"].get("summary", exec_summary)

        primary = self.agency.get("primary_color", "#06b6d4")
        secondary = self.agency.get("secondary_color", "#0f172a")

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{domain} — Monthly Website Report — {month_year}</title>
<style>
  @page {{ size: A4; margin: 15mm; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1e293b; line-height: 1.6; }}
  .page {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
  .header {{ background: {secondary}; color: white; padding: 30px; border-radius: 12px; margin-bottom: 30px; }}
  .header h1 {{ font-size: 1.6rem; color: {primary}; }}
  .header h2 {{ font-size: 1.1rem; font-weight: 400; opacity: 0.8; margin-top: 5px; }}
  .header .meta {{ margin-top: 15px; font-size: 0.85rem; opacity: 0.6; }}
  .score-section {{ display: flex; gap: 30px; align-items: center; margin-bottom: 30px; }}
  .score-ring {{ width: 100px; height: 100px; border-radius: 50%; border: 8px solid {primary};
    display: flex; align-items: center; justify-content: center; font-size: 1.8rem; font-weight: bold; flex-shrink: 0; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 30px; }}
  .kpi {{ background: #f8fafc; border-radius: 8px; padding: 15px; text-align: center; }}
  .kpi .value {{ font-size: 1.4rem; font-weight: bold; color: {primary}; }}
  .kpi .label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }}
  .section {{ margin-bottom: 30px; }}
  .section h3 {{ font-size: 1.1rem; color: {secondary}; border-bottom: 2px solid {primary}; padding-bottom: 5px; margin-bottom: 15px; }}
  .exec-summary {{ background: #f0fdfa; border-left: 4px solid {primary}; padding: 15px; border-radius: 0 8px 8px 0; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{ background: {secondary}; color: white; padding: 8px 12px; text-align: left; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; }}
  .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; color: white; }}
  .risk-critical {{ background: #dc2626; }}
  .risk-high {{ background: #ea580c; }}
  .risk-medium {{ background: #d97706; }}
  .risk-low {{ background: #16a34a; }}
  .risk-card {{ background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 12px; margin-bottom: 10px; }}
  .risk-name {{ font-weight: 600; font-size: 0.9rem; }}
  .risk-amount {{ font-size: 1.2rem; font-weight: bold; color: #dc2626; }}
  .risk-amount span {{ font-size: 0.8rem; font-weight: 400; }}
  .risk-fix {{ font-size: 0.75rem; color: #64748b; }}
  .footer {{ text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0;
    font-size: 0.75rem; color: #94a3b8; }}
  .footer a {{ color: {primary}; text-decoration: none; }}
  .recommendation {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 15px; margin-top: 15px; }}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <h1>{self.agency.get("name", "Website Agency")}</h1>
    <h2>Monthly Website Health Report: {domain}</h2>
    <div class="meta">
      Prepared for {client_config.get("client_name", domain)} | {month_year} |
      {self.contact.get("email", "")} | {self.contact.get("phone", "")}
    </div>
  </div>

  <div class="exec-summary">
    <strong>Executive Summary</strong>
    <p>{exec_summary}</p>
    {trend_html}
  </div>

  <div class="score-section">
    <div class="score-ring">{score}</div>
    <div>
      <h3>Overall Health Score</h3>
      <p>Your website scored <strong>{score}/100</strong> this month across security, SEO, performance, accessibility, and compliance checks.</p>
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi">
      <div class="value">${revenue_risk:,.0f}</div>
      <div class="label">Revenue at Risk / Month</div>
    </div>
    <div class="kpi">
      <div class="value">{len(defects)}</div>
      <div class="label">Issues Detected</div>
    </div>
    <div class="kpi">
      <div class="value">{roi}x</div>
      <div class="label">Fix ROI Ratio</div>
    </div>
  </div>

  <div class="section">
    <h3>Top Revenue Risks</h3>
    {top_risks_html or "<p>No revenue impact data available yet.</p>"}
  </div>

  <div class="section">
    <h3>All Detected Issues</h3>
    <table>
      <thead><tr><th>Issue</th><th>Severity</th><th>Revenue Impact</th></tr></thead>
      <tbody>{defect_rows or "<tr><td colspan='3'>No issues detected.</td></tr>"}</tbody>
    </table>
  </div>

  <div class="section">
    <h3>Recommended Next Steps</h3>
    <div class="recommendation">
      <p><strong>Priority 1:</strong> Address the top revenue risk items above. Estimated recovery: <strong>${revenue_risk:,.0f}/month</strong>.</p>
      <p style="margin-top:8px"><strong>Priority 2:</strong> Fix remaining medium-severity items to improve search rankings and user trust.</p>
      <p style="margin-top:8px"><strong>Investment Required:</strong> ${fix_cost:,.0f} total. <strong>Expected Payback:</strong> {"< 1 month" if roi > 1 else f"{round(1/roi, 1) if roi > 0 else 'N/A'} months"}.</p>
    </div>
  </div>

  <div class="footer">
    <p>Generated by {self.agency.get("name", "Website Agency")} | {self.agency.get("tagline", "")}</p>
    <p>{self.contact.get("website", "")} | {self.contact.get("address", "")}</p>
    <p style="margin-top:8px">This report is auto-generated from audit evidence. Findings require human review before action.</p>
  </div>

</div>
</body>
</html>'''
        return html

    def save_report(self, domain, client_config=None):
        \"\"\"Generate and save the HTML report.\"\"\"
        html = self.generate_html(domain, client_config)
        out_dir = Path("outputs/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        month = datetime.now().strftime("%Y-%m")
        out_path = out_dir / f"{domain}_{month}_report.html"
        out_path.write_text(html)
        return out_path
"""
pathlib.Path("website_auditor/reporting/generator.py").write_text(generator)
print("  [1/3] generator.py created")

# ============================================
# FILE 2: PDF Export (Playwright with fallback)
# ============================================
pdf_export = """
\"\"\"
PDF Export: Converts HTML reports to PDF using Playwright headless browser.
Falls back to HTML-only if Playwright is not installed.
\"\"\"
from pathlib import Path


def html_to_pdf(html_path, pdf_path=None):
    \"\"\"Convert an HTML file to PDF using Playwright.\"\"\"
    html_path = Path(html_path)
    if pdf_path is None:
        pdf_path = html_path.with_suffix(".pdf")
    else:
        pdf_path = Path(pdf_path)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "html_only",
            "reason": "Playwright not installed. Run: python3 -m pip install playwright && python3 -m playwright install chromium",
            "html_path": str(html_path),
        }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{html_path.resolve()}")
            page.wait_for_load_state("networkidle")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
                print_background=True,
            )
            browser.close()
        return {"status": "success", "pdf_path": str(pdf_path)}
    except Exception as e:
        return {"status": "error", "error": str(e), "html_path": str(html_path)}
"""
pathlib.Path("website_auditor/reporting/pdf_export.py").write_text(pdf_export)
print("  [2/3] pdf_export.py created")

# ============================================
# FILE 3: Email Sender (SMTP with fallback)
# ============================================
email_sender = """
\"\"\"
Email Sender: Sends monthly reports via SMTP.
Falls back to save-only if SMTP is not configured.
\"\"\"
import smtplib, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path


def send_report_email(to_email, subject, body_text, attachment_path=None, smtp_config=None):
    \"\"\"Send the monthly report email with optional PDF attachment.\"\"\"
    if not smtp_config:
        return {"status": "skipped", "reason": "No SMTP configuration provided"}

    host = smtp_config.get("smtp_host", "")
    port = smtp_config.get("smtp_port", 587)
    user = smtp_config.get("smtp_user", "")
    password = smtp_config.get("smtp_password", "")

    if not host or not user or not password:
        return {"status": "skipped", "reason": "SMTP credentials not configured in config/branding.yaml"}

    try:
        msg = MIMEMultipart()
        msg["From"] = user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "html"))

        if attachment_path and Path(attachment_path).exists():
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=Path(attachment_path).name)
                part["Content-Disposition"] = f'attachment; filename="{Path(attachment_path).name}"'
                msg.attach(part)

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

        return {"status": "sent", "to": to_email}
    except Exception as e:
        return {"status": "error", "error": str(e)}
"""
pathlib.Path("website_auditor/reporting/email_sender.py").write_text(email_sender)
print("  [3/3] email_sender.py created")
print("\\n✅ MONTHLY REPORTING ENGINE COMPLETE!")
