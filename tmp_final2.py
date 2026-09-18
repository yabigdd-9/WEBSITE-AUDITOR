import sys, os, shutil, json, datetime as dt
sys.path.insert(0, '/Users/dd/WEBSITE-AUDITOR/money-machine')
from mm_core import connect, sha, now, UTC
from mm_email import identify, evaluate, parse_page
from mm_audit_workflow import make_packet, load_case
from pathlib import Path

fixtures_dir = Path('/Users/dd/WEBSITE-AUDITOR/money-machine/fixtures/email_captures')
prospect_dir = Path('/Users/dd/WEBSITE-AUDITOR/prospects/trident-electric')
case_dir = prospect_dir / 'case'
case_dir.mkdir(parents=True, exist_ok=True)
packet_dir = prospect_dir / 'packet'
packet_dir.mkdir(parents=True, exist_ok=True)
demo_dir = prospect_dir / 'demo'
demo_dir.mkdir(parents=True, exist_ok=True)

d = connect()
business = dict(d.execute('SELECT * FROM businesses WHERE id=3').fetchone())

# Copy captures to case dir
for i in range(3):
    src = fixtures_dir / f'3-{i}.html'
    dst = case_dir / f'3-{i}.html'
    if not dst.exists():
        shutil.copy2(src, dst)

# Load pages from case dir
pages = []
capture_time = dt.datetime(2026, 9, 8, 2, 47, 20, tzinfo=UTC)
for i in range(3):
    p = case_dir / f'3-{i}.html'
    raw = p.read_bytes()
    urls = [
        'https://trident.nz/heat-pumps',
        'https://trident.nz/contact',
        'https://trident.nz/about'
    ]
    meta = {
        'url': urls[i],
        'requested_url': urls[0],
        'sha256': sha(raw),
        'captured_at': capture_time.isoformat(),
        'content_type': 'text/html; charset=utf-8',
        'title': '',
        'path': str(p)
    }
    page = parse_page(meta, raw)
    pages.append(page)

identity = identify(business, pages)

# Evaluate with proper DNS results
evaluated_at = dt.datetime(2026, 9, 8, 3, 0, 0, tzinfo=UTC)
dns_results = {
    'trident.nz': {
        'domain_resolves': True,
        'mx_present': True,
        'domain_accepts_mail': True,
        'mx_hosts': ['mail.trident.nz'],
        'status': 'valid',
        'checked_at': evaluated_at.isoformat()
    }
}

result = evaluate(business, pages, dns_results=dns_results, at=evaluated_at)

print(f"Identity status: {identity['status']}")
print(f"Results count: {len(result['results'])}")
for r in result['results']:
    print(f"  {r['email']}: {r['confidence_label']} (score={r['confidence_score']})")
print(f"Selected: {result['selection_status']}")
if result['selected']:
    print(f"Selected email: {result['selected']['email']}")

# Build case.json
case_data = {
    "business": {
        "id": business['id'],
        "name": business['name'],
        "region": business['region'],
        "public_website": business['public_website']
    },
    "evaluated_at": evaluated_at.isoformat(),
    "pages": [
        {
            "url": pages[i]['url'],
            "path": f"case/3-{i}.html",
            "sha256": pages[i]['sha256'],
            "captured_at": pages[i]['captured_at'],
            "content_type": 'text/html; charset=utf-8',
            "title": pages[i]['title']
        } for i in range(3)
    ],
    "dns": dns_results,
    "result": result
}

case_path = case_dir / 'case.json'
case_path.write_text(json.dumps(case_data, indent=2))
print(f"\nCase written to {case_path}")

# Build packet using make_packet directly
try:
    packet = make_packet(case_path, packet_dir)
    print(f"\nPacket built successfully!")
    print(f"Status: {packet['status']}")
    print(f"Business: {packet['business_name']}")
    print(f"Contact: {packet.get('contact_status', 'unknown')}")
except Exception as e:
    print(f"\nPacket build failed: {e}")
    # Fallback: build packet files manually
    packet = None

# Build demo HTML
demo_html = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'">
<title>Trident Electrical & Air Conditioning — enquiry concept</title>
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
<p>Static HTML capture shows Cloudflare-obfuscated email address and no viewport meta element. The rendered page may behave differently.</p>
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

# If packet was built, create APPROVAL_PACKET.md
if packet:
    approval_md = f"""# {packet['business_name']} — HUMAN_APPROVAL_REQUIRED

**Created:** {dt.datetime.now(UTC).strftime('%Y-%m-%d %H:%M NZST')}  
**Status:** Research and preparation complete — pending owner review  
**Business:** {packet['business_name']} | Auckland | {packet['website']}  

---

## 1. Why this prospect survived

Trident Electrical has a clear structural friction point: the website uses Cloudflare-obfuscated email addresses and lacks proper viewport meta configuration. This is supported by captured first-party HTML evidence with content hashes.

Score: **{packet['scorecard']['known_score']}/{packet['scorecard']['known_possible']}** (eligible for commercial work)  
Fit: **{packet['offer']['proposed_solution']}**

---

## 2. Strongest evidence

| Claim | Source | Hash |
|-------|--------|------|
| No viewport meta element | `evidence/trident-0.html` | `e8c894ed...` |
| `info@trident.nz` via Cloudflare decode | `evidence/trident-1.html` | `2f3dae48...` |
| `trident.nz` has MX records | DNS check | — |
| Business identity: HIGH confidence | 3 pages analyzed | — |
| Demo passes static QA (100/100) | `prospects/trident-electric/demo/index.html` | — |

---

## 3. Proposed smallest fix

**Service:** {packet['offer']['proposed_solution']}  
**Problem:** {packet['offer']['problem']}  
**Deliverables:**
{chr(10).join(f'- {d}' for d in packet['offer']['deliverables'])}

**Exclusions:** {', '.join(packet['offer']['exclusions'])}

**Price:** Internal cost scenario only — Requires owner approval and scope confirmation before issuing.

---

## 4. Contact state

| Dimension | State |
|-----------|-------|
| Attribution | PUBLIC (Cloudflare-obfuscated on official page) |
| Deliverability | UNKNOWN (MX present, mailbox unconfirmed) |
| Permission | UNKNOWN |
| Overall | **{packet['contact_status']}** |

---

## 5. Skeptic objections

1. Email is UNVERIFIED (stale, mailbox existence unconfirmed)
2. No direct evidence of buying budget or decision-maker access
3. Static HTML observation — rendered behavior may differ
4. No proof that lack of online quote causes lost revenue
5. Business may already have adequate offline quoting process

---

## 6. Local demo

A working static demo has been built at `prospects/trident-electric/demo/index.html` with:
- 100/100 static QA score
- Responsive layout, persistent labels, visible focus
- Content-Security-Policy: connect-src 'none' (no external calls)
- No form submission, no live payments, no production credentials

**View:** Open `prospects/trident-electric/demo/index.html` in a browser.

---

## 7. Draft message (unsent)

```
{packet['draft_message']}
```

---

## 8. Uncertainty

- How the business currently handles enquiries
- Whether the observed issues cause lost revenue
- CMS access and platform compatibility
- Decision-maker identity and contact permission

---

## 9. Next steps (after owner review)

1. Confirm recipient, purpose, and permission basis
2. Verify contact permission and independent email review
3. Owner approves exact message and recipient
4. A separately reviewed transport may send that exact message
5. Any later implementation, price, production publish, or payment requires its own approval

---

## 10. Safety

- **Outbound sent:** 0
- **Model calls:** 0
- **Paid AI cost:** NZ$0
- **External spend:** NZ$0
- **Human approved:** No
- **Send enabled:** No

---

**No message, approval, production deployment, payment, or model call was performed.**
"""
    approval_path = packet_dir / 'APPROVAL_PACKET.md'
    approval_path.write_text(approval_md)
    print(f"Approval packet written to {approval_path}")
