import pathlib

pathlib.Path("website_auditor/advanced").mkdir(parents=True, exist_ok=True)
pathlib.Path("website_auditor/advanced/__init__.py").touch()

# ==========================================
# MODULE 1: NZ MARKET DOMINATOR (Path 3)
# ==========================================
nz_code = """
\"\"\"
NZ Dominator: Macron validation, NZBN API, and Fair Trading Act heuristics.
\"\"\"
import re, urllib.request, json

MACRON_DICT = {
    "Maori": "Māori", "Whakatane": "Whakatāne", "Wanganui": "Whanganui",
    "Waikato": "Waikato", "Tauranga": "Tauranga", "Rotorua": "Rotorua",
    "Kawerau": "Kawerau", "Opotiki": "Ōpōtiki", "Whangarei": "Whangārei"
}

ILLEGAL_CLAIMS = [
    r"\\bguaranteed cheapest\\b", r"\\bnumber one in nz\\b", 
    r"\\bfree \\w+ \\(no catch\\)\\b", r"\\bcountdown timer\\b"
]

def check_macrons(html_text):
    missing = []
    for wrong, right in MACRON_DICT.items():
        if re.search(rf"\\b{wrong}\\b", html_text, re.IGNORECASE) and right not in html_text:
            missing.append(f"Missing macron: '{wrong}' should be '{right}'")
    return missing

def check_fair_trading(html_text):
    flags = []
    for pattern in ILLEGAL_CLAIMS:
        if re.search(pattern, html_text, re.IGNORECASE):
            flags.append(f"Potential Fair Trading Act risk: '{pattern}'")
    return flags

def lookup_nzbn(nzbn_number):
    \"\"\"Stub for NZBN public register API.\"\"\"
    if not nzbn_number or len(str(nzbn_number)) != 13:
        return {"status": "invalid_format"}
    # In production, this hits the public NZBN API
    return {"status": "verified_stub", "nzbn": nzbn_number, "entity_type": "NZ Limited Company"}
"""
pathlib.Path("website_auditor/advanced/nz_dominator.py").write_text(nz_code)


# ==========================================
# MODULE 2: AGENCY INTELLIGENCE (Path 2)
# ==========================================
intel_code = """
\"\"\"
Tech Fingerprinting: Detects CMS, Page Builders, Caching, and CDNs.
\"\"\"
import re

SIGNATURES = {
    "page_builder": {
        "Elementor": ["elementor", "elementor-front", "elementor-widget"],
        "Divi": ["et_pb_section", "divi", "et_builder"],
        "WPBakery": ["vc_row", "wpb_row", "js_composer"],
        "Bricks": ["bricks-page", "brxe-"],
    },
    "caching": {
        "WP Rocket": ["wp-rocket", "rocket-loader"],
        "LiteSpeed": ["litespeed", "lscache"],
        "W3 Total Cache": ["w3tc", "w3-total-cache"],
    },
    "cdn": {
        "Cloudflare": ["cf-ray", "cloudflare", "cf-cache-status"],
        "Fastly": ["fastly", "x-served-by: cache-"],
        "AWS CloudFront": ["x-amz-cf-id", "cloudfront.net"],
    }
}

def fingerprint(headers, html_source):
    found = {"page_builder": [], "caching": [], "cdn": []}
    html_lower = (html_source or "").lower()
    headers_str = str(headers or {}).lower()
    
    for category, tools in SIGNATURES.items():
        for tool_name, sigs in tools.items():
            for sig in sigs:
                if sig.lower() in html_lower or sig.lower() in headers_str:
                    found[category].append(tool_name)
                    break
    return {k: list(set(v)) for k, v in found.items()}
"""
pathlib.Path("website_auditor/advanced/tech_fingerprint.py").write_text(intel_code)


# ==========================================
# MODULE 3: HEADLESS BROWSER / PLAYWRIGHT (Path 1)
# ==========================================
pw_code = """
\"\"\"
Playwright Engine: Core Web Vitals lab metrics and Cookie Consent Lie Detector.
Requires: pip install playwright && playwright install chromium
\"\"\"
import json

def run_browser_audit(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"status": "skipped", "reason": "Playwright not installed"}

    results = {"cwv": {}, "cookie_lie": False, "js_errors": []}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Capture JS Errors
        page.on("pageerror", lambda err: results["js_errors"].append(str(err)))
        
        # 1. Measure LCP (Largest Contentful Paint)
        page.goto(url, wait_until="networkidle")
        lcp = page.evaluate(\"\"\"() => {
            return new Promise((resolve) => {
                new PerformanceObserver((list) => {
                    const entries = list.getEntries();
                    resolve(entries[entries.length - 1].startTime);
                }).observe({type: 'largest-contentful-paint', buffered: true});
                setTimeout(() => resolve(null), 3000);
            });
        }\"\"\")
        results["cwv"]["lcp_ms"] = round(lcp, 2) if lcp else "timeout"
        
        # 2. Cookie Consent Lie Detector
        # Look for a reject button, click it, and see if GA/Meta pixels still fire
        reject_selectors = ["button:has-text('Reject')", "button:has-text('Decline')", "button:has-text('Necessary only')"]
        clicked_reject = False
        for sel in reject_selectors:
            try:
                if page.locator(sel).first.is_visible(timeout=2000):
                    page.locator(sel).first.click()
                    clicked_reject = True
                    break
            except: continue
            
        if clicked_reject:
            # Check if tracking scripts are still loading
            cookies = page.context.cookies()
            tracking_cookies = [c for c in cookies if any(x in c['name'].lower() for x in ['_ga', '_fbp', '_gcl'])]
            if tracking_cookies:
                results["cookie_lie"] = True # They claimed to reject, but tracking cookies are still set!
                
        browser.close()
        return {"status": "success", "data": results}
"""
pathlib.Path("website_auditor/advanced/playwright_engine.py").write_text(pw_code)


# ==========================================
# MODULE 4: DUCKDB PORTFOLIO SCALE (Path 4)
# ==========================================
db_code = """
\"\"\"
Portfolio DB: Replaces flat JSON with DuckDB for instant SQL querying across 1000s of sites.
Requires: pip install duckdb
\"\"\"
import json
from pathlib import Path

def init_portfolio_db(db_path="outputs/portfolio.duckdb"):
    try:
        import duckdb
    except ImportError:
        return {"status": "skipped", "reason": "duckdb not installed"}
        
    con = duckdb.connect(db_path)
    con.execute(\"\"\"
        CREATE TABLE IF NOT EXISTS site_health (
            domain VARCHAR, scan_date DATE, score INTEGER, 
            critical_issues INTEGER, cms VARCHAR, lcp_ms DOUBLE
        )
    \"\"\")
    con.close()
    return {"status": "initialized", "path": db_path}

def ingest_remediation_to_db(json_path, db_path="outputs/portfolio.duckdb"):
    try:
        import duckdb
    except ImportError: return
        
    data = json.loads(Path(json_path).read_text())
    domain = Path(json_path).stem.replace("-remediation", "")
    score = data.get("score", 0)
    issues = len(data.get("defects", data.get("issues", [])))
    
    con = duckdb.connect(db_path)
    con.execute(\"\"\"
        INSERT INTO site_health (domain, scan_date, score, critical_issues, cms, lcp_ms) 
        VALUES (?, CURRENT_DATE, ?, ?, ?, ?)
    \"\"\", [domain, score, issues, "detected", None])
    con.close()
"""
pathlib.Path("website_auditor/advanced/portfolio_db.py").write_text(db_code)

print("✅ MASTERCLASS SUITE GENERATED SUCCESSFULLY!")
print("   - NZ Dominator (Macrons & Fair Trading)")
print("   - Tech Fingerprint (Elementor, Divi, Cloudflare)")
print("   - Playwright Engine (CWV & Cookie Lie Detector)")
print("   - DuckDB Portfolio Scale")
