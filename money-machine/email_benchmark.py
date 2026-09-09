"""Reproducible V1 persisted-output / V2 shadow benchmark. No outreach writes."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

import mm_email as e
from mm_email_network import DNSChecks, atomic_json

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests/fixtures/email_finder_golden.json'
DNS_FILE = ROOT / 'tests/fixtures/email_dns.json'


def load_cases():
    golden = json.loads(GOLDEN.read_text())
    return golden, [(c, [e.parse_page(p, (ROOT / p['path']).read_bytes()) for p in c['pages']]) for c in golden['cases']]


def capture_dns():
    _, cases = load_cases(); checker = DNSChecks(); domains = set()
    for c, pages in cases:
        identity = e.identify(c['business'], pages)
        for p in pages:
            for o in p['observations']:
                v = e.verification({'email': o['email'], 'observations': [o]}, identity)
                if v['syntax_valid'] and v['business_match'] and not v['rejection_reasons']:
                    domains.add(e.domain_name(o['email'].split('@')[-1]))
    results = {}
    for domain in sorted(domains):
        results[domain] = checker.check(domain)
        print(domain, results[domain]['status'], flush=True)
        atomic_json(DNS_FILE, {'captured_at': e.utcnow(), 'results': results, 'smtp': 'Not probed; no mailbox-existence or delivery claim'})
    return results


def compare(at=None):
    golden, cases = load_cases(); dns_doc = json.loads(DNS_FILE.read_text())
    # Replay at the DNS snapshot's date by default; live persistence must instead
    # explicitly use current time, and readiness always enforces live expiry.
    at = at or dt.datetime.fromisoformat(dns_doc['captured_at'])
    metrics = {'prospects_discovered': len(cases), 'domains_identified': 0, 'domain_identity_failures': 0,
               'raw_emails_observed': 0, 'candidates_generated': 0, 'verified_high': 0, 'verified_medium': 0,
               'rejected': 0, 'suppressed': 0, 'no_verified_email': 0, 'catch_all_domains': 0, 'smtp_hard_rejects': 0,
               'third_party_only_candidates': 0, 'vendor_developer_emails_rejected': 0, 'duplicate_emails': 0,
               'stale_evidence_count': 0, 'selected_email_count': 0, 'true_positive': 0, 'false_positive': 0,
               'golden_publicly_confirmed_emails': 0, 'eligible_public_emails': 0, 'old_supported_emails': 0,
               'old_total_reported_emails': 0, 'old_unknown_emails': 0, 'unsupported_guesses_promoted': 0,
               'external_sends': 0, 'model_calls': 0, 'paid_inference_cost': 0}
    results = []; sources = []
    for c, pages in cases:
        result = e.evaluate(c['business'], pages, dns_doc['results'], legacy=c['v1_emails'], suppressed_business=c['suppressed_business'], at=at)
        metrics['domains_identified'] += result['identity']['status'] == 'HIGH'
        metrics['domain_identity_failures'] += result['identity']['status'] != 'HIGH'
        metrics['raw_emails_observed'] += sum(len(p['observations']) for p in pages)
        metrics['duplicate_emails'] += sum(len(p['observations']) for p in pages) - len({o['email'] for p in pages for o in p['observations']})
        metrics['no_verified_email'] += result['selected'] is None
        metrics['golden_publicly_confirmed_emails'] += len(c['confirmed_emails'])
        if not c['suppressed_business']: metrics['eligible_public_emails'] += len(c['confirmed_emails'])
        metrics['old_total_reported_emails'] += len(c['v1_emails'])
        metrics['old_supported_emails'] += len(set(c['v1_emails']) & set(c['confirmed_emails']))
        metrics['old_unknown_emails'] += len(set(c['v1_emails']) - set(c['confirmed_emails']))
        for v in result['results']:
            for state in ('VERIFIED_HIGH', 'VERIFIED_MEDIUM', 'REJECTED', 'SUPPRESSED'):
                if v['confidence_label'] == state: metrics[state.lower()] += 1
            metrics['stale_evidence_count'] += v['freshness'] == 'stale'
            metrics['smtp_hard_rejects'] += v['smtp_result'] == 'rejected'
            metrics['third_party_only_candidates'] += 'Third-party-only address evidence' in v['rejection_reasons']
            metrics['vendor_developer_emails_rejected'] += 'Developer/vendor context' in v['rejection_reasons']
            if v['confidence_label'] == 'VERIFIED_HIGH':
                metrics['unsupported_guesses_promoted'] += not v['first_party_observed'] or not v['evidence']
                if v['email'] in c['confirmed_emails']: metrics['true_positive'] += 1
                else: metrics['false_positive'] += 1
        if result['selected']:
            metrics['selected_email_count'] += 1; sources.append(result['selected']['source_count'])
        new = result['selected']['email'] if result['selected'] else 'NO_VERIFIED_EMAIL'
        result['comparison'] = {'old_email': c['v1_emails'], 'old_confidence': c['v1_confidence'], 'new_email': new,
              'truth_label': c['truth_label'], 'confirmed_emails': c['confirmed_emails'],
              'disagreement_reason': 'Suppression preserved' if c['suppressed_business'] else '; '.join(result['identity']['reasons']) if result['identity']['status'] != 'HIGH' else 'Only VERIFIED_HIGH addresses are eligible; role relevance determines selection' if new not in c['v1_emails'] else 'Published legacy address corroborated with current first-party/MX evidence'}
        results.append(result)
    n = metrics['true_positive'] + metrics['false_positive']
    metrics['precision'] = metrics['true_positive'] / n if n else None
    metrics['false_positive_rate'] = metrics['false_positive'] / n if n else None
    metrics['recall_all_public_emails'] = metrics['true_positive'] / metrics['golden_publicly_confirmed_emails']
    metrics['recall_eligible_public_emails'] = metrics['true_positive'] / metrics['eligible_public_emails'] if metrics['eligible_public_emails'] else None
    metrics['average_evidence_sources_per_selected_email'] = sum(sources) / len(sources) if sources else 0
    metrics['catch_all_unknown_domains'] = len(dns_doc['results'])
    metrics['smtp_probed_mailboxes'] = 0
    metrics['new_prospects_discovered'] = 0
    # Wilson interval conveys the very small sample; point precision is not a
    # defensible claim of >=95% population precision.
    if n:
        z=1.96; p=metrics['precision']; den=1+z*z/n; center=(p+z*z/(2*n))/den; half=z*((p*(1-p)/n+z*z/(4*n*n))**.5)/den
        metrics['precision_95pct_wilson_interval'] = [max(0, center-half), min(1, center+half)]
    return {'evaluated_at': at.isoformat(), 'verifier_version': e.VERSION, 'golden_sha256': e.hash_bytes(GOLDEN.read_bytes()),
            'dns_sha256': e.hash_bytes(DNS_FILE.read_bytes()), 'metrics': metrics, 'results': results,
            'limitations': golden['coverage_limitations'] + ['V1 is the retained legacy output, not a rerun of an unavailable historical LLM finder.','Public attribution benchmark does not measure live mailbox delivery. SMTP is not probed.']}


def write_report(result):
    out = ROOT / 'reports'; atomic_json(out / 'EMAIL_FINDER_METRICS.json', result)
    m = result['metrics']
    lines = ['# V1 / V2 shadow comparison', '', 'Read-only replay of all 18 real prospects; no outreach, approvals or CRM changes.', '',
             'V1 consists of preserved historical DB/report addresses. No executable historical finder exists to rerun. V2 uses frozen public captures and dated DNS. Report confidence is not mailbox verification.', '',
             '| Business | V1 recorded address(es) | V2 selected | Reason |', '|---|---|---|---|']
    for r in result['results']:
        c=r['comparison']; lines.append('| '+r['business']+' | '+(', '.join(c['old_email']) or 'None recorded')+' | '+c['new_email']+' | '+c['disagreement_reason']+' |')
    lines += ['', '## Measured results', '', '```json', json.dumps(m, indent=2), '```', '', '## Interpretation', '',
              'Precision is for every VERIFIED_HIGH candidate, not just the one selected per business. Suppressed businesses contribute no high contacts. Recall is reported both over all public addresses and after excluding suppressed businesses. Unknown/ambiguous truth is never treated as correct. Synthetic regressions are excluded from all real-business accuracy numbers.', '',
              'The existing historical selected addresses are mostly publicly attributable; this sample does not establish the user-reported overall high false-positive rate. The reproduced V1 flaw and live placeholder/fragment captures demonstrate why the old admission policy is unsafe. Do not invent a before/after delivery improvement.', '',
              'See `EMAIL_FINDER_METRICS.json` for per-address reasons, provenance, raw observations, score components, catch-all/SMTP uncertainty and exact benchmark hashes.', '',
              '## Limitations', '', *['- '+x for x in result['limitations']]]
    (out / 'EMAIL_FINDER_V1_V2_COMPARISON.md').write_text('\n'.join(lines)+'\n')
    return m


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture-dns',action='store_true');p.add_argument('--live-time',action='store_true');a=p.parse_args()
    if a.capture_dns: capture_dns()
    else: print(json.dumps(write_report(compare(dt.datetime.now(e.UTC) if a.live_time else None)),indent=2))
