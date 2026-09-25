import sys, json, httpx
from pathlib import Path
from auditor_toolkit.advanced.nz_dominator import check_macrons, check_fair_trading
from auditor_toolkit.advanced.tech_fingerprint import fingerprint
from auditor_toolkit.advanced.playwright_engine import run_browser_audit
from auditor_toolkit.advanced.portfolio_db import init_portfolio_db, ingest_remediation_to_db

url = sys.argv[1] if len(sys.argv) > 1 else "https://clyne-bennie.co.nz"
print(f"\n🚀 RUNNING MASTERCLASS AUDIT: {url}\n")

# 1. Fetch Raw Data
print("1. Fetching HTML & Headers...")
try:
    resp = httpx.get(url, follow_redirects=True, timeout=15)
    html = resp.text
    headers = dict(resp.headers)
except Exception as e:
    print(f"   ❌ Failed to fetch: {e}")
    sys.exit(1)

# 2. Tech Fingerprinting (Agency Intel)
print("2. Fingerprinting Tech Stack...")
tech = fingerprint(headers, html)
print(f"   🏗️  Page Builders: {tech['page_builder'] or 'None detected'}")
print(f"   ⚡ Caching: {tech['caching'] or 'None detected'}")
print(f"   ☁️  CDN: {tech['cdn'] or 'None detected'}")

# 3. NZ Dominator Checks
print("3. Running NZ Market Checks...")
macrons = check_macrons(html)
fair_trading = check_fair_trading(html)
if macrons: print(f"   🇳🇿 Te Reo Macrons Missing: {len(macrons)}")
else: print("   🇳🇿 Te Reo Macrons: ✅ Perfect")
if fair_trading: print(f"   ⚖️  Fair Trading Risks: {fair_trading}")
else: print("   ⚖️  Fair Trading Act: ✅ Clear")

# 4. Playwright Headless Browser
print("4. Launching Headless Browser (Core Web Vitals & Cookie Lies)...")
browser_res = run_browser_audit(url)
if browser_res["status"] == "success":
    lcp = browser_res["data"]["cwv"].get("lcp_ms", "N/A")
    lie = browser_res["data"]["cookie_lie"]
    js_errs = len(browser_res["data"]["js_errors"])
    print(f"   📊 LCP (Largest Contentful Paint): {lcp}ms")
    print(f"   🍪 Cookie Consent Lie Detector: {'🚨 CAUGHT LYING!' if lie else '✅ Honest'}")
    print(f"   🐛 JavaScript Errors: {js_errs}")
else:
    print(f"   ⚠️  Browser skipped: {browser_res.get('reason')}")

# 5. DuckDB Integration
print("5. Saving to DuckDB Portfolio...")
init_portfolio_db()
rem_files = list(Path("outputs/remediations").glob("*.json"))
if rem_files:
    ingest_remediation_to_db(rem_files[0])
    print("   🗄️  Ingested into SQL database.")

print("\n🏁 MASTERCLASS AUDIT COMPLETE.")
