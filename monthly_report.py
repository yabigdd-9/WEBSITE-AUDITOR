#!/usr/bin/env python3
"""
monthly_report.py - Generate monthly PDF reports for all clients.
Usage:
  python3 monthly_report.py                  # Generate all client reports
  python3 monthly_report.py --domain X       # Generate for one client
  python3 monthly_report.py --email          # Generate + email (if SMTP configured)
  python3 monthly_report.py --pdf            # Generate HTML + convert to PDF
"""
import json, sys, os
from pathlib import Path
from datetime import datetime

os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")


def load_yaml_simple(path):
    """Minimal YAML parser for branding config (no external deps)."""
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

    from auditor_toolkit.monthly import generate_monthly
    from auditor_toolkit.browser import export_pdf
    from auditor_toolkit.agency_config import load_config, get_client, site_url
    from auditor_toolkit.revenue import calculate_revenue
    from auditor_toolkit.common import atomic_write_text

    agency_name = branding.get("agency", {}).get("name", "Website Agency")
    month_year = datetime.now().strftime("%B %Y")

    print(f"\n{'='*60}")
    print(f"  MONTHLY REPORT GENERATOR — {month_year}")
    print(f"{'='*60}\n")

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
        client_id = client.get("id", domain.replace("https://", "").split("/")[0])
        result = generate_monthly(Path("outputs/toolkit"), branding, client_id, pdf=False)
        html_path = Path(result["artifacts"]["html"])
        print(f"    HTML: {html_path}")

        # 2. Convert to PDF (if requested or by default)
        pdf_path = None
        if do_pdf or True:  # Always try PDF
            try:
                pdf_path = html_path.with_suffix(".pdf")
                export_pdf(html_path, pdf_path)
                print(f"    PDF:  {pdf_path}")
            except Exception as e:
                print(f"    PDF:  Skipped ({e})")

        # 3. Email (if configured and requested)
        if do_email:
            print(f"    Email: Draft created in outputs/toolkit/")

        generated += 1

    print(f"\n{'='*60}")
    print(f"  Generated {generated} report(s)")
    print(f"  Saved to: outputs/reports/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()