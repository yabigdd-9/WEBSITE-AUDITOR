"""Bounded GET/DNS adapters. No SMTP DATA, messages, model calls, or form submits."""
import datetime as dt
import http.client
import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET
import dns.resolver
import dns.exception
import ipaddress

from email_baseline_capture import get_public, CONTACT_PATHS
from mm_email import domain_name, root_domain, parse_page, age_days, utcnow, hash_bytes


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(value, indent=2)); temp.replace(path)


class DNSChecks:
    def __init__(self, cache=None, resolver=None):
        self.cache_path = Path(cache) if cache else None
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path and self.cache_path.exists() else {}
        self.resolver = resolver or dns.resolver.Resolver()
        self.resolver.lifetime = 5; self.resolver.timeout = 3
        self.resolver.cache = dns.resolver.LRUCache(max_size=256)

    def check(self, domain):
        domain = domain_name(domain)
        old = self.cache.get(domain)
        if old and 0 <= age_days(old.get('checked_at')) <= 1 / 24:
            return old
        result = {'domain': domain, 'checked_at': utcnow(), 'domain_resolves': None, 'mx_present': None,
                  'mx_hosts': [], 'domain_accepts_mail': None, 'status': 'unknown', 'method': 'DNS MX and public MX target address resolution'}
        try:
            answer = self.resolver.resolve(domain, 'MX')
            records = sorted((int(r.preference), str(r.exchange).rstrip('.')) for r in answer)
            result['domain_resolves'] = True
            if any(not host for _, host in records):
                result.update(mx_present=False, domain_accepts_mail=False, status='null_mx')
            else:
                result['mx_hosts'] = [host for _, host in records]
                result['mx_present'] = bool(records)
                routes = []
                uncertain = False
                for _, host in records[:5]:
                    addresses = []
                    for kind in ('A', 'AAAA'):
                        try: addresses.extend(str(a) for a in self.resolver.resolve(host, kind))
                        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer): pass
                        except dns.exception.DNSException: uncertain = True
                    if addresses and all(ipaddress.ip_address(a).is_global for a in addresses): routes.append(host)
                result['routable_mx_hosts'] = routes
                result['domain_accepts_mail'] = True if routes else None if uncertain else False
                result['status'] = 'mx' if routes else 'unknown' if uncertain else 'unroutable_mx'
        except dns.resolver.NXDOMAIN:
            result.update(domain_resolves=False, mx_present=False, domain_accepts_mail=False, status='nxdomain')
        except dns.resolver.NoAnswer:
            # A-only fallback is not assumed to run an SMTP listener. Preserve
            # rejection until demonstrable mail routing can be supplied/reviewed.
            result.update(domain_resolves=True, mx_present=False, domain_accepts_mail=False, status='no_mx')
        except dns.exception.DNSException:
            result['status'] = 'unknown'
        self.cache[domain] = result
        if self.cache_path: atomic_json(self.cache_path, self.cache)
        return result


def smtp_evidence(recipient_code=None, random_recipient_code=None, *, condition=None, checked_at=None):
    """Interpret controlled/imported probe evidence without opening SMTP sockets.

    A random recipient acceptance is catch-all; recipient acceptance with no
    random-recipient rejection remains inconclusive. 5xx is a hard recipient
    reject only when supplied for RCPT TO, not a connection/banner failure.
    """
    status = condition or 'not_probed'; catch_all = 'unknown'
    if random_recipient_code and 200 <= random_recipient_code < 300: catch_all = 'yes'
    elif random_recipient_code and 500 <= random_recipient_code < 600: catch_all = 'no'
    if recipient_code:
        status = 'accepted' if 200 <= recipient_code < 300 else 'temporary_failure' if 400 <= recipient_code < 500 else 'rejected' if 500 <= recipient_code < 600 else 'inconclusive'
    return {'result': status, 'catch_all_status': catch_all, 'checked_at': checked_at or utcnow(),
            'recipient_rcpt_code': recipient_code, 'random_rcpt_code': random_recipient_code,
            'mailbox_confirmed': status == 'accepted' and catch_all == 'no'}


class Crawler:
    def __init__(self, root, max_pages=5, max_requests=8, fetcher=None):
        if not 1 <= max_pages <= 5 or not max_pages <= max_requests <= 8: raise ValueError('Crawl bounds exceeded')
        self.root = Path(root); self.folder = self.root / 'cache/email-v2'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.max_pages = max_pages; self.max_requests = max_requests; self.fetch = fetcher or get_public

    def crawl(self, website):
        if not website: return [], ['No website recorded']
        index = self.folder / (hash_bytes(website) + '.json')
        state = json.loads(index.read_text()) if index.exists() else {'pages': [], 'errors': [], 'pending': [website], 'requests': 0, 'started_at': utcnow(), 'complete': False}
        if 0 <= age_days(state['started_at']) <= 1:
            if state.get('complete'):
                try: return [parse_page(p, (self.root / p['path']).read_bytes()) for p in state['pages']], state['errors']
                except (OSError, ValueError): pass
        else: state = {'pages': [], 'errors': [], 'pending': [website], 'requests': 0, 'started_at': utcnow(), 'complete': False}
        seen = {p['url'] for p in state['pages']}; parsed = []
        attempts = state.setdefault('attempts', {})
        for p in state['pages']:
            try: parsed.append(parse_page(p, (self.root / p['path']).read_bytes()))
            except (ValueError, OSError): state['errors'].append('Cached capture failed integrity')
        canonical = root_domain(parsed[0]['url']) if parsed else root_domain(website)
        while state['pending'] and len(parsed) < self.max_pages and state['requests'] < self.max_requests:
            url = state['pending'].pop(0)
            if url in seen: continue
            if parsed and root_domain(url) != canonical: continue
            seen.add(url); state['requests'] += 1
            attempts[url] = attempts.get(url, 0) + 1
            try:
                meta, data = self.fetch(url)
                meta['requested_url'] = url
                if parsed and root_domain(meta['url']) != canonical: raise ValueError('Cross-domain contact redirect')
                canonical = root_domain(meta['url'])
                path = self.folder / (meta['sha256'] + '.capture'); path.write_bytes(data)
                meta['path'] = str(path.relative_to(self.root))
                if 'xml' in meta.get('content_type', '') or urlsplit(url).path.endswith('sitemap.xml'):
                    tree = ET.fromstring(data)
                    for loc in tree.iter():
                        if loc.tag.endswith('loc') and loc.text and root_domain(loc.text) == canonical and any(x in loc.text for x in CONTACT_PATHS): state['pending'].append(loc.text)
                    continue
                page = parse_page(meta, data)
                # Distinct URLs and response hashes are retained, but redirects
                # to the same page do not inflate source counts.
                if page['url'] not in {p['url'] for p in parsed}: parsed.append(page); state['pages'].append(meta)
                links = []
                for link in page['links']:
                    dest = urljoin(meta['url'], link['href']).split('#')[0]; part = urlsplit(dest)
                    if part.scheme not in ('http', 'https') or part.query or root_domain(dest) != canonical: continue
                    label = link['text'].lower(); path = part.path.lower()
                    if 'contact' in label or 'contact' in path: links.append((0, dest))
                    elif any(t in path for t in CONTACT_PATHS): links.append((1, dest))
                    elif path.endswith('.pdf') and any(t in label + path for t in ('contact', 'team', 'staff')): links.append((2, dest))
                state['pending'].extend(u for _, u in sorted(links) if u not in seen)
                if state['requests'] == 1:
                    base = urlsplit(meta['url']); state['pending'].append(base.scheme + '://' + base.netloc + '/sitemap.xml')
            except (OSError, ValueError, ET.ParseError, http.client.HTTPException) as e:
                state['errors'].append({'url': url, 'reason': type(e).__name__ + ': ' + str(e)[:120]})
                if isinstance(e, (OSError, http.client.HTTPException)) and attempts[url] < 2:
                    seen.discard(url); state['pending'].append(url)
                    time.sleep(.3 * 2 ** (attempts[url] - 1))
            finally:
                # Checkpoint every request; crash recovery preserves known errors.
                atomic_json(index, state)
            time.sleep(.3)
        state['complete'] = True; atomic_json(index, state)
        return parsed, state['errors']
