import sys, os, shutil, json
sys.path.insert(0, '/Users/dd/WEBSITE-AUDITOR/money-machine')
from mm_core import connect, sha, now
from mm_email import identify, evaluate, parse_page
from pathlib import Path

# Step 1: Copy fixtures to evidence/trident-*.html
evidence_dir = Path('/Users/dd/WEBSITE-AUDITOR/evidence')
fixtures_dir = Path('/Users/dd/WEBSITE-AUDITOR/money-machine/fixtures/email_captures')

for i in range(3):
    src = fixtures_dir / f'3-{i}.html'
    dst = evidence_dir / f'trident-{i}.html'
    shutil.copy2(src, dst)
    print(f"Copied {src.name} -> {dst.name} ({dst.stat().st_size} bytes)")

# Step 2: Evaluate business 3 using existing captures
d = connect()
business = dict(d.execute('SELECT * FROM businesses WHERE id=3').fetchone())
print(f"\nBusiness: {business['name']}")
print(f"Website: {business['public_website']}")

# Load pages from fixtures
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
    print(f"\nPage {i}: {len(page['observations'])} observations, title='{page['title'][:60]}'")

# Identify
identity = identify(business, pages)
print(f"\nIdentity status: {identity['status']}")
print(f"Canonical root domain: {identity['canonical_root_domain']}")
print(f"Reasons: {identity['reasons']}")

# Evaluate
result = evaluate(business, pages)
print(f"\nSelection status: {result['selection_status']}")
if result['selected']:
    print(f"Selected email: {result['selected']['email']}")
    print(f"Confidence: {result['selected']['confidence_label']} ({result['selected']['confidence_score']})")
else:
    print("No email selected - showing all results:")
    for r in result['results']:
        print(f"  {r['email']}: {r['confidence_label']} ({r['confidence_score']}) - {r['rejection_reasons']}")
