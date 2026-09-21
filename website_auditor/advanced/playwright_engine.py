
"""
Playwright Engine: Core Web Vitals lab metrics and Cookie Consent Lie Detector.
Requires: pip install playwright && playwright install chromium
"""
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
        lcp = page.evaluate("""() => {
            return new Promise((resolve) => {
                new PerformanceObserver((list) => {
                    const entries = list.getEntries();
                    resolve(entries[entries.length - 1].startTime);
                }).observe({type: 'largest-contentful-paint', buffered: true});
                setTimeout(() => resolve(null), 3000);
            });
        }""")
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
