"""Bounded public observations; no authentication, form submission or active exploitation."""
import json
import socket
import ssl
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from .checks import Finding, analyse_html, classify_response
from .common import public_headers


def inspect_headers(response):
    findings = []
    url = str(response.url)
    for header in ['content-security-policy', 'x-content-type-options']:
        if not response.headers.get(header):
            findings.append(Finding('header-' + header, f'Missing {header}',
                                    'Review deployment requirements', 'low', url, check='headers'))
    if url.startswith('https:') and not response.headers.get('strict-transport-security'):
        findings.append(Finding('header-hsts', 'Missing HSTS', 'Review HTTPS deployment',
                                'medium', url, check='headers'))
    cookies = []
    for raw in response.headers.get_list('set-cookie'):
        parsed = SimpleCookie()
        try:
            parsed.load(raw)
        except Exception:
            continue
        for name, cookie in parsed.items():
            attrs = {'name': name, 'secure': bool(cookie['secure']),
                     'httponly': bool(cookie['httponly']), 'samesite': cookie['samesite']}
            cookies.append(attrs)
            if not cookie['secure'] and url.startswith('https:'):
                findings.append(Finding('cookie-secure', 'Cookie lacks Secure attribute',
                                        name, 'medium', url, check='headers', selector=name))
    return findings, {'headers': public_headers(response.headers), 'cookies': cookies}


def inspect_tls(url, timeout):
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        return [], {'status': 'not_applicable', 'reason': 'HTTP URL has no TLS certificate'}
    with socket.create_connection((parsed.hostname, parsed.port or 443), timeout=timeout) as raw:
        with ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname) as conn:
            cert = conn.getpeercert()
            expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert['notAfter']), UTC)
            days = (expires - datetime.now(UTC)).days
            findings = []
            if days < 30:
                findings.append(Finding('tls-expiry', 'Certificate expires within 30 days',
                                        expires.isoformat(), 'high', url, check='tls'))
            return findings, {'expires_at': expires.isoformat(), 'days_remaining': days,
                              'protocol': conn.version(), 'cipher': conn.cipher()[0]}


def inspect_dns(url, timeout):
    import dns.exception
    import dns.resolver
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    host = urlparse(url).hostname
    result = {}
    for name, kind in [(host, 'A'), (host, 'AAAA'), (host, 'MX'), (host, 'TXT'),
                       ('_dmarc.' + host, 'TXT')]:
        key = name + ':' + kind
        try:
            result[key] = {'status': 'ok', 'records': [str(r) for r in resolver.resolve(name, kind)]}
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            result[key] = {'status': 'absent', 'records': []}
        except dns.exception.DNSException as exc:
            raise RuntimeError(f'DNS unavailable for {key}: {exc}') from exc
    result['limitations'] = 'DKIM needs a supplied selector; absent email records do not prove a website defect.'
    return [], result


def inspect_schema(html, url, profile):
    soup = BeautifulSoup(html, 'lxml')
    types, errors = [], []
    def visit(value):
        if isinstance(value, dict):
            typ = value.get('@type', [])
            types.extend(typ if isinstance(typ, list) else [typ])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
    findings = [Finding('invalid-jsonld', 'Invalid JSON-LD', error, 'medium', url,
                        check='schema', selector=f'script-jsonld-{i}') for i, error in enumerate(errors)]
    generator = soup.find('meta', attrs={'name': 'generator'})
    return findings, {'types': sorted(set(str(t) for t in types)), 'profile': profile,
        'generator': generator.get('content', '') if generator else '',
        'local_business_review': 'Check identity, address and service area against the business owner.',
        'crawler_readiness': {'robots_meta': [m.get('content', '') for m in soup.select('meta[name="robots"]')],
                             'rendered_content_comparison': 'Available only in rendered mode'}}


def crawl(url, fetcher, options):
    base = urlparse(url)
    origin = f'{base.scheme}://{base.netloc}'
    robots_response = fetcher.get(origin + '/robots.txt')
    robot = RobotFileParser()
    if robots_response.status_code == 200:
        robot.parse(robots_response.text.splitlines())
    elif robots_response.status_code in (404, 410):
        robot.parse([])
    else:
        raise RuntimeError(f'robots.txt unavailable: HTTP {robots_response.status_code}')
    # The entry page is explicitly requested; robots controls subsequent crawling.
    queue = [(url, 0)]
    sitemap_urls = robot.site_maps() or [origin + '/sitemap.xml']
    sitemap_evidence = []
    for sitemap_url in sitemap_urls[:2]:
        if urlparse(sitemap_url).netloc != base.netloc:
            continue
        response = fetcher.get(sitemap_url)
        sitemap_evidence.append({'url': sitemap_url, 'status': response.status_code})
        if response.status_code == 200:
            try:
                xml = ET.fromstring(response.content)
                if xml.tag.rsplit('}', 1)[-1] == 'urlset':
                    for loc in xml.iter():
                        if loc.tag.rsplit('}', 1)[-1] == 'loc' and loc.text:
                            queue.append((loc.text.strip(), 1))
                            if len(queue) >= options.max_pages * 2:
                                break
            except ET.ParseError:
                sitemap_evidence[-1]['parse_error'] = 'Not valid sitemap XML'
    visited, pages, edges, findings, blocked = set(), [], [], [], []
    while queue and len(visited) < options.max_pages:
        target, depth = queue.pop(0)
        if target in visited or urlparse(target).netloc != base.netloc or depth > options.max_depth:
            continue
        visited.add(target)
        if options.respect_robots and not robot.can_fetch('WebsiteAuditorToolkit', target):
            blocked.append(target)
            continue
        response = fetcher.get(target)
        status, errors = classify_response(response.status_code, response.text)
        for error in errors:
            findings.append(Finding(error.defect_key, error.defect, error.impact, error.severity,
                                    target, check='crawl'))
        links = []
        if status == 'ok' and ('html' in response.headers.get('content-type', 'text/html')):
            page_findings, evidence = analyse_html(response.text, str(response.url))
            findings.extend(page_findings)
            soup = BeautifulSoup(response.text, 'lxml')
            links = list(dict.fromkeys(urljoin(str(response.url), a['href']).split('#')[0]
                                      for a in soup.select('a[href]')))
            for link in links[:options.max_links]:
                if urlparse(link).scheme in ('http', 'https'):
                    edges.append({'from': target, 'to': link})
                    if len(queue) < options.max_pages * 4:
                        queue.append((link, depth + 1))
        pages.append({'url': target, 'status_code': response.status_code, 'depth': depth, 'links': links[:options.max_links]})
    return findings, {'pages': pages, 'edges': edges, 'robots_blocked': blocked,
                      'sitemaps': sitemap_evidence, 'bounded': bool(queue),
                      'limits': {'pages': options.max_pages, 'depth': options.max_depth}}
