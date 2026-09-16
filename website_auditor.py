#!/usr/bin/env python3
"""Website Rescue Auditor — NZ small business website defect detection.

Usage:
    python3 website_auditor.py <url> [--output report.md]
    python3 website_auditor.py --batch prospects.csv

Detects objectively observable defects from public data only.
No client access, login, or cooperation required.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# === DEFECT DETECTION ===

def curl_check(url: str, timeout: int = 15) -> dict:
    """Run curl and return status, headers, body preview."""
    cmd = ["curl", "-sSL", "-o", "/dev/null", "-w",
           "HTTP %{http_code}\nTIME %{time_total}\nSIZE %{size_download}\nREDIRECT %{redirect_url}\nSSL %{ssl_verify_result}",
           "--max-time", str(timeout), url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
        lines = result.stdout.strip().split("\n")
        info = {}
        for line in lines:
            if line.startswith("HTTP "): info["http_code"] = int(line.split()[1])
            elif line.startswith("TIME "): info["load_time"] = float(line.split()[1])
            elif line.startswith("SIZE "): info["size"] = int(line.split()[1])
            elif line.startswith("REDIRECT "): info["redirect"] = line[9:]
            elif line.startswith("SSL "): info["ssl_result"] = int(line.split()[1])
        return info
    except Exception as e:
        return {"error": str(e)}

def curl_headers(url: str, timeout: int = 15) -> dict:
    """Get HTTP headers."""
    cmd = ["curl", "-sLI", "--max-time", str(timeout), url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
        headers = {}
        for line in result.stdout.split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                headers[key.strip().lower()] = val.strip()
        return headers
    except Exception:
        return {}

def curl_body(url: str, timeout: int = 15) -> str:
    """Fetch page body."""
    cmd = ["curl", "-sSL", "--max-time", str(timeout), url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
        return result.stdout[:5000]
    except Exception:
        return ""

def check_ssl(domain: str) -> dict:
    """Check SSL certificate validity."""
    cmd = ["bash", "-c", f"echo | openssl s_client -servername {domain} -connect {domain}:443 2>/dev/null | openssl x509 -noout -dates 2>/dev/null"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = result.stdout
        issues = {}
        if "notBefore" in output:
            match = re.search(r"notAfter=(\w+ \d+ \d+:\d+:\d+ \d+ \w+)", output)
            if match:
                expiry_str = match.group(1)
                try:
                    expiry = datetime.strptime(expiry_str, "%b %d %H:%M:%S %Y %Z")
                    days_left = (expiry - datetime.utcnow()).days
                    issues["expiry_date"] = expiry.isoformat()
                    issues["days_remaining"] = days_left
                    if days_left < 0:
                        issues["expired"] = True
                    elif days_left < 30:
                        issues["expiring_soon"] = True
                except ValueError:
                    pass
        if "Verify return code: 0" not in result.stdout and result.returncode != 0:
            issues["ssl_error"] = True
        return issues
    except Exception as e:
        return {"error": str(e)}

def check_page_speed(url: str) -> dict:
    """Get PageSpeed Insights scores."""
    api_key = os.environ.get("GOOGLE_PSI_API_KEY", "")
    base = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = f"?url={url}&strategy=mobile&category=performance&category=seo&category=accessibility&category=best-practices"
    if api_key:
        params += f"&key={api_key}"
    try:
        req = urllib.request.Request(base + params, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        lighthouse = data.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        scores = {}
        for cat in ["performance", "seo", "accessibility", "best-practices"]:
            if cat in categories:
                scores[cat] = round(categories[cat].get("score", 0) * 100)
        return scores
    except Exception as e:
        return {"error": str(e)}

def check_w3c_markup(url: str) -> dict:
    """Check HTML markup validity via W3C Nu validator."""
    api_url = f"https://validator.w3.org/nu/?doc={url}&out=json"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        errors = []
        warnings = []
        for msg in data.get("messages", []):
            if msg.get("type") == "error":
                errors.append(msg.get("message", ""))
            elif msg.get("type") == "info" and msg.get("subType") == "warning":
                warnings.append(msg.get("message", ""))
        return {"error_count": len(errors), "warning_count": len(warnings), "errors": errors[:5]}
    except Exception as e:
        return {"error": str(e)}

def check_title_meta(body: str) -> dict:
    """Extract title and meta description."""
    results = {}
    title_match = re.search(r"<title>([^<]*)</title>", body, re.IGNORECASE)
    desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', body, re.IGNORECASE)
    results["title"] = title_match.group(1) if title_match else None
    results["meta_description"] = desc_match.group(1) if desc_match else None
    return results

def check_copyright(body: str) -> dict:
    """Check copyright year."""
    year_match = re.search(r"©\s*(\d{4})", body)
    if year_match:
        year = int(year_match.group(1))
        current_year = datetime.now().year
        if year < current_year:
            return {"stale": True, "year": year, "current": current_year}
    return {"stale": False}

def check_contact_form(body: str) -> dict:
    """Check if contact form exists."""
    has_form = bool(re.search(r"<form", body, re.IGNORECASE))
    has_email = bool(re.search(r'mailto:', body, re.IGNORECASE)) or bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', body))
    return {"has_form": has_form, "has_email": has_email}

def check_social_links(body: str) -> list:
    """Extract social media links."""
    social_patterns = {
        "facebook": r'facebook\.com/[^"\'\s]+',
        "instagram": r'instagram\.com/[^"\'\s]+',
        "twitter": r'twitter\.com/[^"\'\s]+',
        "linkedin": r'linkedin\.com/[^"\'\s]+',
    }
    links = {}
    for platform, pattern in social_patterns.items():
        matches = re.findall(pattern, body, re.IGNORECASE)
        if matches:
            links[platform] = list(set(matches))[:3]
    return links

def check_mobile_responsive(body: str) -> dict:
    """Check viewport meta tag."""
    has_viewport = bool(re.search(r'<meta[^>]*name=["\']viewport["\']', body, re.IGNORECASE))
    return {"has_viewport": has_viewport}

def check_broken_links(base_url: str, body: str, sample_size: int = 10) -> list:
    """Check a sample of internal links for 404s."""
    # Extract hrefs
    hrefs = re.findall(r'href=["\'](/[^"\']*|https?://[^"\']*)["\']', body, re.IGNORECASE)
    internal = [h for h in hrefs if h.startswith("/") and len(h) > 1][:sample_size]
    base = re.match(r"(https?://[^/]+)", base_url)
    if not base:
        return []
    base_domain = base.group(1)
    
    broken = []
    for href in internal[:5]:  # Limit to 5 for speed
        full_url = base_domain + href
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status >= 400:
                    broken.append({"url": full_url, "status": resp.status})
        except urllib.error.HTTPError as e:
            if e.code >= 400:
                broken.append({"url": full_url, "status": e.code})
        except Exception:
            pass
    return broken

# === MAIN AUDIT ===

def audit_website(url: str) -> dict:
    """Run full audit on a website."""
    print(f"🔍 Auditing: {url}")
    
    domain = re.match(r"https?://([^/]+)", url)
    domain = domain.group(1) if domain else url
    
    defects = []
    score = 0
    evidence = {}
    
    # 1. Basic fetch
    print("  Checking HTTP status...")
    curl_info = curl_check(url)
    if curl_info.get("http_code", 0) != 200:
        defects.append({
            "defect": f"HTTP {curl_info.get('http_code', 'error')}",
            "how": f"curl returned status {curl_info.get('http_code')}",
            "impact": "Site may be down or returning errors to visitors and search engines"
        })
        score += 30
    
    # 2. SSL
    print("  Checking SSL...")
    ssl_info = check_ssl(domain)
    if ssl_info.get("expired"):
        defects.append({
            "defect": "Expired SSL certificate",
            "how": f"Certificate expired {ssl_info.get('days_remaining', '?')} days ago",
            "impact": "Browser security warnings block visitors; trust destroyed"
        })
        score += 25
    elif ssl_info.get("expiring_soon"):
        defects.append({
            "defect": "SSL certificate expiring soon",
            "how": f"Certificate expires in {ssl_info.get('days_remaining', '?')} days",
            "impact": "Imminent outage risk if not renewed"
        })
        score += 10
    
    # 3. Page body checks
    print("  Analyzing page content...")
    body = curl_body(url)
    
    # 4. Title/Meta
    meta = check_title_meta(body)
    if not meta.get("title"):
        defects.append({
            "defect": "Missing page title",
            "how": "No <title> tag found in HTML source",
            "impact": "Google shows blank/untitled results; visitors see no context"
        })
        score += 15
    if not meta.get("meta_description"):
        defects.append({
            "defect": "Missing meta description",
            "how": "No <meta name='description'> found",
            "impact": "Lower click-through from search results"
        })
        score += 10
    
    # 5. Copyright
    copyright_info = check_copyright(body)
    if copyright_info.get("stale"):
        defects.append({
            "defect": f"Stale copyright year ({copyright_info['year']})",
            "how": f"Footer shows © {copyright_info['year']} but current year is {copyright_info['current']}",
            "impact": "Signals abandoned site; visitors may assume business closed"
        })
        score += 8
    
    # 6. Contact form
    contact = check_contact_form(body)
    if not contact["has_form"]:
        defects.append({
            "defect": "No contact form",
            "how": "No <form> element found on contact page",
            "impact": "Every enquiry requires manual step; leads are lost"
        })
        score += 12
    
    # 7. Mobile responsive
    mobile = check_mobile_responsive(body)
    if not mobile["has_viewport"]:
        defects.append({
            "defect": "Not mobile-responsive (no viewport meta)",
            "how": "No <meta name='viewport'> tag found",
            "impact": "Site unusable on mobile; Google penalises in mobile search"
        })
        score += 15
    
    # 8. Social links
    social = check_social_links(body)
    evidence["social_links"] = list(social.keys())
    
    # 9. Broken links
    print("  Checking for broken links...")
    broken = check_broken_links(url, body)
    if broken:
        defects.append({
            "defect": f"{len(broken)} broken link(s) detected",
            "how": "Sampled internal links returned HTTP 4xx errors",
            "impact": "Frustrates visitors and wastes marketing spend"
        })
        score += 10
    
    # 10. Page speed
    print("  Running PageSpeed Insights...")
    psi_scores = check_page_speed(url)
    if isinstance(psi_scores, dict) and "error" not in psi_scores:
        if psi_scores.get("performance", 100) < 50:
            defects.append({
                "defect": f"Slow page speed (Performance: {psi_scores.get('performance', '?')}/100)",
                "how": "Google PageSpeed Insights performance score below 50",
                "impact": "Google ranking penalty; 1s delay cuts conversions ~7%"
            })
            score += 15
        evidence["psi_scores"] = psi_scores
    
    # 11. W3C Markup
    print("  Checking HTML validity...")
    markup = check_w3c_markup(url)
    if isinstance(markup, dict) and "error" not in markup:
        if markup.get("error_count", 0) > 0:
            defects.append({
                "defect": f"{markup['error_count']} HTML markup error(s)",
                "how": f"W3C validator found {markup['error_count']} errors",
                "impact": "Inconsistent rendering across browsers; SEO impact"
            })
            score += 8
        evidence["w3c_errors"] = markup.get("error_count", 0)
    
    # Cap at 100
    score = min(score, 100)
    
    return {
        "url": url,
        "domain": domain,
        "defects": defects,
        "defect_count": len(defects),
        "score": score,
        "evidence": evidence,
        "meta": meta,
        "social": list(social.keys()),
        "timestamp": datetime.now().isoformat()
    }

def generate_report(audit: dict) -> str:
    """Generate a mini-audit report in Markdown."""
    url = audit["url"]
    defects = audit["defects"]
    score = audit["score"]
    
    # Tier
    if score >= 80:
        tier = "🔥 HOT"
    elif score >= 60:
        tier = "🌡️ WARM"
    elif score >= 40:
        tier = "📊 NURTURE"
    else:
        tier = "❄️ COLD"
    
    lines = [
        f"# Website Audit: {url}",
        f"**Score:** {score}/100 — {tier}",
        f"**Defects Found:** {audit['defect_count']}",
        f"**Date:** {audit['timestamp'][:10]}",
        "",
        "## Defects",
        ""
    ]
    
    if not defects:
        lines.append("No defects detected. Site appears well-maintained.")
    else:
        for i, d in enumerate(defects, 1):
            lines.append(f"### {i}. {d['defect']}")
            lines.append(f"- **How detected:** {d['how']}")
            lines.append(f"- **Business impact:** {d['impact']}")
            lines.append("")
    
    lines.append("## Evidence")
    lines.append(f"- Social links found: {', '.join(audit.get('social', [])) or 'None'}")
    if "psi_scores" in audit.get("evidence", {}):
        lines.append(f"- PageSpeed: {json.dumps(audit['evidence']['psi_scores'])}")
    lines.append(f"- Title: {audit.get('meta', {}).get('title', 'N/A')}")
    lines.append(f"- Meta description: {'Yes' if audit.get('meta', {}).get('meta_description') else 'No'}")
    lines.append("")
    lines.append("## Next Step")
    lines.append("Reply 'send' to email this audit to the business owner (requires consent gate approval).")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by CATALYX Website Rescue Auditor — defects detected from public data only.*")
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="NZ Website Rescue Auditor")
    parser.add_argument("url", nargs="?", help="Website URL to audit")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    if not args.url:
        # Demo mode
        print("Usage: python3 website_auditor.py <url> [--output report.md]")
        print("Example: python3 website_auditor.py https://example.com")
        sys.exit(1)
    
    url = args.url
    if not url.startswith("http"):
        url = "https://" + url
    
    audit = audit_website(url)
    
    if args.json:
        output = json.dumps(audit, indent=2)
    else:
        output = generate_report(audit)
    
    if args.output:
        Path(args.output).write_text(output)
        print(f"\n✅ Report saved to {args.output}")
    else:
        print("\n" + output)
    
    # Save audit data
    audit_path = Path("audits")
    audit_path.mkdir(exist_ok=True)
    safe_name = re.sub(r'[^\w.-]', '_', audit['domain'])
    (audit_path / f"{safe_name}.json").write_text(json.dumps(audit, indent=2))

if __name__ == "__main__":
    main()
