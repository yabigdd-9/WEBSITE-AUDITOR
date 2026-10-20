
"""
Tech Fingerprinting: Detects CMS, Page Builders, Caching, and CDNs.
"""
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
