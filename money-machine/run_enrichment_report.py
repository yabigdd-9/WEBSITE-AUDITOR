#!/usr/bin/env python3
"""Full enrichment run + comparison report: first-party only vs first-party + Hunter.

For each business:
1. Run first-party page crawl + email discovery (no Hunter)
2. Run Hunter.io domain search
3. Evaluate with and without Hunter data
4. Compare selected email, score, and corroboration

Outputs: enrichment-report.json + human-readable summary
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "money-machine"))

import mm_core as c
import mm_email as e
import mm_email_store as store
import hunter_enrichment as hunter
from mm_email_network import Crawler, DNSChecks

UTC = dt.timezone.utc


def utcnow():
    return dt.datetime.now(UTC).isoformat()


def run_first_party_only(d, bid, business):
    """Run first-party discovery without Hunter."""
    pages, errors = Crawler(c.root()).crawl(business['public_website'])
    identity = e.identify(business, pages)
    checker = DNSChecks(c.root() / 'cache/email-v2/dns.json')
    dns_results = {}
    for page in pages:
        for observation in page['observations']:
            preliminary = e.verification(
                {'email': observation['email'], 'observations': [observation]}, identity
            )
            if preliminary['syntax_valid'] and preliminary['business_match'] and not preliminary['rejection_reasons']:
                domain = e.domain_name(observation['email'].split('@')[-1])
                if domain not in dns_results:
                    dns_results[domain] = checker.check(domain)
    legacy = [row[0] for row in d.execute(
        'SELECT normalized_email FROM email_candidates WHERE prospect_id=?', (bid,)
    )]
    suppressed = [row[0] for row in d.execute('SELECT address FROM mm_suppression')]
    result = e.evaluate(business, pages, dns_results, legacy=legacy,
                        suppressed_addresses=suppressed, suppressed_business=store.is_suppressed(d, bid))
    return result, errors


def run_with_hunter(d, bid, business, identity, pages, dns_results, legacy, suppressed):
    """Run evaluation with Hunter enrichment data."""
    root_domain = identity.get('canonical_root_domain')
    hunter_data = {}
    hunter_candidates = []

    if root_domain:
        try:
            cache_dir = c.root() / 'cache' / 'email-v2'
            h_result = hunter.enrich_business(d, bid, root_domain, cache_dir=cache_dir)
            if h_result.get('candidates'):
                hunter.store_enrichment(d, bid, h_result)
                hunter_candidates = [c['email'] for c in h_result['candidates']]
        except Exception:
            pass

    # Build hunter_data map
    for row in d.execute(
        "SELECT email, hunter_confidence, hunter_sources FROM hunter_enrichment WHERE business_id = ?",
        (bid,)
    ).fetchall():
        normalized = row['email'].lower().strip()
        hunter_data[normalized] = row['hunter_confidence']
        hunter_data[normalized + '_sources'] = json.loads(row['hunter_sources'] or '[]')

    all_legacy = list(legacy) + hunter_candidates
    result = e.evaluate(business, pages, dns_results, legacy=all_legacy,
                        suppressed_addresses=suppressed, suppressed_business=store.is_suppressed(d, bid),
                        hunter_data=hunter_data)
    return result, hunter_candidates


def run_enrichment_comparison(d, businesses):
    """Run comparison for all businesses."""
    results = []
    stats = {
        'total_businesses': len(businesses),
        'first_party_only': {'verified_high': 0, 'no_email': 0, 'other': 0},
        'with_hunter': {'verified_high': 0, 'no_email': 0, 'other': 0},
        'hunter_corroborated': 0,
        'hunter_new_candidates': 0,
        'score_changes': [],
    }

    for i, biz in enumerate(businesses):
        biz_id = biz['id']
        name = biz['name']
        website = biz['public_website']
        print(f"[{i+1}/{len(businesses)}] {name} ({website})")

        # Clear any prior Hunter data for clean comparison
        d.execute("DELETE FROM hunter_enrichment WHERE business_id = ?", (biz_id,))

        # --- First-party only ---
        try:
            fp_result, fp_errors = run_first_party_only(d, biz_id, biz)
        except Exception as ex:
            print(f"  First-party ERROR: {ex}")
            fp_result = {'selection_status': 'ERROR', 'selected': None, 'identity': {'canonical_root_domain': None}}

        # --- With Hunter ---
        try:
            # Re-crawl for clean run
            pages, errors = Crawler(c.root()).crawl(website)
            identity = e.identify(biz, pages)
            checker = DNSChecks(c.root() / 'cache/email-v2/dns.json')
            dns_results = {}
            for page in pages:
                for observation in page['observations']:
                    domain = e.domain_name(observation['email'].split('@')[-1])
                    if domain not in dns_results:
                        dns_results[domain] = checker.check(domain)
            legacy = [row[0] for row in d.execute(
                'SELECT normalized_email FROM email_candidates WHERE prospect_id=?', (biz_id,)
            )]
            suppressed = [row[0] for row in d.execute('SELECT address FROM mm_suppression')]
            h_result, hunter_candidates = run_with_hunter(d, biz_id, biz, identity, pages, dns_results, legacy, suppressed)
            d.commit()
        except Exception as ex:
            print(f"  Hunter ERROR: {ex}")
            h_result = {'selection_status': 'ERROR', 'selected': None}
            hunter_candidates = []

        # --- Compare ---
        fp_selected = fp_result.get('selected', {})
        h_selected = h_result.get('selected', {})

        fp_email = fp_selected.get('email') if fp_selected else None
        h_email = h_selected.get('email') if h_selected else None
        fp_score = fp_selected.get('confidence_score', 0) if fp_selected else 0
        h_score = h_selected.get('confidence_score', 0) if h_selected else 0
        fp_label = fp_selected.get('confidence_label', 'NO_VERIFIED_EMAIL') if fp_selected else 'NO_VERIFIED_EMAIL'
        h_label = h_selected.get('confidence_label', 'NO_VERIFIED_EMAIL') if h_selected else 'NO_VERIFIED_EMAIL'

        # Track stats
        if fp_label == 'VERIFIED_HIGH':
            stats['first_party_only']['verified_high'] += 1
        elif fp_label == 'NO_VERIFIED_EMAIL':
            stats['first_party_only']['no_email'] += 1
        else:
            stats['first_party_only']['other'] += 1

        if h_label == 'VERIFIED_HIGH':
            stats['with_hunter']['verified_high'] += 1
        elif h_label == 'NO_VERIFIED_EMAIL':
            stats['with_hunter']['no_email'] += 1
        else:
            stats['with_hunter']['other'] += 1

        corroborated = h_result.get('hunter_corroborated', [])
        hunter_high = h_result.get('hunter_high_confidence', [])
        if corroborated:
            stats['hunter_corroborated'] += 1
        if hunter_candidates:
            stats['hunter_new_candidates'] += len(hunter_candidates)

        score_diff = h_score - fp_score
        if score_diff != 0:
            stats['score_changes'].append({
                'business': name,
                'email': h_email,
                'fp_score': fp_score,
                'h_score': h_score,
                'diff': score_diff,
            })

        result_entry = {
            'business': name,
            'id': biz_id,
            'website': website,
            'domain': identity.get('canonical_root_domain'),
            'first_party': {
                'email': fp_email,
                'score': fp_score,
                'label': fp_label,
            },
            'with_hunter': {
                'email': h_email,
                'score': h_score,
                'label': h_label,
            },
            'hunter_candidates': hunter_candidates,
            'hunter_corroborated': corroborated,
            'hunter_high_confidence': hunter_high,
            'score_diff': score_diff,
        }
        results.append(result_entry)

        print(f"  FP: {fp_email} ({fp_score}/{fp_label}) → H: {h_email} ({h_score}/{h_label})")
        if hunter_candidates:
            print(f"  Hunter candidates: {len(hunter_candidates)}")
        if corroborated:
            print(f"  Corroborated: {corroborated}")

    return results, stats


def generate_report(results, stats, output_dir):
    """Generate JSON and human-readable report."""
    output_dir = Path(output_dir)

    # JSON report
    json_path = output_dir / 'enrichment-report.json'
    with open(json_path, 'w') as f:
        json.dump({'generated_at': utcnow(), 'stats': stats, 'results': results}, f, indent=2)
    print(f"\nSaved JSON: {json_path}")

    # Human-readable summary
    md_path = output_dir / 'enrichment-report.md'
    lines = []
    lines.append("# Hunter.io Enrichment Comparison Report")
    lines.append("")
    lines.append(f"Generated: {utcnow()}")
    lines.append(f"Total businesses: {stats['total_businesses']}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | First-Party Only | With Hunter |")
    lines.append("|--------|-----------------|-------------|")
    lines.append(f"| VERIFIED_HIGH | {stats['first_party_only']['verified_high']} | {stats['with_hunter']['verified_high']} |")
    lines.append(f"| NO_VERIFIED_EMAIL | {stats['first_party_only']['no_email']} | {stats['with_hunter']['no_email']} |")
    lines.append(f"| Other | {stats['first_party_only']['other']} | {stats['with_hunter']['other']} |")
    lines.append(f"| Businesses with Hunter corroboration | — | {stats['hunter_corroborated']} |")
    lines.append(f"| Total Hunter candidate emails | — | {stats['hunter_new_candidates']} |")
    lines.append("")

    if stats['score_changes']:
        lines.append("## Score Changes (Hunter Corroboration Boost)")
        lines.append("")
        lines.append("| Business | Email | FP Score | Hunter Score | Delta |")
        lines.append("|----------|-------|----------|--------------|-------|")
        for change in sorted(stats['score_changes'], key=lambda x: -x['diff']):
            lines.append(f"| {change['business']} | {change['email']} | {change['fp_score']} | {change['h_score']} | +{change['diff']} |")
        lines.append("")

    lines.append("## Detailed Results")
    lines.append("")
    for r in results:
        lines.append(f"### {r['business']}")
        lines.append(f"- **Domain**: {r['domain']}")
        lines.append(f"- **First-party**: {r['first_party']['email']} ({r['first_party']['score']}/{r['first_party']['label']})")
        lines.append(f"- **With Hunter**: {r['with_hunter']['email']} ({r['with_hunter']['score']}/{r['with_hunter']['label']})")
        if r['hunter_candidates']:
            lines.append(f"- **Hunter candidates**: {', '.join(r['hunter_candidates'])}")
        if r['hunter_corroborated']:
            lines.append(f"- **Corroborated**: {', '.join(r['hunter_corroborated'])}")
        if r['hunter_high_confidence']:
            lines.append(f"- **High confidence**: {', '.join(r['hunter_high_confidence'])}")
        lines.append("")

    md_path.write_text('\n'.join(lines) + '\n')
    print(f"Saved report: {md_path}")


def main():
    api_key = os.environ.get("HUNTER_API_KEY")
    if not api_key:
        print("HUNTER_API_KEY required")
        sys.exit(1)

    d = c.connect()

    # Get all non-dummy businesses
    businesses = [
        dict(r) for r in d.execute(
            "SELECT id, name, public_website FROM businesses WHERE is_dummy = 0 ORDER BY id"
        ).fetchall()
    ]

    print(f"Running enrichment comparison for {len(businesses)} businesses...")
    print("=" * 60)

    results, stats = run_enrichment_comparison(d, businesses)

    print("=" * 60)
    print("\nGenerating report...")
    generate_report(results, stats, c.root() / 'reports')

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"First-party VERIFIED_HIGH: {stats['first_party_only']['verified_high']}")
    print(f"With Hunter VERIFIED_HIGH: {stats['with_hunter']['verified_high']}")
    print(f"Hunter corroboration: {stats['hunter_corroborated']} businesses")
    print(f"Hunter candidates: {stats['hunter_new_candidates']} emails")
    if stats['score_changes']:
        print(f"Score boosts: {len(stats['score_changes'])} emails gained points")


if __name__ == "__main__":
    main()
