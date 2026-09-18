"""Evidence-first email attribution. Pure deterministic decisions; no model calls.

VERIFIED_HIGH means supported public business attribution with current MX routing.
It never promises delivery, mailbox existence, employment, or contact permission.
"""
from collections import defaultdict
import datetime as dt
import hashlib
import html
import io
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Comment
from email_validator import validate_email, EmailNotValidError
import idna
import tldextract

VERSION = 'email-v2.0.1'
UTC = dt.timezone.utc
STATES = ('OBSERVED', 'CANDIDATE', 'VERIFIED_HIGH', 'VERIFIED_MEDIUM', 'UNVERIFIED', 'REJECTED', 'SUPPRESSED')
PSL = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)
EMAIL_RE = re.compile(r"(?<![\w.!#$%&'*+/=?^`{|}~@-])[\w.!#$%&'*+/=?^`{|}~-]+@[\w.-]+(?![\w@.-])", re.UNICODE)
FREE_MAIL = {'gmail.com', 'googlemail.com', 'outlook.com', 'hotmail.com', 'hotmail.co.nz', 'live.com', 'yahoo.com', 'yahoo.co.nz', 'icloud.com', 'xtra.co.nz', 'proton.me', 'protonmail.com'}
DISPOSABLE = {'mailinator.com', 'guerrillamail.com', '10minutemail.com', 'tempmail.com', 'yopmail.com', 'sharklasers.com', 'trashmail.com', 'getnada.com'}
DISPOSABLE.update(line.strip() for line in (Path(__file__).resolve().parents[1] / 'config/disposable_email_blocklist.conf').read_text().splitlines() if line.strip() and not line.startswith('#'))

# Blocklist source metadata (auto-downloadable from upstream)
DISPOSABLE_SOURCE = {
    'source': 'https://github.com/disposable-email-domains/disposable-email-domains',
    'download_url': 'https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/main/disposable_email_blocklist.conf',
    'captured_at': '2026-09-08T05:33:00.955025+00:00',
    'sha256': 'a53449b4811524be1b506ab8ff2401ff16092720249332c76c9eb8e413c33511',
    'entries': 8740,
    'license': 'Public-domain dedication / Unlicense',
    'limitation': 'Known-domain snapshot only; no blocklist can establish that all unlisted services are permanent.',
}


def is_disposable_email(email: str) -> bool:
    """Check if an email address uses a disposable email domain.

    Checks the full domain hierarchy: if any parent domain is in the blocklist,
    the email is considered disposable. E.g., if gmail.com is blocked, then
    user@mail.gmail.com would also be flagged.
    """
    try:
        normalized, error = normalize_email(email)
        if error:
            return False
        domain = domain_name(normalized.split('@')[-1])
        if not domain:
            return False

        # Check exact domain match
        if domain.upper() in {d.upper() for d in DISPOSABLE}:
            return True

        # Check parent domains (e.g., if mail.gmail.com is used, check gmail.com)
        parts = domain.split('.')
        for i in range(1, len(parts)):
            parent = '.'.join(parts[i:])
            if parent.upper() in {d.upper() for d in DISPOSABLE}:
                return True

        return False
    except Exception:
        return False


def refresh_disposable_blocklist(force: bool = False) -> dict:
    """Attempt to refresh the disposable email blocklist from upstream source.

    Returns a dict with status info. Set force=True to bypass cache and always download.
    """
    import hashlib
    from pathlib import Path
    import json as _json

    config_path = Path(__file__).resolve().parents[1] / 'config/disposable_email_blocklist.conf'
    source_info = DISPOSABLE_SOURCE.copy()

    if not force and config_path.exists():
        existing_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
        if existing_sha == source_info['sha256']:
            source_info['fresh'] = True
            source_info['already_up_to_date'] = True
            return source_info

    try:
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = source_info['download_url']
        with urllib.request.urlopen(url, timeout=30, context=ctx) as resp:
            content = resp.read().decode('utf-8')
        new_lines = [line.strip() for line in content.splitlines()
                     if line.strip() and not line.startswith('#')]
        # Write new blocklist
        config_path.write_text('\n'.join(new_lines) + '\n')
        new_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
        source_info['fresh'] = True
        source_info['downloaded'] = True
        source_entries = len(set(line.lower() for line in new_lines))
        source_info['entries'] = source_entries
        source_info['sha256_match'] = new_sha == source_info['sha256']
        return source_info
    except Exception as e:
        source_info['error'] = str(e)
        source_info['fallback'] = True
        return source_info
THIRD_PARTY = {'yellow.co.nz', 'yellowpages.com', 'yelp.com', 'facebook.com', 'instagram.com', 'linkedin.com', 'booking.com', 'tripadvisor.com', 'fresha.com', 'trademe.co.nz', 'builderscrack.co.nz', 'companyhub.nz', 'wixsite.com'}
THIRD_PARTY.update({'finda.co.nz','neighbourly.co.nz','hotfrog.co.nz','cylex.co.nz','cybo.com','trustindex.io','birdeye.com','foursquare.com','google.com'})
VENDORS = {'wix.com', 'sentry.io', 'xero.com', 'squarespace.com', 'godaddy.com', 'mailchimp.com', 'hubspot.com'}
PLACEHOLDER = {'example.com', 'example.org', 'example.net', 'domain.com', 'yourdomain.com', 'mydomain.com', 'email.com', 'test.com'}
BAD_ROLES = {'privacy/legal', 'careers', 'accounts', 'webmaster/developer', 'third-party vendor'}
ROLE_ORDER = {'owner': 0, 'director': 0, 'sales': 1, 'company general': 2, 'office': 2, 'staff': 3, 'support': 4, 'unknown': 5}
WEIGHTS = {'first_party': 55, 'identity': 15, 'mx': 10, 'fresh': 5, 'relevant_contact': 8,
           'independent_source': 20, 'person': 10, 'smtp_non_catchall': 5, 'second_official_page': 5,
           'hunter_corroboration': 10}


def utcnow(): return dt.datetime.now(UTC).isoformat()
def hash_bytes(data): return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def age_days(stamp, at=None):
    try:
        t = dt.datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if t.tzinfo is None: t = t.replace(tzinfo=UTC)
        return ((at or dt.datetime.now(UTC)) - t).total_seconds() / 86400
    except (ValueError, TypeError, AttributeError): return float('inf')


def domain_name(value):
    host = urlsplit(value).hostname if '://' in value else value
    try: return idna.encode((host or '').strip().rstrip('.').lower(), uts46=True).decode('ascii')
    except idna.IDNAError: return ''


def root_domain(value):
    name = domain_name(value); parts = PSL(name)
    return parts.top_domain_under_public_suffix if parts.suffix else ''


def decode_obfuscation(value):
    value = html.unescape(unicodedata.normalize('NFC', value))
    value = re.sub(r'\s*(?:\[\s*at\s*\]|\(\s*at\s*\))\s*', '@', value, flags=re.I)
    return re.sub(r'\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\))\s*', '.', value, flags=re.I)


def normalize_email(raw):
    value = decode_obfuscation(raw).strip()
    try:
        result = validate_email(value, check_deliverability=False, allow_smtputf8=False)
        normalized = result.local_part + '@' + result.ascii_domain.lower()
        if not root_domain(result.ascii_domain): raise ValueError('Unknown public suffix')
        if result.ascii_domain.rsplit('.', 1)[-1] in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'css', 'js'): raise ValueError('Asset filename')
        return normalized, None
    except (EmailNotValidError, ValueError) as e:
        return value, 'Invalid syntax/domain: ' + str(e)


def normalize_name(name):
    words = re.findall(r'[a-z0-9]+', unicodedata.normalize('NFKD', name or '').casefold())
    return ' '.join(w for w in words if w not in {'limited', 'ltd', 'company', 'co', 'the', 'and'})


def name_matches(name, text):
    want = set(normalize_name(name).split()); have = set(normalize_name(text).split())
    return bool(want) and want <= have


def normalized_phone(value):
    digits=re.sub(r'\D','',value or '')
    return '0'+digits[2:] if digits.startswith('64') else digits


def logical_source_url(url):
    """Conservative publication key; raw URLs/captures are never rewritten."""
    parsed = urlsplit(url)
    return domain_name(parsed.hostname or '').removeprefix('www.') + (unquote(parsed.path).rstrip('/') or '/')


def branch_from_url(url):
    match = re.search(r'/(?:locations?|branches|(?:our-)?showrooms?)/([^/?#]+)', urlsplit(url).path, re.I)
    return normalize_name(unquote(match.group(1)).replace('-', ' ')) if match else ''


def without_addresses(text):
    return EMAIL_RE.sub(' ', decode_obfuscation(text or ''))


PERSON_ROLE_RE = re.compile(r'\b(?:owner|founder|director|manager|consultant|engineer|electrician|plumber|builder|coordinator|administrator|chief\s+\w+\s+officer|head of\s+\w+|ceo|cfo)\b', re.I)


def classify_role(address, context):
    local = address.split('@')[0].lower(); c = context.lower()
    if re.search(r'website (?:designed|developed|built|made)|web design by|powered by|software vendor|invoice platform', c): return 'third-party vendor'
    if local in ('webmaster', 'developer', 'noreply', 'no-reply', 'donotreply'): return 'webmaster/developer'
    if local in ('privacy', 'legal', 'dpo', 'abuse'): return 'privacy/legal'
    if (re.search(r'\b(?:privacy practices|data protection|data subject)\b', c)
        or re.search(r'\b(?:questions?|requests?|contact|access|correction|exercise)\b.{0,160}\b(?:privacy policy|personal information|personal data|privacy rights)\b', c)
        or re.search(r'\b(?:personal information|personal data|privacy rights)\b.{0,120}\b(?:request|correct|access)\w*\b', c)):
        return 'privacy/legal'
    if local in ('jobs', 'careers', 'recruitment', 'hr'): return 'careers'
    if local in ('accounts', 'accounting', 'invoices', 'billing'): return 'accounts'
    if re.search(r'\b(?:owner|founder)\b', c): return 'owner'
    if re.search(r'\bdirector\b', c): return 'director'
    if local in ('sales', 'quotes', 'quote', 'enquiries', 'enquiry'): return 'sales'
    if local in ('office', 'admin', 'reception'): return 'office'
    if local in ('info', 'hello', 'contact', 'yes', 'design'): return 'company general'
    if local in ('support', 'help', 'service'): return 'support'
    if re.search(r'\b(?:email|e-mail|contact|mail|call|enquir|team|phone)\b', c): return 'company general'
    return 'unknown'


def surrounding(node):
    """Use nearest local block; avoid attributing a whole footer's vendor credit."""
    parent = node if getattr(node, 'name', None) in ('p', 'li', 'address', 'td') else node.parent
    text = parent.get_text(' ', strip=True) if parent else str(node)
    if len(text) < 25 and parent and parent.parent:
        larger = parent.parent.get_text(' ', strip=True)
        if len(larger) < 500: text = larger
    return text[:700]

def person_surrounding(node):
    """Use nearest local block; avoid attributing a whole footer's vendor credit."""
    parent = node if getattr(node, 'name', None) in ('p', 'li', 'address', 'td') else node.parent
    text = parent.get_text(' ', strip=True) if parent else str(node)
    # Image links may be nested deeply; never borrow a neighbouring person's name.
    for _ in range(6):
        if len(text) >= 25 or not parent or not parent.parent: break
        larger = parent.parent
        if larger.name in ('body', 'html', 'main', 'nav', 'header', 'footer'): break
        mailboxes = {a['href'].lower() for a in larger.select('a[href^="mailto:"]')}
        candidate_text = larger.get_text(' ', strip=True)
        if len(mailboxes) > 1 or len(candidate_text) > 700: break
        parent = larger; text = candidate_text
    return text[:700]


def unit_scope(node, url):
    """Capture one local branch block, excluding navigation and mixed lists."""
    if node is not None:
        parent = node if getattr(node, 'name', None) else node.parent
        for _ in range(8):
            if not parent or parent.name in ('body', 'html', 'main', 'nav', 'header', 'footer'): break
            text = parent.get_text(' ', strip=True)
            if len(text) > 1500: break
            branches = {branch_from_url(a['href']) for a in parent.select('a[href]') if branch_from_url(a['href'])}
            if len(branches) == 1 and len(text) > 70 and (parent.find(re.compile('^h[1-6]$')) or re.search(r'\b(?:office|branch|showroom|street|road|lane)\b', text, re.I)):
                return {'kind': 'branch_block', 'branch': next(iter(branches)), 'text': text}
            if len(branches) > 1: break
            parent = parent.parent
    branch = branch_from_url(url)
    return {'kind': 'page_branch' if branch else 'unscoped', 'branch': branch, 'text': ''}


def observation_matches_unit(observation, identity):
    scope = observation.get('unit_scope', {})
    if not identity.get('branch_sensitive'): return True
    if scope.get('kind') == 'branch_block' and any(name_matches(target, scope.get('text', '')) for target in identity.get('unit_targets', []) if target): return True
    return bool(scope.get('branch') and scope['branch'] in identity.get('matched_branches', []))


def parse_page(meta, raw):
    if hash_bytes(raw) != meta['sha256']: raise ValueError('Page capture hash mismatch')
    result = {**meta, 'observations': [], 'organization_names': [], 'social_links': [], 'phones': [], 'headings': [], 'contact_forms': [], 'links': []}
    is_pdf = 'pdf' in meta.get('content_type', '')
    if is_pdf:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        if len(reader.pages) > 12: raise ValueError('PDF exceeds 12-page limit')
        text = '\n'.join(p.extract_text() or '' for p in reader.pages)
        soup = BeautifulSoup('<pre>' + html.escape(text) + '</pre>', 'html.parser')
    else: soup = BeautifulSoup(raw, 'html.parser')
    result['title'] = soup.title.get_text(' ', strip=True) if soup.title else meta.get('title', '')
    result['headings'] = [h.get_text(' ', strip=True) for h in soup.select('h1,h2,h3,h4')][:60]
    structured = []
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            def visit(obj):
                if isinstance(obj, list):
                    for x in obj: visit(x)
                elif isinstance(obj, dict):
                    types = obj.get('@type', []); types = [types] if isinstance(types, str) else types
                    if any(t in ('Organization', 'LocalBusiness', 'HomeAndConstructionBusiness', 'HVACBusiness', 'Electrician', 'Plumber') for t in types):
                        if isinstance(obj.get('name'), str): result['organization_names'].append(obj['name'])
                        if isinstance(obj.get('email'), str): structured.append((obj['email'].removeprefix('mailto:'), json.dumps({k:obj[k] for k in ('name','email','telephone') if k in obj})))
                    for v in obj.values():
                        if isinstance(v, (dict, list)): visit(v)
            visit(json.loads(node.get_text()))
        except (ValueError, TypeError, RecursionError): pass
    for node in soup(['script', 'style', 'noscript', 'svg', 'template']): node.decompose()
    for node in soup.select('[hidden],[aria-hidden="true"],input,textarea'):
        node.decompose()
    text = soup.get_text(' ', strip=True); result['text'] = text
    result['phones'] = list(dict.fromkeys(re.findall(r'(?:\+64|0)[\d ()-]{7,18}\d', text)))[:15]
    for a in soup.select('a[href]'):
        href = a['href']
        if href.startswith(('https://', 'http://')) and root_domain(href) in {'facebook.com', 'instagram.com', 'linkedin.com'}: result['social_links'].append(href.split('?')[0])
        result['links'].append({'href': href, 'text': a.get_text(' ', strip=True)[:100]})
    if soup.find('form'): result['contact_forms'].append(meta['url'])

    def add(raw_email, method, context, original=None, node=None):
        normalized, error = normalize_email(raw_email)
        result['observations'].append({'email': normalized, 'observed_email': original or raw_email,
             'syntax_error': error, 'method': method, 'source_url': meta['url'], 'title': result['title'],
             'context': context[:700], 'person_context': person_surrounding(node) if node is not None else context[:700], 'observed_at': meta['captured_at'], 'capture_path': meta.get('path'),
             'capture_hash': meta['sha256'], 'role': classify_role(normalized, context), 'unit_scope': unit_scope(node, meta['url'])})
    for a in soup.select('a[href]'):
        if a['href'].lower().startswith('mailto:'):
            address = unquote(a['href'][7:].split('?')[0])
            # Malformed lists are observations, not silently accepted single mailboxes.
            add(address, 'mailto', surrounding(a), a['href'], a)
    for a in soup.select('[data-cfemail]'):
        try:
            encoded = bytes.fromhex(a['data-cfemail']); decoded = bytes(x ^ encoded[0] for x in encoded[1:]).decode('utf-8')
            add(decoded, 'cloudflare_obfuscation', surrounding(a), a['data-cfemail'], a)
        except (ValueError, UnicodeError, IndexError): pass
    for node in soup.find_all(string=True):
        if isinstance(node, Comment) or not node.strip() or node.parent.name in ('title',): continue
        decoded = decode_obfuscation(str(node))
        for match in EMAIL_RE.finditer(decoded):
            add(match.group().rstrip('.'), 'pdf_text' if is_pdf else 'obfuscated_text' if decoded != str(node) else 'visible_text', surrounding(node), str(node).strip()[:700], node)
    for addr, context in structured: add(addr, 'structured_data', context)
    return result


def identify(business, pages):
    requested = business.get('public_website') or business.get('website_url') or ''
    root = root_domain(requested)
    # Only the requested domain or its actual recorded redirect destination can
    # supply identity. A caller-supplied directory page cannot nominate itself.
    eligible_pages = []
    for p in pages:
        origin = root_domain(p.get('requested_url', p['url']))
        if origin == root and root: eligible_pages.append(p)
    destinations = {root_domain(p['url']) for p in eligible_pages}
    dest = root_domain(eligible_pages[0]['url']) if eligible_pages else root
    names = [business.get('name', ''), business.get('trading_name', ''), business.get('legal_name', '')]
    prominent = ' '.join(p['title'] + ' ' + ' '.join(p['headings']) + ' ' + ' '.join(p['organization_names']) for p in eligible_pages)
    body = ' '.join(p['text'] for p in eligible_pages)
    brand = any(name_matches(n, prominent) for n in names if n)
    body_name = any(name_matches(n, body) for n in names if n)
    region = bool(business.get('region')) and name_matches(business['region'], body)
    phones=[number for p in eligible_pages for number in p['phones']]
    phone = bool(business.get('phone')) and normalized_phone(business['phone']) in {normalized_phone(n) for n in phones}
    phone_conflict=bool(business.get('phone') and phones and not phone)
    address = bool(business.get('address')) and name_matches(business['address'], body)
    structured_name = any(name_matches(n, ' '.join(p['organization_names'])) for n in names if n for p in eligible_pages)
    branches = {re.search(r'/(?:our-)?showrooms?/([^/]+)', urlsplit(p['url']).path).group(1)
                for p in eligible_pages if re.search(r'/(?:our-)?showrooms?/([^/]+)', urlsplit(p['url']).path)}
    branch_ambiguous = len(branches) > 1 and not business.get('branch')
    unit_targets = [business.get(k, '') for k in ('branch', 'region', 'address') if business.get(k)]
    scopes = [o.get('unit_scope', {}) for p in eligible_pages for o in p['observations']]
    all_branches = {branch_from_url(p['url']) for p in eligible_pages} | {o.get('branch', '') for o in scopes}
    all_branches.discard('')
    matched_branches = {b for b in all_branches if any(name_matches(target, b) for target in unit_targets)}
    matched_branches.update(o['branch'] for o in scopes if o.get('kind') == 'branch_block'
                            and any(name_matches(target, o.get('text', '')) for target in unit_targets))
    location_conflict = bool(business.get('region')) and not region and bool(re.search(r'\b(?:auckland|wellington|christchurch|lower hutt|upper hutt|hamilton|dunedin)\b', body, re.I))
    parked = bool(re.search(r'this domain is (?:for sale|parked)|buy this domain|domain expired|account suspended|website coming soon', body, re.I))
    directory_page=bool(re.search(r'claim this business|add your business|business directory|business listings|claim (?:this|your) listing',body,re.I))
    blocked_domain = dest in THIRD_PARTY or dest in VENDORS or not dest or directory_page
    # Multiple signal types: prominent name + location/phone/address/structured data.
    high = bool(brand and body_name and (region or phone or address or structured_name) and not parked and not blocked_domain and len(destinations) == 1 and not branch_ambiguous and not location_conflict and not phone_conflict)
    reasons = []
    if not brand: reasons.append('Business name not confirmed in title/headings/organization')
    if not body_name: reasons.append('Business name not confirmed in visible page text')
    if not (region or phone or address or structured_name): reasons.append('Location/phone/address/structured corroboration missing')
    if parked: reasons.append('Parked/expired/placeholder domain')
    if blocked_domain: reasons.append('Third-party or unrecognized domain')
    if len(destinations) > 1: reasons.append('Conflicting destinations')
    if branch_ambiguous: reasons.append('Multiple branches: exact branch association requires review')
    if location_conflict: reasons.append('Recorded region conflicts with site location evidence')
    if phone_conflict: reasons.append('Recorded phone conflicts with site contact numbers; possible name collision')
    if dest != root and not high: reasons.append('Redirect identity mismatch')
    return {'canonical_business_name': business.get('name'), 'trading_name': business.get('trading_name'),
            'legal_name': business.get('legal_name'), 'website_url_discovered': requested,
            'canonical_root_domain': dest if high else None, 'proposed_root_domain': dest,
            'redirected_destination': eligible_pages[0]['url'] if eligible_pages else None,
            'page_titles': [p['title'] for p in eligible_pages], 'organization_names': sorted({n for p in eligible_pages for n in p['organization_names']}),
            'physical_location': business.get('address') or business.get('region'), 'phone': business.get('phone'),
            'observed_phones': sorted({n for p in eligible_pages for n in p['phones']}),
            'social_links': sorted({n for p in eligible_pages for n in p['social_links']}),
            'evidence_urls': sorted({p['url'] for p in eligible_pages}), 'checked_at': max((p['captured_at'] for p in eligible_pages), default=None),
            'page_evidence': [{'url':p['url'],'capture_path':p.get('path'),'capture_hash':p['sha256'],'captured_at':p['captured_at']} for p in eligible_pages],
            'status': 'HIGH' if high else 'REJECTED' if parked or blocked_domain or (dest != root) else 'AMBIGUOUS',
            'signals': {'prominent_name': brand, 'body_name': body_name, 'region': region, 'phone': phone, 'address': address, 'structured_name': structured_name},
            'reasons': reasons, 'accepted_roots': sorted({dest, root}) if high else [],
            'branch_sensitive': bool(all_branches), 'observed_branches': sorted(all_branches),
            'matched_branches': sorted(matched_branches), 'unit_targets': unit_targets,
            'entity_key': hash_bytes(normalize_name(business.get('name')) + '|' + (dest or '') + '|' + normalize_name(business.get('region')))}


def verification(candidate, identity, dns=None, smtp=None, suppressed=False, person=None, at=None):
    """Hard gates dominate score. SMTP is never required or sufficient evidence."""
    dns = dns or {}; smtp = smtp or {}; obs = candidate.get('observations', [])
    email, syntax_error = normalize_email(candidate['email']); domain = domain_name(email.split('@')[-1]); email_root = root_domain(domain)
    direct = [o for o in obs if o.get('method') in ('mailto', 'visible_text', 'obfuscated_text', 'cloudflare_obfuscation', 'structured_data', 'pdf_text')
              and not o.get('syntax_error') and normalize_email(o['email'])[0] == email
              and o['source_url'] in identity['evidence_urls'] and root_domain(o['source_url']) in identity['accepted_roots']
              and o.get('capture_hash') and o.get('capture_path')]
    recent = [o for o in direct if 0 <= age_days(o['observed_at'], at) <= 7]
    unit_recent = [o for o in recent if observation_matches_unit(o, identity)]
    unit_match = identity['status'] == 'HIGH' and bool(unit_recent)
    wrong_branch = bool(recent and not unit_recent and all(o.get('unit_scope', {}).get('branch') for o in recent))
    scoring_observations = unit_recent if identity.get('branch_sensitive') else recent
    role = min((o['role'] for o in scoring_observations or direct or obs), key=lambda x: ROLE_ORDER.get(x, 99), default=classify_role(email, ''))
    context = ' '.join(o.get('context', '') for o in direct or obs)
    vendor = domain in VENDORS or email_root in VENDORS or any(o.get('role') == 'third-party vendor' for o in obs)
    disposable = is_disposable_email(email) or (email_root in DISPOSABLE)
    freemail = domain in FREE_MAIL
    match = email_root in identity['accepted_roots'] if email_root else False
    person_evidence = [o for o in scoring_observations if person
                       and name_matches(person.get('name', ''), without_addresses(o.get('person_context', o['context'])))
                       and PERSON_ROLE_RE.search(without_addresses(o.get('person_context', o['context'])))
                       and (not person.get('role') or name_matches(person['role'], without_addresses(o.get('person_context', o['context']))))]
    person_ok = bool(person_evidence)
    former = bool(re.search(r'former employee|no longer (?:works|owns)|left the company|ex-employee', context, re.I))
    pattern = candidate.get('method') == 'CANDIDATE_PATTERN_DERIVED'
    mx = dns.get('mx_present') is True and dns.get('domain_accepts_mail') is True and bool(dns.get('mx_hosts'))
    dns_fresh = 0 <= age_days(dns.get('checked_at'), at) <= 1
    smtp_fresh = 0 <= age_days(smtp.get('checked_at'), at) <= 1
    smtp_status = smtp.get('result', 'not_probed') if smtp_fresh else 'not_probed'
    catch_all = smtp.get('catch_all_status', 'unknown') if smtp_fresh else 'unknown'
    hard = []
    if syntax_error: hard.append(syntax_error)
    if domain in PLACEHOLDER or email.split('@')[0].lower() in ('example', 'yourname', 'username'): hard.append('Placeholder/template address')
    if disposable: hard.append('Disposable domain')
    if vendor: hard.append('Developer/vendor context')
    if role in BAD_ROLES: hard.append('Mailbox role unsuitable for general business outreach: ' + role)
    if wrong_branch: hard.append('First-party address belongs to a different or unconfirmed business branch')
    if identity['status'] == 'REJECTED': hard.extend(identity['reasons'])
    if identity['status'] == 'HIGH' and not match and not freemail: hard.append('Canonical business-domain mismatch')
    if obs and not direct and any(root_domain(o['source_url']) != identity['proposed_root_domain'] or root_domain(o['source_url']) in THIRD_PARTY for o in obs): hard.append('Third-party-only address evidence')
    if dns_fresh and (dns.get('domain_resolves') is False or dns.get('domain_accepts_mail') is False): hard.append('No valid mail routing: ' + dns.get('status', 'rejected'))
    if smtp_status == 'rejected': hard.append('SMTP hard rejection')
    if former: hard.append('Former/stale person-company relationship')
    points = {}; reasons = []
    if direct: points['first_party'] = WEIGHTS['first_party']; reasons.append('Exact address observed in captured official source')
    if identity['status'] == 'HIGH': points['identity'] = WEIGHTS['identity']; reasons.append('Business/domain identity has multiple agreeing signals')
    if mx and dns_fresh: points['mx'] = WEIGHTS['mx']; reasons.append('Current routable MX records')
    if recent: points['fresh'] = WEIGHTS['fresh']
    if len({logical_source_url(o['source_url']) for o in scoring_observations}) >= 2: points['second_official_page'] = WEIGHTS['second_official_page']
    if recent and role in ROLE_ORDER and role not in ('unknown', 'support'): points['relevant_contact'] = WEIGHTS['relevant_contact']
    if person_ok: points['person'] = WEIGHTS['person']
    if smtp_status == 'accepted' and catch_all == 'no': points['smtp_non_catchall'] = WEIGHTS['smtp_non_catchall']
    # Hunter.io corroboration: external source confirms first-party observation
    if direct and candidate.get('hunter_confidence', 0) >= 70:
        points['hunter_corroboration'] = WEIGHTS['hunter_corroboration']
        reasons.append('External source (Hunter.io) corroborates with confidence ' + str(candidate.get('hunter_confidence')) + '%')
    # Copies on the same domain are not independent evidence; external listings
    # remain supporting observations and never override direct contradictions.
    if catch_all == 'yes': reasons.append('Catch-all: mailbox existence inconclusive')
    if smtp_status != 'accepted' or catch_all != 'no': reasons.append('Individual mailbox existence is not confirmed')
    score = min(100, sum(points.values()))
    label = 'VERIFIED_HIGH' if score >= 90 else 'VERIFIED_MEDIUM' if score >= 75 else 'UNVERIFIED'
    if pattern and not recent: label = 'CANDIDATE'; score = min(49, score); reasons.append('Pattern candidate only; no observed evidence')
    elif not recent or not mx or not dns_fresh or identity['status'] != 'HIGH': label = 'UNVERIFIED'; score = min(74, score)
    if freemail and len({logical_source_url(o['source_url']) for o in scoring_observations}) < 2: label = 'VERIFIED_MEDIUM' if recent and mx and dns_fresh else 'UNVERIFIED'; score = min(89, score); reasons.append('Free-mail ownership needs multiple official publications')
    if recent and not unit_match: label = 'UNVERIFIED'; score = min(74, score); reasons.append('Address not bound to the requested business unit')
    if person and not person_ok: label = 'UNVERIFIED'; score = min(74, score); reasons.append('Named person not supported beside address')
    if hard: label = 'REJECTED'; score = 0
    if suppressed: label = 'SUPPRESSED'; score = 0; hard.append('Suppression overrides all evidence')
    return {'email': email, 'syntax_valid': not syntax_error, 'domain_resolves': dns.get('domain_resolves'),
            'mx_present': mx, 'mx_hosts': dns.get('mx_hosts', []), 'domain_accepts_mail': dns.get('domain_accepts_mail'),
            'dns_checked_at': dns.get('checked_at'), 'smtp_result': smtp_status, 'catch_all_status': catch_all,
            'mailbox_verification': 'accepted_non_catchall' if smtp_status == 'accepted' and catch_all == 'no' else 'inconclusive',
            'disposable_status': 'known_disposable' if disposable else 'not_in_local_blocklist',
            'role_account': role, 'first_party_observed': bool(direct), 'source_count': len({logical_source_url(o['source_url']) for o in obs}),
            'raw_source_url_count': len({o['source_url'] for o in obs}), 'unit_evidence_urls': sorted({o['source_url'] for o in unit_recent}),
            'independent_source_count': len({root_domain(o['source_url']) for o in direct}),
            'person_match': person_ok if person else 'not_requested', 'person': person,
            'person_company_evidence': {'name':person.get('name'),'role':person.get('role') or next((PERSON_ROLE_RE.search(without_addresses(o.get('person_context',o['context']))).group() for o in person_evidence),None),'contexts':[o.get('person_context',o['context']) for o in person_evidence],'company':identity['canonical_business_name'],'urls':[o['source_url'] for o in person_evidence],'evidence_date':max((o['observed_at'] for o in person_evidence),default=None)} if person else None,
            'business_match': unit_match, 'domain_match': match, 'free_mail': freemail,
            'freshness': 'current' if recent else 'stale' if direct and any(age_days(o['observed_at'], at) > 7 for o in direct) else 'missing_or_future', 'confidence_score': score, 'confidence_label': label,
            'rejection_reasons': list(dict.fromkeys(hard)), 'reasons': reasons, 'score_components': points,
            'evidence': obs, 'candidate_method':candidate.get('method','observed'), 'checked_at': utcnow() if at is None else at.isoformat(), 'verifier_version': VERSION}


def evaluate(business, pages, dns_results=None, smtp_results=None, legacy=None, suppressed_addresses=(), suppressed_business=False, person=None, at=None, hunter_data=None):
    identity = identify(business, pages); groups = defaultdict(list)
    for p in pages:
        for observation in p['observations']: groups[observation['email']].append(observation)
    for addr in legacy or []: groups.setdefault(normalize_email(addr)[0], [])
    results = []
    for addr, obs in sorted(groups.items()):
        suppressed = suppressed_business or addr.casefold() in {a.strip().casefold() for a in suppressed_addresses}
        candidate = {'email': addr, 'observations': obs, 'method': 'observed' if obs else 'legacy'}
        # Attach Hunter confidence if available
        if hunter_data and addr in hunter_data:
            candidate['hunter_confidence'] = hunter_data[addr]
            candidate['hunter_sources'] = hunter_data.get(addr + '_sources', [])
        results.append(verification(candidate, identity,
                       (dns_results or {}).get(domain_name(addr.split('@')[-1])), (smtp_results or {}).get(addr), suppressed, person, at))
    high = [x for x in results if x['confidence_label'] == 'VERIFIED_HIGH']
    high.sort(key=lambda x: (ROLE_ORDER.get(x['role_account'], 99), -x['confidence_score'], x['email']))
    selected = high[0] if high else None
    return {'business_id': business.get('id'), 'business': business['name'], 'website': business.get('public_website'),
            'identity': identity, 'results': results, 'selected': selected,
            'selection_status': 'VERIFIED_HIGH' if selected else 'NO_VERIFIED_EMAIL',
            'contact_form_urls': sorted({u for p in pages if p['url'] in identity['evidence_urls'] for u in p['contact_forms']}),
            'email_review_required': True, 'human_review': 'Human relevance, permission and exact-item approval still required',
            'external_sends': 0, 'model_calls': 0, 'verifier_version': VERSION}


def pattern_candidates(identity, person, observed_emails=(), pages=()):
    if identity['status'] != 'HIGH' or not person.get('name') or not person.get('evidence_url') or not (0 <= age_days(person.get('evidence_date')) <= 7): return []
    supporting=[p for p in pages if p['url']==person['evidence_url'] and p['url'] in identity['evidence_urls']
                and 0 <= age_days(p['captured_at']) <= 7 and name_matches(person['name'],without_addresses(p['text']))
                and person.get('role') and name_matches(person['role'],without_addresses(p['text']))
                and not re.search(r'former employee|left the company|no longer works',p['text'],re.I)]
    if not supporting:return []
    parts = normalize_name(person['name']).split()
    if len(parts) < 2: return []
    domain = identity['canonical_root_domain']
    # Candidate generation is opt-in and entirely separate from observation.
    return [{'email': parts[0] + '.' + parts[-1] + '@' + domain, 'method': 'CANDIDATE_PATTERN_DERIVED',
             'status': 'CANDIDATE', 'observations': [], 'person': person,
             'known_pattern_observed': any('.' in e.split('@')[0] and e.endswith('@' + domain) for e in observed_emails)}]
