#!/usr/bin/env python3
"""Remediation Engine — auto-generate fix suggestions + HTML patches from audit data.

Usage:
    python3 remediation-engine.py <audit.json>
    python3 remediation-engine.py --batch audits/
    python3 remediation-engine.py --all --output-dir outputs/remediations

Generates:
  - Per-defect fix suggestions with code snippets
  - HTML patch files ready to apply
  - Priority-ranked action queue
  - Cost/time estimates for each fix
"""

import argparse, json, os, re, sys
from pathlib import Path
from datetime import datetime

from auditor_core.remediation import initial_remediation

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"

# Fix templates: defect_key → {title, effort, cost, code_snippet, docs}
FIX_LIBRARY = {
    "ssl_expired": {
        "title": "Renew SSL Certificate",
        "effort": "15 min", "cost": "Free (Let's Encrypt) or $0-50/mo (hosting)",
        "code": None,  # handled by hosting
        "docs": "https://letsencrypt.org/getting-started/",
        "steps": [
            "1. SSH into hosting/server",
            "2. sudo certbot certonly --standalone -d yourdomain.nz",
            "3. Update web server config to point to /etc/letsencrypt/live/yourdomain.nz/",
            "4. Reload: sudo systemctl reload nginx",
            "5. Set auto-renewal: sudo certbot renew --dry-run",
        ]
    },
    "ssl_expiring_soon": {
        "title": "Renew Expiring SSL",
        "effort": "10 min", "cost": "Free",
        "code": None,
        "docs": "https://letsencrypt.org/docs/renewal/",
        "steps": ["Run: certbot renew", "Reload web server", "Verify: openssl s_client -connect yourdomain.nz:443"]
    },
    "http_error": {
        "title": "Fix HTTP Error",
        "effort": "30 min", "cost": "Free",
        "code": None,
        "docs": "https://httpstatus.es/",
        "steps": ["Check hosting status", "Verify DNS A record points to correct IP", "Check server error logs", "Restart web server if needed"]
    },
    "missing_title": {
        "title": "Add Page Title Tag",
        "effort": "5 min/page", "cost": "Free",
        "code": "<title>Your Keyword | Business Name</title>",
        "docs": "https://developers.google.com/search/docs/appearance/title-link",
        "steps": ["Add <title> to <head> on each page", "Keep under 60 characters", "Include primary keyword"]
    },
    "missing_meta_description": {
        "title": "Add Meta Description",
        "effort": "5 min/page", "cost": "Free",
        "code": '<meta name="description" content="Compelling summary with keyword, 150-160 chars">',
        "docs": "https://developers.google.com/search/docs/appearance/snippet",
        "steps": ["Add meta description to each page", "Include primary keyword naturally", "Keep 150-160 characters"]
    },
    "stale_copyright": {
        "title": "Update Copyright Year",
        "effort": "2 min", "cost": "Free",
        "code": f"© {datetime.now().year} Business Name. All rights reserved.",
        "docs": None,
        "steps": ["Find footer copyright text", "Update year to current", "Use dynamic year: {new_year}"]
    },
    "no_contact_form": {
        "title": "Add Contact Form",
        "effort": "15 min", "cost": "Free (Formspree/Netlify)",
        "code": '<form action="https://formspree.io/f/YOUR_ID" method="POST"><input name="email" type="email" required><textarea name="message" required></textarea><button type="submit">Send</button></form>',
        "docs": "https://formspree.io/",
        "steps": ["Sign up at formspree.io (free)", "Add form HTML to contact page", "Verify email forwarding works"]
    },
    "no_viewport": {
        "title": "Add Viewport Meta Tag",
        "effort": "1 min", "cost": "Free",
        "code": '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "docs": "https://developer.mozilla.org/en-US/docs/Web/HTML/Viewport_meta_tag",
        "steps": ["Add viewport meta to <head> of every page", "Test on mobile devices"]
    },
    "broken_links": {
        "title": "Fix Broken Links",
        "effort": "10-30 min", "cost": "Free",
        "code": None,
        "docs": "https://support.google.com/webmasters/answer/9019367",
        "steps": ["Identify broken URLs", "Fix or remove links", "Set 301 redirects for moved pages", "Re-scan to verify"]
    },
    "slow_page": {
        "title": "Optimize Page Speed",
        "effort": "1-4 hours", "cost": "Free-$50/mo (CDN)",
        "code": None,
        "docs": "https://developers.google.com/speed/docs/insights",
        "steps": [
            "Compress images to WebP/AVIF",
            "Enable gzip/brotli on server",
            "Minify CSS/JS (use esbuild/terser)",
            "Add CDN (Cloudflare free tier)",
            "Lazy-load below-fold images",
            "Target: <3s load time on 4G"
        ]
    },
    "html_errors": {
        "title": "Fix HTML Validation Errors",
        "effort": "15-60 min", "cost": "Free",
        "code": None,
        "docs": "https://validator.w3.org/",
        "steps": ["Run W3C validator", "Fix missing closing tags", "Validate nested elements", "Re-validate"]
    },
    "no_h1": {
        "title": "Add H1 Tag",
        "effort": "2 min/page", "cost": "Free",
        "code": "<h1>Primary Page Topic / Keyword</h1>",
        "docs": "https://developers.google.com/search/docs/appearance/structured-data",
        "steps": ["Add one <h1> per page", "Match search intent", "Keep descriptive"]
    },
    "multiple_h1": {
        "title": "Consolidate H1 Tags",
        "effort": "5 min/page", "cost": "Free",
        "code": "<!-- Keep one <h1>, use <h2>-<h6> for subsections -->",
        "docs": None,
        "steps": ["Keep only one <h1> per page", "Move extras to <h2>-<h6>"]
    },
    "missing_alt_text": {
        "title": "Add Image Alt Text",
        "effort": "5 min/page", "cost": "Free",
        "code": '<img src="photo.jpg" alt="Descriptive text of image">',
        "docs": "https://www.w3.org/WAI/tutorials/images/",
        "steps": ["Add alt to all <img> tags", "Describe the image content", "Empty alt for decorative images"]
    },
    "no_security_headers": {
        "title": "Add Security Headers",
        "effort": "15 min", "cost": "Free",
        "code": "Strict-Transport-Security: max-age=31536000; includeSubDomains\nContent-Security-Policy: default-src 'self'\nX-Frame-Options: DENY\nX-Content-Type-Options: nosniff",
        "docs": "https://securityheaders.com/",
        "steps": [
            "Add HSTS header",
            "Configure CSP (start with report-only)",
            "Set X-Frame-Options to DENY",
            "Add X-Content-Type-Options: nosniff",
            "Test at securityheaders.com"
        ]
    },
    "no_robots_txt": {
        "title": "Create robots.txt",
        "effort": "5 min", "cost": "Free",
        "code": "User-agent: *\nAllow: /\nSitemap: https://yourdomain.nz/sitemap.xml",
        "docs": "https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt",
        "steps": ["Create /robots.txt", "Allow key paths", "Add sitemap URL", "Submit to Google Search Console"]
    },
    "no_sitemap": {
        "title": "Create sitemap.xml",
        "effort": "10 min", "cost": "Free",
        "code": None,
        "docs": "https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap",
        "steps": ["Generate sitemap (plugin or static)", "Upload to /sitemap.xml", "Submit to Google & Bing"]
    },
    "no_structured_data": {
        "title": "Add Structured Data (Schema.org)",
        "effort": "30 min", "cost": "Free",
        "code": '<script type="application/ld+json">\n{"@context":"https://schema.org","@type":"LocalBusiness","name":"Business","url":"https://yourdomain.nz"}\n</script>',
        "docs": "https://schema.org/LocalBusiness",
        "steps": ["Choose schema type (LocalBusiness, Service, etc.)", "Add JSON-LD to <head>", "Test at schema.org validator"]
    },
    "no_og_tags": {
        "title": "Add Open Graph Tags",
        "effort": "5 min/page", "cost": "Free",
        "code": '<meta property="og:title" content="Page Title">\n<meta property="og:description" content="Description">\n<meta property="og:image" content="https://yourdomain.nz/image.jpg">',
        "docs": "https://ogp.me/",
        "steps": ["Add og:title, og:description, og:image", "Test with Facebook Debugger"]
    },
    "no_canonical": {
        "title": "Add Canonical URL",
        "effort": "2 min/page", "cost": "Free",
        "code": '<link rel="canonical" href="https://yourdomain.nz/page">',
        "docs": "https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls",
        "steps": ["Add canonical link to each page", "Point to preferred URL version"]
    },
    "no_privacy_policy": {
        "title": "Add Privacy Policy",
        "effort": "1 hour", "cost": "Free (generator) or $50 lawyer",
        "code": None,
        "docs": "https://app.termly.io/generator/privacy-policy",
        "steps": ["Generate policy (Termly/FreePrivacyPolicy)", "Add page to site", "Link in footer"]
    },
    "no_cookie_consent": {
        "title": "Add Cookie Consent Banner",
        "effort": "15 min", "cost": "Free (CookieYes/Osano)",
        "code": None,
        "docs": "https://www.cookieyes.com/",
        "steps": ["Sign up for free cookie consent", "Add script to site", "Configure cookie categories"]
    },
    "no_social_links": {
        "title": "Add Social Media Links",
        "effort": "5 min", "cost": "Free",
        "code": '<a href="https://facebook.com/yourpage">Facebook</a>',
        "docs": None,
        "steps": ["Add social links to footer", "Match business platforms"]
    },
}

# Stable taxonomy check ID -> existing remediation recipe.
CHECK_ID_TO_FIX_KEY = {
    "security.tls_expired": "ssl_expired",
    "security.tls_expiring": "ssl_expiring_soon",
    "security.tls_verification_failed": "ssl_expired",
    "security.hsts_missing": "no_security_headers",
    "security.csp_missing": "no_security_headers",
    "security.x_frame_options_missing": "no_security_headers",
    "security.x_content_type_options_missing": "no_security_headers",
    "security.referrer_policy_missing": "no_security_headers",
    "security.permissions_policy_missing": "no_security_headers",
    "seo.h1_missing": "no_h1",
    "seo.multiple_h1": "multiple_h1",
    "seo.title_missing": "missing_title",
    "seo.meta_description_missing": "missing_meta_description",
    "seo.noindex": "no_robots_txt",
    "seo.canonical_missing": "no_canonical",
    "seo.open_graph_missing": "no_og_tags",
    "seo.schema_missing": "no_structured_data",
    "accessibility.image_alt_missing": "missing_alt_text",
    "technical.html_errors": "html_errors",
    "technical.broken_links": "broken_links",
    "technical.site_unreachable": "http_error",
}

# Map from defect description keywords → defect_key for backward compat
DEFECT_TEXT_TO_KEY = {
    "expired ssl": "ssl_expired",
    "ssl expiring": "ssl_expiring_soon",
    "ssl verification": "ssl_expired",
    "http ": "http_error",
    "site unreachable": "http_error",
    "missing page title": "missing_title",
    "missing title": "missing_title",
    "missing meta description": "missing_meta_description",
    "missing meta": "missing_meta_description",
    "stale copyright": "stale_copyright",
    "no contact form": "no_contact_form",
    "no viewport": "no_viewport",
    "mobile-responsive": "no_viewport",
    "missing viewport": "no_viewport",
    "broken link": "broken_links",
    "broken links": "broken_links",
    "slow page": "slow_page",
    "slow load": "slow_page",
    "html error": "html_errors",
    "html errors": "html_errors",
    "markup error": "html_errors",
    "missing h1": "no_h1",
    "multiple h1": "multiple_h1",
    "missing alt": "missing_alt_text",
    "alt text": "missing_alt_text",
    "missing security": "no_security_headers",
    "no hsts": "no_security_headers",
    "no csp": "no_security_headers",
    "no robots": "no_robots_txt",
    "no sitemap": "no_sitemap",
    "structured data": "no_structured_data",
    "schema.org": "no_structured_data",
    "open graph": "no_og_tags",
    "missing og": "no_og_tags",
    "canonical": "no_canonical",
    "privacy policy": "no_privacy_policy",
    "cookie consent": "no_cookie_consent",
    "social link": "no_social_links",
    "noindex": "no_robots_txt",
    "thin content": "html_errors",
}

def infer_defect_key(defect_text):
    """Map a defect description string to a defect_key."""
    text = defect_text.lower()
    for keyword, key in DEFECT_TEXT_TO_KEY.items():
        if keyword in text:
            return key
    return "unknown"

PRIORITY_WEIGHTS = {
    "ssl_expired": 1, "http_error": 1, "ssl_expiring_soon": 2,
    "no_viewport": 2, "missing_title": 3, "missing_meta_description": 3,
    "no_contact_form": 3, "broken_links": 4, "slow_page": 4,
    "html_errors": 5, "no_h1": 5, "multiple_h1": 6,
    "missing_alt_text": 6, "no_security_headers": 7,
    "no_robots_txt": 8, "no_sitemap": 8, "no_structured_data": 9,
    "no_og_tags": 9, "no_canonical": 9, "no_privacy_policy": 10,
    "no_cookie_consent": 10, "no_social_links": 11, "stale_copyright": 12,
}

def load_audit(path):
    path_str = str(path)
    if path_str.endswith(".json"):
        return json.loads(Path(path_str).read_text())
    return None

def get_priority(defect_key):
    return PRIORITY_WEIGHTS.get(defect_key, 99)

def generate_remediation(audit_data):
    """Generate a prioritized remediation plan using stable finding IDs when available."""
    domain = audit_data.get("domain", "unknown")
    score = audit_data.get("score", 0)
    findings = audit_data.get("findings")
    legacy_defects = audit_data.get("defects", [])

    source = findings if isinstance(findings, list) and findings else legacy_defects
    actions = []
    for item in source:
        if not isinstance(item, dict):
            continue
        check_id = item.get("check_id")
        message = item.get("message") or item.get("defect", "")
        key = CHECK_ID_TO_FIX_KEY.get(check_id or "")
        if not key:
            key = item.get("defect_key", "") or infer_defect_key(message)
        fix = FIX_LIBRARY.get(key, {
            "title": message or "Unknown issue",
            "effort": "TBD",
            "cost": "TBD",
            "code": None,
            "docs": None,
            "steps": ["Investigate manually"],
        })
        state = item.get("remediation")
        if not isinstance(state, dict):
            state = initial_remediation(
                verification_command=f"python website_auditor.py https://{domain} --format json"
            )
        actions.append({
            "check_id": check_id or "legacy.unclassified",
            "defect_key": key,
            "defect": message,
            "impact": item.get("business_impact") or item.get("impact", ""),
            "category": item.get("category", "technical_health"),
            "severity": item.get("severity", "low"),
            "confidence": item.get("confidence"),
            "human_review": bool(item.get("human_review", False)),
            "priority_label": item.get("priority"),
            "priority": get_priority(key),
            "remediation": state,
            "fix": fix,
        })

    actions.sort(key=lambda action: (action["priority"], action["check_id"]))

    return {
        "schema_version": 2,
        "domain": domain,
        "score": score,
        "score_semantics": audit_data.get("score_semantics", {}),
        "category_scores": audit_data.get("category_scores", {}),
        "taxonomy": audit_data.get("taxonomy", {}),
        "total_defects": len(actions),
        "generated": datetime.now().isoformat(),
        "actions": actions,
        "summary": {
            "high": sum(1 for action in actions if action["priority"] <= 3),
            "medium": sum(1 for action in actions if 4 <= action["priority"] <= 7),
            "low": sum(1 for action in actions if action["priority"] >= 8),
            "needs_human_review": sum(1 for action in actions if action["human_review"]),
        },
    }

def generate_html_patch(audit_data, remediation):
    """Generate an HTML patch file with suggested fixes applied."""
    domain = audit_data.get("domain", "")
    body = audit_data.get("evidence", {}).get("html", "")

    patches = []
    for action in remediation["actions"]:
        fix = action["fix"]
        code = fix.get("code")
        if code:
            patches.append({
                "defect": action["defect"],
                "patch": code,
                "effort": fix.get("effort", "?"),
            })

    return {
        "domain": domain,
        "patches": patches,
        "generated": datetime.now().isoformat(),
    }

def run_single(audit_path, output_dir=None):
    """Process a single audit file."""
    data = load_audit(audit_path)
    if not data:
        print(f"  ❌ Cannot read: {audit_path}")
        return None

    remediation = generate_remediation(data)

    print(f"\n  🔧 {data['domain']} (score: {data['score']}/100)")
    print(f"     {remediation['summary']['high']} high, {remediation['summary']['medium']} medium, {remediation['summary']['low']} low priority")

    for i, action in enumerate(remediation["actions"][:5], 1):
        fix = action["fix"]
        print(f"     {i}. [{action['priority']}] {action['defect']}")
        print(f"        Fix: {fix['title']} ({fix['effort']}, {fix['cost']})")
        if fix.get("code"):
            print(f"        Code: {fix['code'][:80]}...")

    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[^\w.-]', '_', data['domain'])
        out_file = out_dir / f"{safe}-remediation.json"
        out_file.write_text(json.dumps(remediation, indent=2, default=str))
        print(f"     💾 Saved: {out_file}")

    return remediation

def run_batch(audits_dir, output_dir=None):
    """Process all audit files in a directory."""
    audits_path = Path(audits_dir)
    results = []
    count = 0
    for aj in sorted(audits_path.glob("*.json")):
        result = run_single(aj, output_dir)
        if result:
            results.append(result)
            count += 1
    print(f"\n  ✅ Batch complete: {count} sites remediated")
    if output_dir:
        summary_file = Path(output_dir) / "remediation-summary.json"
        summary = {
            "generated": datetime.now().isoformat(),
            "total_sites": len(results),
            "sites": [{"domain": r["domain"], "score": r["score"], "actions": len(r["actions"])} for r in results],
        }
        summary_file.write_text(json.dumps(summary, indent=2))
        print(f"     Summary: {summary_file}")
    return results

def main():
    parser = argparse.ArgumentParser(description="Remediation Engine — auto-fix suggestions from audits")
    parser.add_argument("audit", nargs="?", help="Single audit JSON file")
    parser.add_argument("--batch", metavar="DIR", default="audits", help="Batch directory (default: audits/)")
    parser.add_argument("--all", action="store_true", help="Process all audits")
    parser.add_argument("--output-dir", "-o", default="outputs/remediations", help="Output directory")
    parser.add_argument("--html-patches", action="store_true", help="Generate HTML patch files")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.audit:
        run_single(args.audit, output_dir)
    elif args.all or not args.audit:
        run_batch(args.batch, output_dir)

if __name__ == "__main__":
    main()