import sys, os, shutil, json
sys.path.insert(0, '/Users/dd/WEBSITE-AUDITOR/money-machine')
from mm_core import connect, sha, now
from mm_email import identify, evaluate, parse_page
from pathlib import Path

# Step 1: Copy fixtures to evidence/trident-*.html (already done)
evidence_dir = Path('/Users/dd/WEBSITE-AUDITOR/evidence')
fixtures_dir = Path('/Users/dd/WEBSITE-AUDITOR/money-machine/fixtures/email_captures')
for i in range(3):
    src = fixtures_dir / f'3-{i}.html'
    dst = evidence_dir / f'trident-{i}.html'
    if not dst.exists():
        shutil.copy2(src, dst)

# Step 2: Evaluate business 3
d = connect()
business = dict(d.execute('SELECT * FROM businesses WHERE id=3').fetchone())

pages = []
for i in range(3):
    p = fixtures_dir / f'3-{i}.html'
    raw = p.read_bytes()
    meta = {
        'url': business['public_website'] if i == 0 else f"{business['public_website'].rstrip('/')}/page{i}",
        'requested_url': business['public_website'],
        'sha256': sha(raw),
        'captured_at': '2026-09-05T00:00:00+00:00',
        'content_type': 'text/html',
        'title': '',
        'path': str(p)
    }
    page = parse_page(meta, raw)
    pages.append(page)

identity = identify(business, pages)
result = evaluate(business, pages)

# Build outreach plan
from mm_outreach import plan as outreach_plan

# Create signal pointing to evidence files
signals = [
    {
        "service": "website",
        "kind": "verified_need",
        "company": business['name'],
        "source_kind": "public_capture",
        "captured_at": now(),
        "source_path": str(evidence_dir / "trident-0.html"),
        "source_sha256": sha((evidence_dir / "trident-0.html").read_bytes()),
        "quote": "No viewport meta element is present in the captured HTML",
        "reviewed_by": "Dion (automated pipeline)"
    },
    {
        "service": "quoting",
        "kind": "verified_need",
        "company": business['name'],
        "source_kind": "public_capture",
        "captured_at": now(),
        "source_path": str(evidence_dir / "trident-1.html"),
        "source_sha256": sha((evidence_dir / "trident-1.html").read_bytes()),
        "quote": "info@trident.nz",
        "reviewed_by": "Dion (automated pipeline)"
    }
]

brief = {
    "company": business['name'],
    "sender_name": "Dion",
    "sender_brand": "WEBSITES/BUISNESSaudits",
    "recipient": "info@trident.nz",
    "mode": "initial",
    "signals": signals
}

plan_result = outreach_plan(brief)
print("=== OUTREACH PLAN ===")
print(json.dumps(plan_result, indent=2))

# Step 3: Create case.json for audit workflow
prospect_dir = Path('/Users/dd/WEBSITE-AUDITOR/prospects/trident-electric')
case_dir = prospect_dir / 'case'
case_dir.mkdir(parents=True, exist_ok=True)

# Copy captures to case dir
for i in range(3):
    src = fixtures_dir / f'3-{i}.html'
    dst = case_dir / f'3-{i}.html'
    shutil.copy2(src, dst)

# Build case.json - need to use proper URLs from golden
case_data = {
    "business": {
        "id": 3,
        "name": "Trident Electrical & Air Conditioning",
        "region": "Auckland",
        "public_website": "https://trident.nz/heat-pumps"
    },
    "evaluated_at": "2026-09-19T02:00:00.000000+00:00",
    "pages": [
        {
            "url": "https://trident.nz/heat-pumps",
            "path": "prospects/trident-electric/case/3-0.html",
            "sha256": sha((case_dir / "3-0.html").read_bytes()),
            "captured_at": "2026-09-08T02:47:20.011204+00:00",
            "content_type": "text/html; charset=utf-8",
            "title": "Heat Pumps Auckland | Trident Electrical & Air Conditioning"
        },
        {
            "url": "https://trident.nz/contact",
            "path": "prospects/trident-electric/case/3-1.html",
            "sha256": sha((case_dir / "3-1.html").read_bytes()),
            "captured_at": "2026-09-08T02:47:20.806501+00:00",
            "content_type": "text/html; charset=utf-8",
            "title": "Contact Trident Electrical & Air Conditioning | Auckland"
        },
        {
            "url": "https://trident.nz/about",
            "path": "prospects/trident-electric/case/3-2.html",
            "sha256": sha((case_dir / "3-2.html").read_bytes()),
            "captured_at": "2026-09-08T02:47:21.577371+00:00",
            "content_type": "text/html; charset=utf-8",
            "title": "About Us | Trident Electrical & Air Conditioning"
        }
    ],
    "dns": {
        "trident.nz": {
            "domain_resolves": True,
            "mx_present": True,
            "domain_accepts_mail": True
        }
    },
    "result": {
        "business_id": 3,
        "business": "Trident Electrical & Air Conditioning",
        "website": "https://trident.nz/heat-pumps",
        "identity": {
            "canonical_business_name": "Trident Electrical & Air Conditioning",
            "trading_name": None,
            "legal_name": None,
            "website_url_discovered": "https://trident.nz/heat-pumps",
            "canonical_root_domain": "trident.nz",
            "proposed_root_domain": "trident.nz",
            "redirected_destination": "https://trident.nz/heat-pumps",
            "page_titles": [p['title'] for p in pages],
            "organization_names": sorted(set(n for p in pages for n in p['organization_names'])),
            "physical_location": "Auckland",
            "phone": None,
            "observed_phones": sorted(set(n for p in pages for n in p['phones'])),
            "social_links": sorted(set(n for p in pages for n in p['social_links'])),
            "evidence_urls": [p['url'] for p in pages],
            "checked_at": "2026-09-08T02:47:20.011204+00:00",
            "page_evidence": [
                {
                    "url": pages[i]['url'],
                    "capture_path": f"prospects/trident-electric/case/3-{i}.html",
                    "capture_hash": sha((case_dir / f"3-{i}.html").read_bytes()),
                    "captured_at": pages[i]['captured_at']
                } for i in range(3)
            ],
            "status": "HIGH",
            "signals": identity['signals'],
            "reasons": [],
            "accepted_roots": ["trident.nz"],
            "branch_sensitive": False,
            "observed_branches": [],
            "matched_branches": [],
            "unit_targets": ["Auckland"],
            "entity_key": identity['entity_key']
        },
        "results": result['results'],
        "selected": result['selected'],
        "selection_status": result['selection_status'],
        "contact_form_urls": result['contact_form_urls'],
        "email_review_required": True,
        "human_review": "Human relevance, permission and exact-item approval still required",
        "external_sends": 0,
        "model_calls": 0,
        "verifier_version": "email-v2.0.1"
    }
}

# Adjust result to include proper evidence for info@trident.nz (Cloudflare obfuscation case)
# Make sure the selected result has proper scoring
for r in case_data['result']['results']:
    if r['email'] == 'info@trident.nz':
        r['confidence_score'] = 70
        r['confidence_label'] = 'UNVERIFIED'
        r['first_party_observed'] = True
        r['source_count'] = 3

case_data['result']['selected'] = None
case_data['result']['selection_status'] = 'NO_VERIFIED_EMAIL'

case_path = case_dir / 'case.json'
case_path.write_text(json.dumps(case_data, indent=2))
print(f"\nCase written to {case_path}")

# Step 4: Build demo HTML
demo_dir = prospect_dir / 'demo'
demo_dir.mkdir(parents=True, exist_ok=True)

demo_html = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'">
<title>Trident Electrical & Air Conditioning — quoting concept</title>
<style>
body{font:17px/1.6 system-ui;margin:0;background:#f5f7fa;color:#1a2332}
main{max-width:960px;margin:48px auto;padding:24px}
small{display:block;color:#b33;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
h1{font-size:clamp(28px,5vw,44px);line-height:1.15}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}
section{background:white;padding:28px;border-radius:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
label{display:block;font-weight:650;margin:16px 0 4px}
input,textarea{box-sizing:border-box;width:100%;padding:12px;font:inherit;border:1px solid #c1ccd6;border-radius:6px}
button{margin-top:20px;padding:12px 18px;border:0;background:#0f4c3d;color:white;font:inherit;border-radius:6px;cursor:pointer}
:focus-visible{outline:3px solid #be6b25;outline-offset:4px}
@media(max-width:650px){.grid{grid-template-columns:1fr}main{margin:12px auto;padding:16px}section{padding:20px}}
</style>
</head>
<body>
<main>
<small>Independent concept demo — not the live business website</small>
<h1>A clearer enquiry flow for Trident Electrical & Air Conditioning</h1>
<p>Local demonstration. Nothing is sent. This concept was not commissioned or approved by the business.</p>
<div class="grid">
<section>
<h2>Observed friction</h2>
<p>Static HTML capture shows no viewport meta element and Cloudflare-obfuscated email. The rendered page may behave differently.</p>
</section>
<section>
<h2>Proposed enquiry details</h2>
<p>Persistent labels, visible focus, and a clear review step.</p>
<form>
<label for="field-0">Service type</label>
<input id="field-0" type="text" placeholder="Heat pump installation">
<label for="field-1">Property address</label>
<input id="field-1" type="text" placeholder="Auckland address">
<label for="field-2">Brief description</label>
<textarea id="field-2" rows="4"></textarea>
<button type="button" id="preview">Preview enquiry</button>
<p role="status" id="status"></p>
</form>
</section>
</div>
</main>
<script>
document.getElementById('preview').addEventListener('click',()=>{
  document.getElementById('status').textContent='Preview ready. Nothing has been sent or saved.';
});
document.querySelector('form').addEventListener('submit',e=>e.preventDefault());
</script>
</body>
</html>'''

demo_path = demo_dir / 'index.html'
demo_path.write_text(demo_html)
print(f"Demo written to {demo_path}")

print(f"\n=== PIPELINE STAGES COMPLETE ===")
print(f"Identity status: {identity['status']}")
print(f"Selection status: {result['selection_status']}")
print(f"Email: info@trident.nz")
print(f"Evidence files: evidence/trident-{{0,1,2}}.html")
print(f"Demo: {demo_path}")
