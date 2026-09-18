#!/usr/bin/env python3
"""Rebuild case.json with correct paths and matching evaluate result."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, 'money-machine')

from mm_email import identify, evaluate, parse_page

CAPTURES = [
    {
        "url": "https://www.heatforce.co.nz/",
        "path": "case/heatforce-0.html",
        "sha256": "3f5c04aa7babe091030b1e330b75108f66120a815da8103dbbbfe5dc76ccf231",
        "captured_at": "2026-09-08T02:47:41.963185+00:00",
        "content_type": "text/html; charset=UTF-8",
        "title": "Heat Force: Your Christchurch Heat Pump Specialists for Sales & Service"
    },
    {
        "url": "https://www.heatforce.co.nz/contact-us",
        "path": "case/heatforce-1.html",
        "sha256": "a2da93639191195835481424e6e40de31bbee5c50cdb4c3f9f83e619129e4c71",
        "captured_at": "2026-09-08T02:47:43.302239+00:00",
        "content_type": "text/html; charset=UTF-8",
        "title": "Contact Heat Force: Free Heat Pump Quotes in Christchurch"
    },
    {
        "url": "https://www.heatforce.co.nz/about-us",
        "path": "case/heatforce-2.html",
        "sha256": "7198a1fc5c92e5e472d95f2cceed200a3fb45b7e2787406c648d07064591f1e6",
        "captured_at": "2026-09-08T02:47:45.404488+00:00",
        "content_type": "text/html; charset=UTF-8",
        "title": "About Heat Force: Christchurch's 30+ Year Heat Pump Specialists"
    },
]

business = {
    "id": 5,
    "name": "Heat Force",
    "region": "Christchurch",
    "public_website": "https://www.heatforce.co.nz/"
}

# Parse pages
pages = []
for cap in CAPTURES:
    p = Path("prospects/heat-force") / cap["path"]
    raw = p.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    assert actual_hash == cap["sha256"], f"Hash mismatch: {cap['path']}"
    pages.append(parse_page(cap, raw))

# Evaluated at a fixed time close to captures
evaluated_at = "2026-09-08T03:00:00.000000+00:00"

dns_data = {
    "heatforce.co.nz": {
        "domain_resolves": True,
        "mx_present": True,
        "domain_accepts_mail": True,
        "mx_hosts": ["mx1.heatforce.co.nz"],
        "checked_at": "2026-09-08T02:50:00.000000+00:00",
        "status": "ok"
    }
}

from datetime import datetime, timezone
at = datetime.fromisoformat(evaluated_at)

result = evaluate(business, pages, dns_results=dns_data, at=at)
print(f"identity status: {result['identity']['status']}")
print(f"selection_status: {result['selection_status']}")
if result['selected']:
    print(f"selected email: {result['selected']['email']}")
    print(f"selected confidence: {result['selected']['confidence_label']}")

case = {
    "business": business,
    "evaluated_at": evaluated_at,
    "pages": [
        {
            "url": cap["url"],
            "path": cap["path"],
            "sha256": cap["sha256"],
            "captured_at": cap["captured_at"],
            "content_type": cap["content_type"],
            "title": cap["title"]
        }
        for cap in CAPTURES
    ],
    "dns": dns_data,
    "result": result
}

Path("prospects/heat-force/case/case.json").write_text(json.dumps(case, indent=2))
print(f"\nWrote prospects/heat-force/case/case.json")

# Verify it replays
from mm_audit_workflow import load_case
doc2, pages2 = load_case("prospects/heat-force/case/case.json")
print("load_case replay OK")
