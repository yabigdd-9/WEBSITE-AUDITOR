"""Zero-cost model routing for the Money Machine.

Policy (master plan, non-negotiable): NZD 0 paid-model/API default.
Preference order:
  1. deterministic code where AI is unnecessary   (call sites decide this)
  2. local models (llama.cpp server on this host)
  3. genuinely free external routes (:free ids on openrouter / nous)
  4. fail / retry / defer (BlockedCost) if no free route is available

Never silently fall back to a paid model or API. Every route decision is
recorded in mm_model_invocations (cost_usd is constrained to 0 by schema).
"""
import datetime as dt
import ipaddress
import json
import os
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from mm_core import now, sha
from mm_pipeline import BlockedCost
from mm_redaction import prepare_prompt

PURPOSE_ROUTES = {
    # Live-verified free routes as of 2026-09-21; local inference always wins.
    'orchestrator': [
        ('local:llamacpp', None),
        ('openrouter', 'meituan/longcat-2.0:free'),
        ('openrouter', 'nvidia/nemotron-3-ultra-550b-a55b:free'),
    ],
    'researcher': [
        ('local:llamacpp', None),
        ('openrouter', 'thinkingmachines/inkling:free'),
        ('openrouter', 'nvidia/nemotron-3.5-lightning:free'),
    ],
    'executor_sales': [
        ('local:llamacpp', None),
        ('openrouter', 'inclusionai/ling-3.0-flash:free'),
        ('openrouter', 'meituan/longcat-2.0:free'),
    ],
    'executor_content': [
        ('local:llamacpp', None),
        ('openrouter', 'thinkingmachines/inkling:free'),
        ('openrouter', 'inclusionai/ling-3.0-flash:free'),
    ],
    'coder': [
        ('local:llamacpp', None),
        ('openrouter', 'poolside/laguna-s-2.1:free'),
        ('openrouter', 'poolside/laguna-xs-2.1:free'),
    ],
    'lightweight_worker': [
        ('local:llamacpp', None),
        ('openrouter', 'nvidia/nemotron-3.5-lightning:free'),
        ('openrouter', 'poolside/laguna-xs-2.1:free'),
    ],
    'judge': [
        ('local:llamacpp', None),
        ('openrouter', 'nvidia/nemotron-3-ultra-550b-a55b:free'),
        ('openrouter', 'meituan/longcat-2.0:free'),
    ],
    'proofer': [
        ('local:llamacpp', None),
        ('openrouter', 'nvidia/nemotron-3.5-lightning:free'),
        ('openrouter', 'inclusionai/ling-3.0-flash:free'),
    ],
    'vision': [
        ('local:llamacpp', None),
        ('openrouter', 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free'),
    ],
}


# Local, zero-cost, no-API-key inference endpoints on this machine.
# llama.cpp's llama-server exposes an OpenAI-compatible /v1/models surface;
LLAMACPP_BASE = os.environ.get('MM_LLAMACPP_HOST', 'http://127.0.0.1:8080')
LOCAL_MODEL_ENV = 'MM_LOCAL_MODEL'  # exact model id, e.g. qwen3:4b or a GGUF ref
EXTERNAL_FREE_ENV = 'MM_ALLOW_EXTERNAL_FREE_MODELS'


class PaidRouteRefused(Exception):
    """A route that could bill was requested. Always a hard error."""


def _is_free(model_id):
    """Only explicit :free external ids or local models are permitted."""
    return model_id is None or model_id.endswith(':free')


def check_route(provider, model):
    """Validate a route against the zero-cost policy. Returns reason or None."""
    if not _is_free(model):
        return 'PAID_ROUTE_REFUSED: %s has no free marker' % model
    if provider.startswith('local'):
        return None
    if provider in ('openrouter', 'nous'):
        return None
    return 'UNKNOWN_PROVIDER: %s not on the free-route allowlist' % provider


def _loopback_url(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    if host == 'localhost':
        host = '127.0.0.1'
    try:
        address = ipaddress.ip_address(host)
        valid = address.is_loopback and parsed.port != 0
    except ValueError:
        valid = False
    if (not valid or parsed.scheme not in {'http', 'https'}
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise BlockedCost('local inference requires a loopback HTTP(S) endpoint')
    authority = '[' + host + ']' if ':' in host else host
    if parsed.port is not None:
        authority += ':' + str(parsed.port)
    return urlunsplit((parsed.scheme, authority, parsed.path, '', ''))


class LocalRedirectRefused(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BlockedCost('local inference redirects are disabled')


def _open_local(request, timeout):
    request.full_url = _loopback_url(request.full_url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), LocalRedirectRefused())
    return opener.open(request, timeout=timeout)


def _get_json(url, timeout=3):
    req = urllib.request.Request(url)
    with _open_local(req, timeout) as r:
        return json.loads(r.read().decode())


def probe_llamacpp(model=None, timeout=3):
    """llama-server exposes an OpenAI-compatible /v1/models listing."""
    want = model or os.environ.get(LOCAL_MODEL_ENV)
    try:
        tags = _get_json(LLAMACPP_BASE.rstrip('/') + '/v1/models', timeout)
        models = [m.get('id') for m in tags.get('data', []) if m.get('id')]
    except Exception:
        return None
    if want:
        return want if want in models else None
    return models[0] if models else None


LOCAL_PROBES = {'local:llamacpp': probe_llamacpp}


def probe_local(kind):
    """Return an available model id for the local llama.cpp server."""
    probe = LOCAL_PROBES.get('local:' + kind)
    return probe() if probe else None


def local_model_available(model=None, timeout=3):
    """Return (provider, model) for the first available local route, else None."""
    for provider, probe in LOCAL_PROBES.items():
        found = probe(model, timeout)
        if found:
            return provider, found
    return None


def plan(d, purpose, at=None, local_lookup=None):
    """Decide the next route for a purpose. Pure decision + audit; no calls.

    `local_lookup` is injectable (defaults to the live local probe) so the
    decision can be tested without a running inference server.
    Returns dict(status=planned|blocked, provider, model, reason).
    Status is recorded in mm_model_invocations with cost_usd=0 either way.
    """
    lookup = probe_local if local_lookup is None else local_lookup
    routes = PURPOSE_ROUTES.get(purpose, PURPOSE_ROUTES['lightweight_worker'])
    tried = []
    chosen = None
    for provider, model in routes:
        refusal = check_route(provider, model)
        if refusal:
            raise PaidRouteRefused(refusal)  # config error must never route
        if provider.startswith('local'):
            kind = provider.split(':', 1)[1]
            found = lookup(kind)
            if found:
                chosen = (provider, found)
                break
            tried.append({'provider': provider, 'kind': kind,
                          'reason': 'no local model available'})
            continue
        if os.environ.get(EXTERNAL_FREE_ENV) != '1':
            tried.append({
                'provider': provider,
                'model': model,
                'reason': 'external free models disabled; set MM_ALLOW_EXTERNAL_FREE_MODELS=1 for public/non-confidential prompts',
            })
            continue
        if provider == 'openrouter' and not os.environ.get('OPENROUTER_API_KEY'):
            tried.append({'provider': provider, 'model': model,
                          'reason': 'OPENROUTER_API_KEY unset'})
            continue
        chosen = (provider, model)
        break
    if chosen is None:
        run = sha(now() + purpose)
        reason = ('BLOCKED_COST: no free route available for %s; tried %s'
                  % (purpose, json.dumps(tried)))
        d.execute("INSERT INTO mm_model_invocations(run_key,model,provider,"
                  "purpose_hash,status,created_at,finished_at,error) "
                  "VALUES(?,?,?,?,?,?,?,?)",
                  (run, 'none', 'none', sha(purpose), 'blocked', now(), now(),
                   reason))
        return {'status': 'blocked', 'run_key': run, 'reason': reason,
                'tried': tried, 'model_calls': 0, 'cost_usd': 0}
    provider, model = chosen
    run = sha(now() + purpose + provider + str(model))
    d.execute("INSERT INTO mm_model_invocations(run_key,model,provider,"
              "purpose_hash,status,created_at) VALUES(?,?,?,?,?,?)",
              (run, model, provider, sha(purpose), 'started', now()))
    return {'status': 'planned', 'run_key': run, 'provider': provider,
            'model': model, 'model_calls': 0, 'cost_usd': 0}


def finish(d, run_key, ok, error=None):
    """Mark a planned route completed/failed. Failure never retries as paid."""
    r = d.execute("SELECT * FROM mm_model_invocations WHERE run_key=?",
                  (run_key,)).fetchone()
    if not r:
        raise ValueError('Unknown run_key')
    d.execute("UPDATE mm_model_invocations SET status=?,finished_at=?,error=? "
              "WHERE run_key=?",
              ('completed' if ok else 'failed', now(), (error or '')[:500], run_key))
    if not ok:
        raise BlockedCost('route %s/%s failed: %s — deferred; no paid fallback'
                          % (r['provider'], r['model'], error))


def prepare_external_prompt(prompt: str) -> dict:
    """Prepare a redacted, zero-cost-safe prompt for an optional free route.

    This does not call a provider. The caller must still opt in to an external
    free route and preserve the returned hashes/redaction metadata.
    """
    return prepare_prompt(prompt, public_only=True)


def routes_report():
    """Static report of configured routes for observability (no probing)."""
    return {
        'policy': {
            'paid_allowed': False,
            'max_cost_usd': 0,
            'external_free_enabled': os.environ.get(EXTERNAL_FREE_ENV) == '1',
            'external_data_rule': 'public or non-confidential prompts only',
            'fallback': 'DEFER',
        },
        'routes': {
            purpose: [{'provider': p, 'model': m} for p, m in routes]
            for purpose, routes in PURPOSE_ROUTES.items()
        },
    }


def local_complete(prompt, purpose='lightweight_worker', max_tokens=64,
                   timeout=120, lookup=None):
    """Run one bounded completion on the local zero-cost endpoint.

    Returns dict with text, provider, model, timing and cost_usd=0. Raises
    BlockedCost when no local route is available — this function can never
    reach a paid provider, because only local endpoints are addressed.
    """
    lookup = probe_local if lookup is None else lookup
    kind = 'llamacpp' if lookup('llamacpp') else None
    if not kind:
        raise BlockedCost('no local inference route available; deferred, no paid fallback')
    model = lookup(kind)
    if kind == 'llamacpp':
        url = _loopback_url(LLAMACPP_BASE).rstrip('/') + '/v1/chat/completions'
        body = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': max_tokens, 'temperature': 0, 'stream': False}
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        started = dt.datetime.now(dt.timezone.utc)
        with _open_local(req, timeout) as r:
            payload = json.loads(r.read().decode())
        elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
        text = (payload.get('choices') or [{}])[0].get('message', {}).get('content', '')
        return {'text': text, 'provider': 'local:llamacpp', 'model': model,
                'elapsed_s': round(elapsed, 3), 'cost_usd': 0,
                'base_url': LLAMACPP_BASE}
