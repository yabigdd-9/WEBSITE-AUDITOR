"""Operator email commands; single-business discovery or reproducible shadow replay."""
import datetime as dt
import json
from pathlib import Path

import mm_core as c
import mm_email as e
import mm_email_store as store
from mm_email_network import Crawler, DNSChecks


def find_one(d, bid):
    business = dict(c.business(d, bid))
    if not store.installed(d): raise ValueError('Run email-migrate with a verified backup first')
    store.require_production_persistence(d)
    # Research may inspect a suppressed business, but cannot make it eligible.
    pages, errors = Crawler(c.root()).crawl(business['public_website'])
    identity = e.identify(business, pages)
    checker = DNSChecks(c.root() / 'cache/email-v2/dns.json'); dns_results = {}
    for page in pages:
        for observation in page['observations']:
            preliminary = e.verification({'email': observation['email'], 'observations': [observation]}, identity)
            if preliminary['syntax_valid'] and preliminary['business_match'] and not preliminary['rejection_reasons']:
                domain = e.domain_name(observation['email'].split('@')[-1])
                if domain not in dns_results: dns_results[domain] = checker.check(domain)
    legacy = [row[0] for row in d.execute('SELECT normalized_email FROM email_candidates WHERE prospect_id=?', (bid,))]
    suppressed = [row[0] for row in d.execute('SELECT address FROM mm_suppression')]

    # --- Hunter.io enrichment (external corroboration) ---
    hunter_candidates = []
    if identity.get('canonical_root_domain'):
        try:
            import hunter_enrichment as hunter
            cache_dir = c.root() / 'cache' / 'email-v2'
            h_result = hunter.enrich_business(d, bid, identity['canonical_root_domain'], cache_dir=cache_dir)
            if h_result.get('candidates'):
                hunter.store_enrichment(d, bid, h_result)
                hunter_candidates = [c['email'] for c in h_result['candidates']]
                d.commit()
        except Exception:
            pass  # Hunter is optional — never block first-party flow

    # Merge Hunter candidates into legacy for evaluation
    all_legacy = list(legacy) + hunter_candidates
    result = e.evaluate(business, pages, dns_results, legacy=all_legacy, suppressed_addresses=suppressed, suppressed_business=store.is_suppressed(d, bid))
    result['crawl_errors'] = errors
    result['hunter_enriched'] = len(hunter_candidates)

    # --- Hunter corroboration metadata ---
    if hunter_candidates:
        corroborated = []
        hunter_high = []
        for row in d.execute("""
            SELECT email, hunter_confidence, status
            FROM hunter_enrichment
            WHERE business_id = ?
        """, (bid,)).fetchall():
            corroborated.append(row['email'])
            if row['status'] == 'OBSERVED' and row['hunter_confidence'] >= 80:
                hunter_high.append(row['email'])
        result['hunter_corroborated'] = corroborated
        result['hunter_high_confidence'] = hunter_high

    with d: store.persist(d, result)
    return store.status(d, bid)


def human_text(status):
    selected = status.get('selected') or {}; identity = status.get('identity') or {}
    lines = ['Business: ' + status['business'], 'Website: ' + (status.get('website') or 'Unknown'),
             'Canonical domain: ' + (identity.get('canonical_root_domain') or 'UNCONFIRMED'),
             'Email selected: ' + status['email'],
             'Confidence: ' + str(status.get('confidence') or '—') + ' / ' + selected.get('confidence_label', 'NO VERIFIED EMAIL FOUND'),
             'Mode: ' + status.get('mode', 'unknown'), 'Observed first-party: ' + ('YES' if selected.get('first_party_observed') else 'NO'),
             'MX: ' + ('PASS' if selected.get('mx_present') else 'UNCONFIRMED'),
             'SMTP: ' + selected.get('smtp_result', 'not_probed'), 'Catch-all: ' + selected.get('catch_all_status', 'unknown'),
             'Mailbox existence: ' + selected.get('mailbox_verification', 'inconclusive'),
             'Evidence count: ' + str(selected.get('source_count', 0)),
             'Last checked: ' + str(status.get('last_checked') or 'Never'), 'Human review: REQUIRED',
             'Outreach eligible: ' + ('YES — still requires exact-item human approval' if status.get('outreach_eligible') else 'NO — independent relevance, permission and exact-item human approval gates apply'),
             'Why: ' + '; '.join(selected.get('reasons') or identity.get('reasons') or ['No current VERIFIED_HIGH candidate'])]
    for url in sorted({o['source_url'] for o in selected.get('evidence', [])}): lines.append('  Evidence: ' + url)
    for url in status.get('contact_form_urls', []): lines.append('  Contact form: ' + url)
    if status.get('hunter_corroborated'):
        lines.append('  Hunter corroborated: ' + ', '.join(status['hunter_corroborated']))
    if status.get('hunter_high_confidence'):
        lines.append('  Hunter high confidence: ' + ', '.join(status['hunter_high_confidence']))
    for item in status.get('candidates', []):
        if item['email'] != status['email']:
            lines.append('  Review candidate: ' + item['email'] + ' / ' + item['confidence_label'] + ' — ' + '; '.join(item.get('rejection_reasons') or item.get('reasons', [])))
    return '\n'.join(lines)


def shadow(d, persist=False):
    if persist: store.require_production_persistence(d)
    from email_benchmark import compare, write_report
    result = compare(dt.datetime.now(e.UTC))
    if persist:
        if not store.installed(d): raise ValueError('Email migration required')
        with d:
            for row in result['results']: store.persist(d, row)
            encoded = json.dumps(result, sort_keys=True)
            d.execute('INSERT INTO email_shadow_runs(created_at,verifier_version,result_hash,result_json) VALUES(?,?,?,?)', (c.now(), e.VERSION, c.sha(encoded), encoded))
    write_report(result)
    return result['metrics']
