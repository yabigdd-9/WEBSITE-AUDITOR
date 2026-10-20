import sys
import json
import requests
from plugins.tech_stack_detector import detect_tech_stack
from plugins.dns_email_validator import audit_email_security
from plugins.ux_dark_pattern_scanner import scan_dark_patterns
from plugins.image_perf_auditor import audit_image_performance

if len(sys.argv) < 2:
    print("Usage: python3 advanced_audit.py <url>")
    sys.exit(1)

url = sys.argv[1]
print(f"🚀 Running Advanced Plugins on {url}...")

try:
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0'}
    response = requests.get(url, headers=headers, timeout=15)
    html = response.text
except Exception as e:
    print(f"Failed to fetch URL: {e}")
    sys.exit(1)

results = {
    "url": url,
    "tech_stack_detected": detect_tech_stack(html, response.headers),
    "email_security_dns": audit_email_security(url),
    "ux_dark_patterns": scan_dark_patterns(html),
    "image_performance": audit_image_performance(html)
}

print(json.dumps(results, indent=2))
