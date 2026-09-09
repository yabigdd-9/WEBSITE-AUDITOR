"""Bounded public-page collection for manual golden-set review; no DB writes.

This collector saves response bodies, never cookies/headers/credentials. It does
not extract, classify, verify, or select email addresses.
"""
import argparse
import datetime as dt
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import socket
import sqlite3
import ssl
import time
import certifi
from urllib.parse import urlsplit, urljoin, urlunsplit
from bs4 import BeautifulSoup

MAX_BYTES = 3_000_000
CONTACT_PATHS = ('/contact', '/contact-us', '/about', '/about-us', '/team',
                 '/staff', '/people', '/our-team', '/locations')


def clean_url(url):
    p = urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password or p.query or p.port not in (None, 80, 443):
        raise ValueError('Unsafe or parameterized URL')
    if p.hostname == 'localhost' or p.hostname.endswith(('.local', '.internal')):
        raise ValueError('Private hostname')
    return urlunsplit((p.scheme, p.netloc.lower(), p.path or '/', '', ''))


def get_public(url, redirects=4):
    """GET only; validate every hop and pin the socket to a checked public IP."""
    chain = []
    for _ in range(redirects + 1):
        url = clean_url(url); p = urlsplit(url)
        addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Non-public DNS destination')
        ip = addresses[0][4][0]
        conn = (http.client.HTTPSConnection(p.hostname, timeout=12, context=ssl.create_default_context(cafile=certifi.where()))
                if p.scheme == 'https' else http.client.HTTPConnection(p.hostname, timeout=12))
        # HTTP Host and TLS SNI retain the original hostname; DNS cannot rebind.
        conn._create_connection = lambda address, timeout, *args, **kwargs: socket.create_connection((ip, address[1]), timeout)
        try:
            conn.request('GET', p.path or '/', headers={'User-Agent': 'MoneyMachine-EvidenceReview/2.0', 'Accept': 'text/html,application/pdf,text/plain,application/xml'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                dest = clean_url(urljoin(url, response.getheader('Location') or ''))
                chain.append({'from': url, 'to': dest, 'status': response.status}); url = dest; continue
            if response.status != 200:
                raise ValueError('HTTP_' + str(response.status))
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES: raise ValueError('Page exceeds byte limit')
            return {'url': url, 'redirects': chain, 'content_type': response.getheader('Content-Type', ''),
                    'captured_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                    'sha256': hashlib.sha256(data).hexdigest()}, data
        finally:
            conn.close()
    raise ValueError('Redirect limit exceeded')


def collect(root, limit=18, retry_failed=False, complete_short=False):
    out = root / 'tests/fixtures/email_captures'; out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect('file:' + str(root / 'database/money_machine.db') + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    rows = [dict(x) for x in db.execute('SELECT id,name,region,public_website FROM businesses WHERE is_dummy=0 ORDER BY id LIMIT ?', (limit,))]; db.close()
    manifest = []
    prior = out / 'manifest.json'
    if prior.exists(): manifest = json.loads(prior.read_text())
    if retry_failed:
        (out / ('prior-' + str(time.time_ns()) + '.json')).write_text(json.dumps(manifest, indent=2))
        manifest = [x for x in manifest if x['pages'] or not x['business']['public_website']]
    for b in rows:
        existing = next((x for x in manifest if x['business']['id'] == b['id']), None)
        if existing and (not complete_short or len(existing['pages']) >= 3 or not existing['pages']): continue
        record = existing or {'business': b, 'pages': [], 'errors': []}
        queue = [b['public_website']] if b['public_website'] else []
        seen = {x['url'] for x in record['pages']}
        if existing:
            page = existing['pages'][0]; soup = BeautifulSoup((root / page['path']).read_bytes(), 'html.parser')
            queue = [urljoin(page['url'], a['href']) for a in soup.select('a[href]')
                     if any(t in a.get_text(' ', strip=True).lower() for t in ('contact', 'christchurch'))
                     and urlsplit(urljoin(page['url'], a['href'])).hostname == urlsplit(page['url']).hostname]
        while queue and len(seen) < 3:
            url = queue.pop(0)
            if url in seen: continue
            seen.add(url)
            try:
                meta, data = get_public(url)
                meta['requested_url'] = url
                file = out / (str(b['id']) + '-' + str(len(record['pages'])) + '.html')
                file.write_bytes(data); meta['path'] = str(file.relative_to(root))
                soup = BeautifulSoup(data, 'html.parser')
                meta['title'] = soup.title.get_text(' ', strip=True) if soup.title else ''
                record['pages'].append(meta)
                if len(seen) == 1:
                    host = urlsplit(meta['url']).hostname
                    links = []
                    for a in soup.select('a[href]'):
                        u = urljoin(meta['url'], a['href']); p = urlsplit(u)
                        if p.hostname != host or p.query: continue
                        path = p.path.rstrip('/').lower()
                        if any(x in path for x in CONTACT_PATHS):
                            links.append((0 if 'contact' in path else 1, u.split('#')[0]))
                    queue.extend(dict.fromkeys(u for _, u in sorted(links)))
            except (ValueError, OSError, http.client.HTTPException) as e:
                record['errors'].append({'url': url, 'reason': type(e).__name__ + ': ' + str(e)[:150]})
            time.sleep(.25)
        if not existing: manifest.append(record)
        tmp = prior.with_suffix('.tmp'); tmp.write_text(json.dumps(manifest, indent=2)); tmp.replace(prior)
        print(b['id'], b['name'], len(record['pages']), 'pages', len(record['errors']), 'errors', flush=True)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--limit', type=int, default=18)
    p.add_argument('--retry-failed', action='store_true'); p.add_argument('--complete-short', action='store_true'); a = p.parse_args()
    if not 1 <= a.limit <= 18: p.error('Baseline limited to the existing 18 businesses')
    collect(Path(__file__).resolve().parents[1], a.limit, a.retry_failed, a.complete_short)
