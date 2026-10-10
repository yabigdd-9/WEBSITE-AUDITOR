"""Offline synthetic checks for the bounded contact-review network adapter."""
import hashlib
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'money-machine'))

import email_baseline_capture as public  # noqa: E402
import mm_contact_review_network as network  # noqa: E402
import mm_email_network as email_network  # noqa: E402

CONFIG = {'max_requests': 5, 'max_pages': 3, 'max_dns_domains': 5,
          'collection_timeout_seconds': 55, 'dns_timeout_seconds': 15}
BUSINESS = {'id': 'synthetic-1', 'public_website': 'https://business.nz/'}


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv('MM_ROOT', str(tmp_path))
    monkeypatch.setenv('MM_EXTERNAL_SEND_DISABLED', '1')
    def denied(*args, **kwargs):
        raise AssertionError('Real network access is forbidden in this suite')
    monkeypatch.setattr(socket, 'getaddrinfo', denied)
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(email_network.time, 'sleep', lambda *args: None)


def response(url, raw, redirects=None):
    return {'url': url, 'redirects': redirects or [], 'content_type': 'text/html',
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'sha256': hashlib.sha256(raw).hexdigest()}, raw


class NoDNS:
    def __init__(self, path):
        self.path = path
    def check(self, domain, **kwargs):
        raise AssertionError('Fixture contains no email domains')


@pytest.mark.parametrize('url,expected', [
    ('https://Business.NZ/Contact-in Dunedin', 'https://business.nz/Contact-in%20Dunedin'),
    ('https://business.nz/Contact-%20Dunedin', 'https://business.nz/Contact-%20Dunedin'),
    ('https://business.nz/contact ', 'https://business.nz/contact%20'),
    ('https://business.nz/équipe', 'https://business.nz/%C3%A9quipe'),
    ('https://business.nz/%C3%A9quipe', 'https://business.nz/%C3%A9quipe'),
    ('https://business.nz/contact#team', 'https://business.nz/contact'),
    ('https://business.nz', 'https://business.nz/'),
    ('https://business.nz.:443/contact', 'https://business.nz:443/contact'),
    ('https://büro.nz/contact', 'https://xn--bro-hoa.nz/contact'),
])
def test_url_paths_are_encoded_once(url, expected):
    assert public.clean_url(url) == expected
    assert public.clean_url(expected) == expected


@pytest.mark.parametrize('url', [
    ' https://business.nz/', 'https://business.nz/\ncontact',
    'https://business.nz/contact%0a', 'https://business.nz/contact%250a',
    'https://business.nz/contact%7f', 'https://business.nz/contact\\other',
    'https://business.nz/contact%C2%85', 'https://business.nz/contact%25252525250a',
    'https://business.nz/contact%5cother', 'https://business.nz/contact%xx',
    'https://user:password@business.nz/', 'https://@business.nz/',
    'https://business.nz/?token=x', 'https://business.nz/?',
    'https://localhost/', 'https://localhost./', 'https://business.local/',
    'https://127.0.0.1/', 'https://[::1]/', 'https://2130706433/',
    'https://[2606:4700:4700::1111%25eth0]/',
    'https://127.1/', 'https://0x7f000001/', 'https://business.nz:22/',
    'https://-business.nz/', 'https://business..nz/', 'https://business_nz.nz/',
])
def test_unsafe_url_is_rejected_before_dns(url):
    with pytest.raises(ValueError):
        public.get_public(url)


def mock_http(monkeypatch, routes):
    requests, timeouts = [], []
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))])
    monkeypatch.setattr(public.ssl, 'create_default_context', lambda **kwargs: object())
    class Reply:
        def __init__(self, status, raw, headers):
            self.status, self.raw, self.headers = status, raw, headers
        def getheader(self, name, default=None):
            return self.headers.get(name, default)
        def read(self, count):
            return self.raw[:count]
    class Connection:
        def __init__(self, host, port=None, timeout=None, context=None):
            self.host, self.path = host, None
            timeouts.append(timeout)
        def request(self, method, path, headers):
            self.path = path
            requests.append('https://' + self.host + path)
        def getresponse(self):
            return Reply(*routes['https://' + self.host + self.path])
        def close(self):
            pass
    monkeypatch.setattr(public.http.client, 'HTTPSConnection', Connection)
    return requests, timeouts


def test_public_fetch_normalizes_hops_and_reports_each_actual_attempt(monkeypatch):
    requests, _ = mock_http(monkeypatch, {
        'https://business.nz/': (302, b'', {'Location': '/contact us'}),
        'https://business.nz/contact%20us': (200, b'contact', {}),
    })
    access, attempts = [], []
    meta, raw = public.get_public(BUSINESS['public_website'],
                                  before_hop=access.append, on_attempt=attempts.append)
    assert raw == b'contact'
    assert requests == access == attempts == [
        'https://business.nz/', 'https://business.nz/contact%20us']
    assert len(meta['redirects']) == 1


def test_access_callback_refuses_redirect_before_any_target_request(monkeypatch):
    requests, _ = mock_http(monkeypatch, {
        'https://business.nz/': (302, b'', {'Location': 'https://other.nz/private'}),
    })
    def access(url):
        if url.startswith('https://other.nz/'):
            raise ValueError('ACCESS_RESTRICTED_OR_ROBOTS_UNAVAILABLE')
    with pytest.raises(ValueError, match='ACCESS_RESTRICTED'):
        public.get_public(BUSINESS['public_website'], before_hop=access)
    assert requests == [BUSINESS['public_website']]


def test_collection_checks_robots_on_new_redirect_origin(monkeypatch, tmp_path):
    requests, _ = mock_http(monkeypatch, {
        'https://business.nz/robots.txt': (200, b'User-agent: *\nAllow: /\n', {}),
        'https://business.nz/': (302, b'', {'Location': 'https://other.nz/contact'}),
        'https://other.nz/robots.txt': (200, b'User-agent: *\nDisallow: /\n', {}),
    })
    _, doc, _ = network.collect_case(BUSINESS, tmp_path, CONFIG, dns_cls=NoDNS)
    assert doc['pages'] == []
    assert requests == ['https://business.nz/robots.txt', 'https://business.nz/',
                        'https://other.nz/robots.txt']
    assert all(url != 'https://other.nz/contact' for url in requests)
    assert doc['request_metrics']['actual_requests'] == 3


def test_collection_checks_robots_on_same_origin_redirect_path(monkeypatch, tmp_path):
    requests, _ = mock_http(monkeypatch, {
        'https://business.nz/robots.txt': (200, b'User-agent: *\nDisallow: /private\n', {}),
        'https://business.nz/': (302, b'', {'Location': '/private'}),
    })
    _, doc, _ = network.collect_case(BUSINESS, tmp_path, CONFIG, dns_cls=NoDNS)
    assert doc['pages'] == []
    assert requests == ['https://business.nz/robots.txt', 'https://business.nz/']
    assert doc['request_metrics']['actual_requests'] == 2
    ledger = json.loads((tmp_path / 'COLLECTION.json').read_text())
    assert sum(call['request_hops'] for call in ledger['public_fetch_calls']) == 2


def test_non_public_dns_never_attempts_http(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))])
    attempts = []
    with pytest.raises(ValueError, match='Non-public DNS'):
        public.get_public(BUSINESS['public_website'], on_attempt=attempts.append)
    assert attempts == []


def test_collection_spaces_do_not_burn_budget_or_lose_contact(monkeypatch, tmp_path):
    requests, _ = mock_http(monkeypatch, {
        'https://business.nz/robots.txt': (200, b'User-agent: *\nAllow: /\n', {}),
        'https://business.nz/': (200, b'<a href="/Contact-in Dunedin">Contact us</a>', {}),
        'https://business.nz/Contact-in%20Dunedin': (200, b'<h1>Contact us</h1>', {}),
        'https://business.nz/sitemap.xml': (404, b'', {}),
    })
    _, doc, _ = network.collect_case(BUSINESS, tmp_path, CONFIG, dns_cls=NoDNS)
    assert len(doc['pages']) == 2
    assert 'https://business.nz/Contact-in%20Dunedin' in requests
    assert doc['request_metrics'] == {'actual_requests': 4, 'reserved_requests': 0,
                                      'accounting': 'attempt_callbacks'}
    budget = json.loads((tmp_path / 'COLLECTION.json').read_text())['request_budget']
    assert budget == {'limit': 5, 'consumed_or_reserved': 4, 'remaining': 1}


def test_known_http_404_uses_one_attempt_and_allows_next_contact(monkeypatch, tmp_path):
    requests, _ = mock_http(monkeypatch, {
        'https://business.nz/robots.txt': (404, b'', {}),
        'https://business.nz/': (200, b'<a href="/contact-a">Contact</a><a href="/contact-b">Contact</a>', {}),
        'https://business.nz/contact-a': (404, b'', {}),
        'https://business.nz/contact-b': (200, b'<h1>Contact us</h1>', {}),
        'https://business.nz/sitemap.xml': (404, b'', {}),
    })
    _, doc, _ = network.collect_case(BUSINESS, tmp_path, CONFIG, dns_cls=NoDNS)
    assert len(doc['pages']) == 2
    assert len(requests) == 5
    assert doc['request_metrics']['actual_requests'] == 5


def test_real_redirect_attempts_robots_and_pages_share_cap(monkeypatch, tmp_path):
    requests, _ = mock_http(monkeypatch, {
        'https://business.nz/robots.txt': (200, b'User-agent: *\nAllow: /\n', {}),
        'https://business.nz/': (302, b'', {'Location': '/home'}),
        'https://business.nz/home': (200, b'<a href="/contact">Contact</a>', {}),
        'https://business.nz/contact': (302, b'', {'Location': '/contact-final'}),
        'https://business.nz/contact-final': (200, b'<h1>Contact</h1>', {}),
    })
    _, doc, _ = network.collect_case(BUSINESS, tmp_path, CONFIG, dns_cls=NoDNS)
    assert len(requests) == 5
    assert len(doc['pages']) == 2
    assert doc['request_metrics']['actual_requests'] == 5
    assert any('REQUEST_LIMIT' in error['reason'] for error in doc['errors'])


def test_legacy_unknown_failure_retains_reservation(tmp_path):
    calls = []
    def older(url, *, redirects):
        calls.append(url)
        raise OSError('Unknown transport outcome')
    _, doc, _ = network.collect_case(BUSINESS, tmp_path, CONFIG,
                                     get_public_fn=older, dns_cls=NoDNS)
    assert len(calls) == 1
    assert doc['request_metrics']['reserved_requests'] == 3
    assert not doc['pages']


def test_invalid_start_url_consumes_zero_budget(tmp_path):
    def never(url, *, redirects):
        raise AssertionError('Invalid URL must not reach fetch adapter')
    _, doc, _ = network.collect_case(
        {**BUSINESS, 'public_website': 'https://business.nz/contact%0a'}, tmp_path,
        CONFIG, get_public_fn=never, dns_cls=NoDNS)
    assert doc['request_metrics']['actual_requests'] == 0
    assert doc['request_metrics']['reserved_requests'] == 0


def test_socket_timeout_uses_remaining_collection_deadline(monkeypatch):
    _, timeouts = mock_http(monkeypatch, {'https://business.nz/': (200, b'ok', {})})
    monkeypatch.setattr(public.time, 'monotonic', lambda: 100.0)
    public.get_public(BUSINESS['public_website'], deadline=102.0)
    assert timeouts == [2.0]


def test_expired_deadline_is_zero_request_cost(monkeypatch, tmp_path):
    monkeypatch.setattr(network.time, 'monotonic', lambda: 100.0)
    _, doc, _ = network.collect_case(BUSINESS, tmp_path, CONFIG,
                                     deadline=99.0, dns_cls=NoDNS)
    assert doc['request_metrics']['actual_requests'] == 0
    assert doc['request_metrics']['reserved_requests'] == 0
    assert 'DEADLINE' in doc['errors'][0]['reason']


def test_dns_deadline_is_passed_and_domain_work_stops(monkeypatch, tmp_path):
    clock = [100.0]
    checked = []
    monkeypatch.setattr(network.time, 'monotonic', lambda: clock[0])
    class SyntheticCrawler:
        def __init__(self, folder, **kwargs):
            pass
        def crawl(self, website):
            return [{'url': website, 'observations': [
                {'email': 'contact@a.nz', 'syntax_error': None},
                {'email': 'contact@b.nz', 'syntax_error': None}]}], []
    class SyntheticDNS:
        def __init__(self, path):
            pass
        def check(self, domain, *, deadline):
            checked.append((domain, deadline))
            clock[0] = deadline
            return {'status': 'unknown'}
    _, doc, _ = network.collect_case(BUSINESS, tmp_path, CONFIG,
                                     crawler_cls=SyntheticCrawler,
                                     dns_cls=SyntheticDNS, deadline=108.0)
    assert checked == [('a.nz', 108.0)]
    assert doc['stage_timings']['dns_seconds'] == 8.0
    assert any('DNS_DEADLINE' in error['reason'] for error in doc['errors'])


def test_dns_resolver_timeouts_shrink_to_remaining_budget(monkeypatch, tmp_path):
    clock = [100.0]
    monkeypatch.setattr(email_network.time, 'monotonic', lambda: clock[0])
    class Resolver:
        def resolve(self, domain, kind):
            assert self.lifetime == 2.0
            assert self.timeout == 2.0
            clock[0] = 102.0
            raise email_network.dns.exception.Timeout
    result = email_network.DNSChecks(tmp_path / 'dns.json', resolver=Resolver()).check(
        'business.nz', deadline=102.0)
    assert result['status'] == 'unknown'
    assert result['domain_accepts_mail'] is None
