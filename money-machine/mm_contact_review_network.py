"""Bounded public evidence collection; no models, messages or database writes.

The caller owns the case deadline and evidence directory. Public GET hops,
including robots and redirects, share one ledger. DNS remains advisory.
"""
from __future__ import annotations

import inspect
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from email_baseline_capture import clean_url, get_public
from mm_email_network import Crawler, DNSChecks


def _supports(function, name):
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False
    return name in parameters


def _save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, indent=2)
        handle.write('\n')
    temporary.replace(path)


def collect_case(business, folder, config, *, get_public_fn=get_public,
                 crawler_cls=Crawler, dns_cls=DNSChecks, deadline=None,
                 dns_cache_path=None):
    """Return ``(folder, document, 'PUBLIC_GET_DNS')`` without authority changes.

    ``deadline`` is an absolute monotonic case deadline. Collection and DNS have
    additional 55/15 second ceilings by default. Older injected test adapters
    lacking attempt hooks retain conservative worst-case reservations.
    """
    folder = Path(folder)
    evidence = folder / 'evidence'
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.monotonic()
    collection_deadline = started + config.get('collection_timeout_seconds', 55)
    if deadline is not None:
        collection_deadline = min(collection_deadline, deadline)
    robots, calls = {}, []
    limit = config['max_requests']
    actual, reserved = 0, 0
    instrumented = (_supports(get_public_fn, 'before_hop')
                    and _supports(get_public_fn, 'on_attempt'))

    def remaining():
        return max(0, limit - actual - reserved)

    def check_time():
        if time.monotonic() >= collection_deadline:
            raise ValueError('CONTACT_REVIEW_COLLECTION_DEADLINE')

    def attempt(url):
        nonlocal actual
        check_time()
        if remaining() <= 0:
            raise ValueError('CONTACT_REVIEW_REQUEST_LIMIT')
        actual += 1

    def bounded_get(url, *, page=False):
        nonlocal actual, reserved
        # Normalization has no side effects. Invalid input consumes no request.
        url = clean_url(url)
        check_time()
        if page and not instrumented:
            authorize_page(url)
        if remaining() <= 0:
            raise ValueError('CONTACT_REVIEW_REQUEST_LIMIT')
        before_reserved = reserved
        call_attempts = 0
        def count_attempt(url):
            nonlocal call_attempts
            attempt(url)
            call_attempts += 1
        allocation = min(3, remaining())
        kwargs = {'redirects': allocation - 1}
        if instrumented:
            kwargs.update(before_hop=authorize_page if page else None,
                          on_attempt=count_attempt)
            if _supports(get_public_fn, 'deadline'):
                kwargs['deadline'] = collection_deadline
        else:
            reserved += allocation
        try:
            meta, raw = get_public_fn(url, **kwargs)
            if not instrumented:
                used = 1 + len(meta.get('redirects', []))
                if used > allocation:
                    raise ValueError('CONTACT_REVIEW_REDIRECT_LIMIT')
                reserved -= allocation
                actual += used
                call_attempts = used
                # Production uses pre-hop hooks; old synthetic adapters can
                # still return redirect metadata and are checked before reuse.
                if page:
                    for hop in meta.get('redirects', []):
                        authorize_page(clean_url(hop['to']), require_attempt=False)
            calls.append({'url': url, 'status': 'captured',
                          'redirects': meta.get('redirects', []),
                          'request_hops': call_attempts})
            return meta, raw
        except Exception as exc:
            # An uninstrumented failure retains its full reservation. An
            # instrumented failure before any HTTP attempt can be unknown DNS
            # or transport telemetry; reserve rather than invent zero cost.
            known_zero = (str(exc) in {
                'CONTACT_REVIEW_REQUEST_LIMIT',
                'CONTACT_REVIEW_COLLECTION_DEADLINE',
                'ACCESS_RESTRICTED_OR_ROBOTS_UNAVAILABLE',
            } or str(exc).startswith(('Unsafe ', 'Private ', 'Non-public ')))
            if instrumented and not call_attempts and not known_zero:
                reserved += min(allocation, remaining())
            calls.append({'url': url, 'status': str(exc)[:160],
                          'request_hops': call_attempts,
                          'reserved_hops': reserved - before_reserved})
            raise

    def authorize_page(url, *, require_attempt=True):
        check_time()
        if require_attempt and remaining() <= 0:
            raise ValueError('CONTACT_REVIEW_REQUEST_LIMIT')
        split = urlsplit(clean_url(url))
        origin = split.scheme + '://' + split.netloc
        if origin not in robots:
            try:
                meta, raw = bounded_get(origin + '/robots.txt')
                parser = RobotFileParser()
                parser.parse(raw.decode('utf-8', 'replace').splitlines())
                robots[origin] = parser
                path = evidence / ('robots-' + meta['sha256'] + '.txt')
                path.write_bytes(raw)
                os.chmod(path, 0o600)
            except ValueError as exc:
                if str(exc) in {'CONTACT_REVIEW_REQUEST_LIMIT',
                                'CONTACT_REVIEW_COLLECTION_DEADLINE'}:
                    raise
                robots[origin] = None if str(exc) in {'HTTP_404', 'HTTP_410'} else False
            except OSError:
                robots[origin] = False
        policy = robots[origin]
        if policy is False or (policy and not policy.can_fetch('MoneyMachine-EvidenceReview', url)):
            raise ValueError('ACCESS_RESTRICTED_OR_ROBOTS_UNAVAILABLE')
        if require_attempt and remaining() <= 0:
            raise ValueError('CONTACT_REVIEW_REQUEST_LIMIT')

    def fetch(url):
        return bounded_get(url, page=True)

    pages, errors = crawler_cls(evidence, max_pages=config['max_pages'],
                               max_requests=config['max_requests'],
                               fetcher=fetch).crawl(business['public_website'])
    collection_finished = time.monotonic()
    domains = sorted({observation['email'].rsplit('@', 1)[-1]
                      for page in pages for observation in page['observations']
                      if not observation['syntax_error']})[:config['max_dns_domains']]
    dns = dns_cls(dns_cache_path or evidence / 'dns.json')
    dns_deadline = collection_finished + config.get('dns_timeout_seconds', 15)
    if deadline is not None:
        dns_deadline = min(dns_deadline, deadline)
    dns_results = {}
    for domain in domains:
        if time.monotonic() >= dns_deadline:
            errors.append({'stage': 'dns', 'reason': 'CONTACT_REVIEW_DNS_DEADLINE'})
            break
        kwargs = {'deadline': dns_deadline} if _supports(dns.check, 'deadline') else {}
        dns_results[domain] = dns.check(domain, **kwargs)
    finished = time.monotonic()
    meta = [{key: page[key] for key in (
        'url', 'requested_url', 'captured_at', 'sha256', 'path', 'content_type', 'redirects')
             if key in page} for page in pages]
    document = {'business': business, 'pages': meta, 'dns': dns_results,
                'errors': errors,
                'stage_timings': {'collection_seconds': round(collection_finished - started, 6),
                                  'dns_seconds': round(finished - collection_finished, 6),
                                  'total_seconds': round(finished - started, 6)},
                'request_metrics': {'actual_requests': actual,
                                    'reserved_requests': reserved,
                                    'accounting': 'attempt_callbacks' if instrumented else 'legacy_conservative'}}
    _save(folder / 'COLLECTION.json', {
        **document, 'public_fetch_calls': calls,
        'request_budget': {'limit': limit, 'consumed_or_reserved': actual + reserved,
                           'remaining': remaining()},
    })
    return folder, document, 'PUBLIC_GET_DNS'
