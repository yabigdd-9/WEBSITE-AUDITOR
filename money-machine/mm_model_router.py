"""Zero-cost model routing for the Money Machine.

Policy (master plan, non-negotiable): NZD 0 paid-model/API default.
Preference order:
  1. deterministic code where AI is unnecessary   (call sites decide this)
  2. local models (Ollama / llama.cpp server on this host)
  3. genuinely free external routes (:free ids on openrouter / nous)
  4. fail / retry / defer (BlockedCost) if no free route is available

Never silently fall back to a paid model or API. Every route decision is
recorded in mm_model_invocations (cost_usd is constrained to 0 by schema).
"""
import datetime as dt
import json
import os
import urllib.request

from mm_core import now, sha
from mm_pipeline import BlockedCost

PURPOSE_ROUTES = {
    # role -> ordered candidate routes (local first, then free external)
    'orchestrator':    [('local:llamacpp', None), ('local:ollama', None), ('openrouter', 'meituan/longcat-2.0:free')],
    'researcher':      [('local:llamacpp', None), ('local:ollama', None), ('openrouter', 'upstage/solar-pro4:free'),
                        ('openrouter', 'stepfun/step-3.7-flash:free')],
    'executor_sales':  [('local:llamacpp', None), ('local:ollama', None), ('openrouter', 'tencent/hy3:free')],
    'executor_content':[('local:llamacpp', None), ('local:ollama', None), ('openrouter', 'stepfun/step-3.7-flash:free')],
    'coder':           [('local:llamacpp', None), ('local:ollama', None), ('openrouter', 'poolside/laguna-s-2.1:free')],
    'lightweight_worker': [('local:llamacpp', None), ('local:ollama', None), ('openrouter', 'poolside/laguna-xs-2.1:free')],
    'judge':           [('local:llamacpp', None), ('local:ollama', None), ('openrouter', 'tencent/hy3:free')],
    'proofer':         [('local:llamacpp', None), ('local:ollama', None), ('openrouter', 'upstage/solar-pro4:free')],
}

# Local, zero-cost, no-API-key inference endpoints on this machine.
# llama.cpp's llama-server exposes an OpenAI-compatible /v1/models surface;
# Ollama exposes /api/tags. Neither bills, so they are preferred over any
# external route and can never silently become a paid call.
LLAMACPP_BASE = os.environ.get('MM_LLAMACPP_HOST', 'http://127.0.0.1:8080')
OLLAMA_BASE = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')
LOCAL_MODEL_ENV = 'MM_LOCAL_MODEL'  # exact model id, e.g. qwen3:4b or a GGUF ref


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


def _get_json(url, timeout=3):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:
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


def probe_ollama(model=None, timeout=3):
    want = model or os.environ.get(LOCAL_MODEL_ENV)
    try:
        tags = _get_json(OLLAMA_BASE.rstrip('/') + '/api/tags', timeout)
        models = [m.get('name') for m in tags.get('models', []) if m.get('name')]
    except Exception:
        return None
    if want:
        return want if want in models else None
    return models[0] if models else None


LOCAL_PROBES = {'local:llamacpp': probe_llamacpp, 'local:ollama': probe_ollama}


def probe_local(kind):
    """Return an available model id for a local kind ('llamacpp'|'ollama')."""
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


def routes_report():
    """Static report of configured routes for observability (no probing)."""
    return {purpose: [{'provider': p, 'model': m} for p, m in routes]
            for purpose, routes in PURPOSE_ROUTES.items()}


def local_complete(prompt, purpose='lightweight_worker', max_tokens=64,
                   timeout=120, lookup=None):
    """Run one bounded completion on the local zero-cost endpoint.

    Returns dict with text, provider, model, timing and cost_usd=0. Raises
    BlockedCost when no local route is available — this function can never
    reach a paid provider, because only local endpoints are addressed.
    """
    lookup = probe_local if lookup is None else lookup
    kind = 'llamacpp' if lookup('llamacpp') else ('ollama' if lookup('ollama') else None)
    if not kind:
        raise BlockedCost('no local inference route available; deferred, no paid fallback')
    model = lookup(kind)
    if kind == 'llamacpp':
        url = LLAMACPP_BASE.rstrip('/') + '/v1/chat/completions'
        body = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': max_tokens, 'temperature': 0, 'stream': False}
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        started = dt.datetime.now(dt.timezone.utc)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode())
        elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
        text = (payload.get('choices') or [{}])[0].get('message', {}).get('content', '')
        return {'text': text, 'provider': 'local:llamacpp', 'model': model,
                'elapsed_s': round(elapsed, 3), 'cost_usd': 0,
                'base_url': LLAMACPP_BASE}
    url = OLLAMA_BASE.rstrip('/') + '/api/generate'
    body = {'model': model, 'prompt': prompt, 'stream': False,
            'options': {'temperature': 0, 'num_predict': max_tokens}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    started = dt.datetime.now(dt.timezone.utc)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode())
    elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
    return {'text': payload.get('response', ''), 'provider': 'local:ollama',
            'model': model, 'elapsed_s': round(elapsed, 3), 'cost_usd': 0,
            'base_url': OLLAMA_BASE}
