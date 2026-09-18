#!/usr/bin/env python3
"""Test Hunter.io enrichment against real businesses."""
import sys, os
sys.path.insert(0, 'money-machine')
os.environ['HUNTER_API_KEY'] = '02959de4dd9c1c1c6f8d8b6c9de999efdf80c5ee'
import mm_core as c
import hunter_enrichment as hunter
from mm_email import root_domain

d = c.connect(readonly=True)

businesses = [dict(r) for r in d.execute('SELECT id, name, public_website FROM businesses WHERE public_website IS NOT NULL AND public_website != "" AND is_dummy = 0 ORDER BY id LIMIT 3').fetchall()]

for biz in businesses:
    print("Business: %s (id=%d)" % (biz['name'], biz['id']))
    print("  Website: %s" % biz['public_website'])
    domain = root_domain(biz['public_website'])
    print("  Root domain: %s" % domain)

    result = hunter.enrich_business(d, biz['id'], domain, limit=5)
    print("  Candidates: %d" % len(result.get('candidates', [])))
    print("  Total found: %d" % result.get('total', 0))
    for cand in result.get('candidates', [])[:3]:
        print("    - %s (conf=%d) status=%s" % (cand['email'], cand.get('hunter_confidence', 0), cand['status']))
    print()
