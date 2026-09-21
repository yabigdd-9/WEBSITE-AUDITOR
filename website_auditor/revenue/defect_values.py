
"""
Defect-to-Revenue mappings based on published industry data.
Sources: Google PageSpeed Insights studies, Deloitte Digital 2023,
NZ Commerce Commission e-commerce benchmarks, Baymard Institute.

Formula:
  Revenue at Risk = Monthly Visitors x Conversion Rate x Avg Lead Value x Impact Factor
"""

# Default business assumptions (configurable per client)
DEFAULTS = {
    "monthly_visitors": 2000,
    "conversion_rate": 0.025,       # 2.5% NZ small business average
    "avg_lead_value_nzd": 150,      # NZD per qualified lead
    "bounce_rate_baseline": 0.45,   # 45% baseline bounce
    "avg_order_value_nzd": 85,      # For e-commerce sites
}

# Impact factors: what % of conversions/revenue each defect type destroys
# Format: defect_keyword -> (impact_factor, confidence, source_note)
DEFECT_REVENUE_MAP = {
    # === CRITICAL: Trust & Security (highest revenue impact) ===
    "ssl expired": (0.35, "high", "Google Chrome shows full-page warning. 85% of users leave immediately. Source: GlobalSign 2023"),
    "ssl expir": (0.25, "high", "Browser warning within days. Trust collapse. Source: Sectigo Consumer Survey"),
    "ssl invalid": (0.35, "high", "Same as expired. Full browser warning."),
    "mixed content": (0.15, "medium", "Browser shows 'Not Secure' padlock. 12-18% trust reduction. Source: HTTPArchive"),
    "missing hsts": (0.05, "low", "No visible impact to users, but fails security audits. Indirect trust."),
    "missing x-frame": (0.02, "low", "Clickjacking risk. No direct revenue impact but compliance gap."),
    "missing csp": (0.03, "low", "XSS risk. No direct revenue impact but compliance gap."),
    "missing referrer-policy": (0.02, "low", "Data leakage risk. Minimal direct revenue impact."),
    "missing permissions-policy": (0.02, "low", "Feature policy gap. Minimal direct revenue impact."),
    "missing x-content-type": (0.02, "low", "MIME sniffing risk. Minimal direct revenue impact."),

    # === HIGH: Conversion Path Blockers ===
    "no contact form": (0.22, "high", "Primary conversion path missing. 20-25% of ready-to-buy visitors cannot contact you. Source: Baymard Institute"),
    "broken contact": (0.20, "high", "Contact form exists but broken. Same as missing for revenue."),
    "broken link": (0.04, "medium", "Each broken link = 2-4% bounce increase. Compounds across site. Source: SEMrush"),
    "404 error": (0.06, "medium", "Dead pages waste ad spend and SEO equity. Source: Ahrefs study"),
    "missing phone": (0.12, "high", "NZ trades: 40% of customers prefer phone. Missing click-to-call loses leads. Source: NZ Commerce Commission"),
    "missing email link": (0.08, "medium", "Secondary contact path missing. 8-12% of converters prefer email."),

    # === HIGH: Performance (Google-validated data) ===
    "slow page": (0.18, "high", "LCP > 4s = 18% mobile conversion drop. Source: Google/Deloitte 2023 'Milliseconds Make Millions'"),
    "page load speed": (0.15, "high", "Every 1s delay = 7% conversion reduction. Source: Akamai/Google"),
    "large image": (0.08, "medium", "Oversized images delay LCP. 5-10% mobile bounce increase."),
    "no lazy loading": (0.05, "medium", "All resources load upfront. Delays interactive time."),
    "render-blocking": (0.10, "medium", "CSS/JS blocking first paint. 8-12% mobile bounce. Source: web.dev"),
    "no compression": (0.06, "medium", "Uncompressed responses = 2-3x load time. Source: HTTPArchive"),
    "no caching": (0.07, "medium", "No cache headers = repeat visitors re-download everything."),

    # === MEDIUM: SEO / Visibility (traffic loss = revenue loss) ===
    "missing page title": (0.12, "high", "Title tag is #1 on-page SEO factor. Missing = invisible in search. Source: Moz/BrightEdge"),
    "missing meta description": (0.06, "high", "2-5% CTR reduction from search results. Source: Backlinko 2024"),
    "missing h1": (0.08, "high", "H1 is primary relevance signal. Missing = lower rankings. Source: Search Engine Journal"),
    "missing canonical": (0.04, "medium", "Duplicate content dilution. 3-5% ranking impact."),
    "missing sitemap": (0.05, "medium", "Crawl efficiency loss. Pages may not get indexed."),
    "robots.txt": (0.03, "medium", "Crawl directives missing. Minor indexing impact."),
    "missing schema": (0.07, "medium", "No rich snippets in search. 5-15% CTR loss. Source: Search Engine Land"),
    "missing structured data": (0.07, "medium", "Same as missing schema."),
    "missing og": (0.04, "medium", "No Open Graph = ugly social shares. 10-20% social CTR loss."),
    "missing twitter card": (0.03, "medium", "No Twitter/X card markup. Minor social impact."),
    "duplicate title": (0.05, "medium", "Duplicate titles confuse search engines. Ranking dilution."),
    "thin content": (0.08, "medium", "Under 300 words = Google deprioritises. Source: Backlinko"),

    # === MEDIUM: Mobile Experience ===
    "missing viewport": (0.20, "high", "Site not responsive on mobile. 55% of NZ traffic is mobile. Source: Stats NZ"),
    "mobile viewport": (0.20, "high", "Same as above."),
    "not responsive": (0.20, "high", "Desktop-only layout on mobile. Massive bounce."),
    "small tap target": (0.05, "medium", "Buttons too small to tap. 3-5% mobile conversion loss."),
    "text too small": (0.04, "medium", "Unreadable on mobile. 3-4% bounce increase."),

    # === MEDIUM: Accessibility (legal + market expansion) ===
    "missing alt text": (0.03, "medium", "Screen readers can't describe images. 1.1M NZers have disability. Source: Stats NZ"),
    "image alt": (0.03, "medium", "Same as above."),
    "missing lang": (0.02, "low", "Screen readers can't determine language."),
    "low contrast": (0.03, "medium", "Text unreadable for visually impaired. WCAG 2.2 AA fail."),
    "keyboard trap": (0.04, "medium", "Keyboard users cannot navigate. Accessibility fail."),
    "missing form label": (0.04, "medium", "Screen readers can't identify form fields."),

    # === LOW: Trust & Compliance ===
    "copyright year": (0.02, "low", "Outdated copyright = 'abandoned site' signal. Minor trust."),
    "missing privacy policy": (0.08, "high", "NZ Privacy Act 2020 requirement. Legal risk + trust. Source: OA NZ"),
    "privacy policy": (0.08, "high", "Same as above."),
    "missing cookie consent": (0.06, "medium", "NZ Privacy Act + GDPR if EU visitors. Compliance risk."),
    "cookie consent": (0.06, "medium", "Same as above."),
    "gdpr": (0.06, "medium", "GDPR signal missing. Risk if EU visitors."),
    "missing terms": (0.04, "medium", "No Terms of Service. Legal exposure for e-commerce."),

    # === LOW: Social & Content ===
    "missing social": (0.03, "low", "No social media links. Minor trust signal loss."),
    "social media": (0.03, "low", "Same as above."),
    "html validation": (0.02, "low", "Markup errors reduce crawl efficiency. Minor SEO."),
    "html error": (0.02, "low", "Same as above."),
    "html markup": (0.02, "low", "Same as above."),
}

def get_defect_value(defect_text):
    """Match a defect description to its revenue impact."""
    text = str(defect_text).lower()
    for keyword, (impact, confidence, source) in DEFECT_REVENUE_MAP.items():
        if keyword in text:
            return impact, confidence, source
    # Unknown defect: assign minimal default impact
    return 0.01, "low", "Unclassified defect. Minimal estimated impact."
