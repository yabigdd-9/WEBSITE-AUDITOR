import pathlib

cli = """#!/usr/bin/env python3
\"\"\"
monthly_report.py - Generate monthly PDF reports for all clients.
Usage:
  python3 monthly_report.py                  # Generate all client reports
  python3 monthly_report.py --domain X       # Generate for one client
  python3 monthly_report.py --email          # Generate + email (if SMTP configured)
  python3 monthly_report.py --pdf            # Generate HTML + convert to PDF
\"\"\"
import json, sys, os
from pathlib import Path
from datetime import datetime

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")


def load_yaml_simple(path):
    \"\"\"Minimal YAML parser for branding config (no external deps).\"\"\"
    config = {}
    current_section = None
    current_list = None
    current_item = None

    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        if stripped.endswith(":") and indent == 0:
            current_section = stripped[:-1].strip()
            config[current_section] = {}
            current_list = None
            current_item = None
        elif stripped.startswith("- ") and current_section:
            if not isinstance(config.get(current_section), list):
                config[current_section] = []
            current_item = {}
            config[current_section].append(current_item)
            kv = stripped[2:].strip()
            if ":" in kv:
                k, v = kv.split(":", 1)
                current_item[k.strip()] = v.strip().strip('"').strip("'")
        elif ":" in stripped and current_item is not None:
            k, v = stripped.split(":", 1)
            current_item[k.strip()] = v.strip().strip('"').strip("'")
        elif ":" in stripped and current_section and isinstance(config.get(current_section), dict):
            k, v = stripped.split(":", 1)
            v = v.strip().strip('"').strip("'")
            if v.lower() == "true": v = True
            elif v.lower() == "false": v = False
            elif v.isdigit(): v = int(v)
            config[current_section][k.strip()] = v

    return config


def main():
    do_email = "--email" in sys.argv
    do_pdf = "--pdf" in sys.argv
    domain_filter = None
    for i, arg in enumerate(sys.argv):
        if arg == "--domain" and i + 1 < len(sys.argv):
            domain_filter = sys.argv[i + 1]

    # Load branding config
    branding_path = Path("config/branding.yaml")
    if not branding_path.exists():
        print("No branding config found. Run: python3 make_branding.py")
        return

    branding = load_yaml_simple(branding_path)
    clients = branding.get("clients", [])
    if not isinstance(clients, list):
        clients = []

    from website_auditor.reporting.generator import MonthlyReportGenerator
    from website_auditor.reporting.pdf_export import html_to_pdf
    from website_auditor.reporting.email_sender import send_report_email

    gen = MonthlyReportGenerator(branding)
    agency_name = branding.get("agency", {}).get("name", "Website Agency")
    month_year = datetime.now().strftime("%B %Y")

    print(f"\\n{'='*60}")
    print(f"  MONTHLY REPORT GENERATOR — {month_year}")
    print(f"{'='*60}\\n")

    # If no clients configured, scan remediation outputs
    if not clients:
        rem_dir = Path("outputs/remediations")
        if rem_dir.exists():
            for f in sorted(rem_dir.glob("*-remediation.json")):
                domain = f.stem.replace("-remediation", "")
                if "summary" in domain:
                    continue
                clients.append({"domain": domain, "client_name": domain, "client_email": ""})

    generated = 0
    for client in clients:
        domain = client.get("domain", "")
        if not domain or "summary" in domain:
            continue
        if domain_filter and domain_filter not in domain:
            continue

        print(f"  Generating report for: {domain}")

        # 1. Generate HTML
        html_path = gen.save_report(domain, client)
        print(f"    HTML: {html_path}")

        # 2. Convert to PDF (if requested or by default)
        pdf_path = None
        if do_pdf or True:  # Always try PDF
            result = html_to_pdf(html_path)
            if result["status"] == "success":
                pdf_path = result["pdf_path"]
                print(f"    PDF:  {pdf_path}")
            else:
                print(f"    PDF:  Skipped ({result.get('reason', result.get('error', 'unknown'))})")

        # 3. Email (if configured and requested)
        if do_email:
            client_email = client.get("client_email", "")
            if client_email:
                smtp_config = branding.get("reporting", {})
                subject = f"Your Monthly Website Report — {month_year}"
                body = f"<p>Kia ora {client.get('client_name', '')},</p><p>Please find your monthly website health report attached.</p><p>Ngā mihi,<br>{agency_name}</p>"
                email_result = send_report_email(
                    client_email, subject, body,
                    attachment_path=pdf_path or html_path,
                    smtp_config=smtp_config
                )
                print(f"    Email: {email_result['status']}")
            else:
                print(f"    Email: Skipped (no client email configured)")

        generated += 1

    print(f"\\n{'='*60}")
    print(f"  Generated {generated} report(s)")
    print(f"  Saved to: outputs/reports/")
    print(f"{'='*60}\\n")


if __name__ == "__main__":
    main()
"""
pathlib.Path("monthly_report.py").write_text(cli)
print("✅ monthly_report.py created")
