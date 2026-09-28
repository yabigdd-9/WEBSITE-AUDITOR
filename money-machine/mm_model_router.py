"""Zero-cost inference routing for the Money Machine.

Active order:
  1. Claude through the loopback FCC harness.
  2. Hermes free-role router.
  3. DEFER when neither route is demonstrably zero-cost.

llama.cpp and Ollama are intentionally excluded from the active Money Machine
routing path. The machine never upgrades itself to a paid Claude/provider route.
"""
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

import yaml

from mm_core import now, sha
from mm_pipeline import BlockedCost
from mm_redaction import prepare_prompt

FCC_PROVIDER = "gateway:fcc-claude"
HERMES_PROVIDER = "hermes:free-role"

FCC_BASE = os.environ.get("MM_FCC_BASE", "http://127.0.0.1:8082")
FCC_MODEL_ENV = "MM_FCC_MODEL"
FCC_FREE_MODELS_ENV = "MM_FCC_FREE_MODELS"

ROOT = Path(__file__).resolve().parents[1]
HERMES_ROUTING_CONFIG = ROOT / "money-machine" / "config" / "routing.yaml"
HERMES_FREE_ROUTER = ROOT / "money-machine" / "scripts" / "free_role_router.py"
FCC_ENV_FILES = (ROOT / ".env.fcc", ROOT / ".env")


def _env_value(name, default=""):
    value = os.environ.get(name)
    if value is not None:
        return value
    for path in FCC_ENV_FILES:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw = stripped.split("=", 1)
            if key.strip() == name:
                return raw.strip().strip('"').strip("'")
    return default

PURPOSE_ROLE = {
    "orchestrator": "MASTER_ORCHESTRATOR",
    "researcher": "RESEARCHER",
    "executor_sales": "FAST_RESEARCHER",
    "executor_content": "RESEARCHER",
    "coder": "CODER",
    "lightweight_worker": "FAST_RESEARCHER",
    "judge": "JUDGE",
    "proofer": "CRITIC",
    "vision": "VISION",
}

PURPOSE_ROUTES = {
    purpose: [(FCC_PROVIDER, None), (HERMES_PROVIDER, None)]
    for purpose in PURPOSE_ROLE
}


class PaidRouteRefused(Exception):
    """A route that could bill was requested. Always a hard error."""


def _loopback_url(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if host == "localhost":
        host = "127.0.0.1"
    try:
        address = ipaddress.ip_address(host)
        valid = address.is_loopback and parsed.port != 0
    except ValueError:
        valid = False
    if (
        not valid
        or parsed.scheme not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise BlockedCost("FCC harness requires a loopback HTTP(S) endpoint")
    authority = "[" + host + "]" if ":" in host else host
    if parsed.port is not None:
        authority += ":" + str(parsed.port)
    return urlunsplit((parsed.scheme, authority, parsed.path, "", ""))


class LocalRedirectRefused(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BlockedCost("FCC harness redirects are disabled")


def _open_local(request, timeout):
    request.full_url = _loopback_url(request.full_url)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), LocalRedirectRefused()
    )
    return opener.open(request, timeout=timeout)


def _fcc_free_allowlist():
    return {
        item.strip()
        for item in _env_value(FCC_FREE_MODELS_ENV, "").split(",")
        if item.strip()
    }


def _fcc_model_allowed(model):
    if not isinstance(model, str) or not model:
        return False
    # FCC may expose model IDs without a :free suffix. Such a Claude route is
    # permitted only when the operator explicitly certifies that exact model ID
    # in MM_FCC_FREE_MODELS. "auto" is never trusted as zero-cost.
    return model.endswith(":free") or model in _fcc_free_allowlist()


def _fcc_request(url, data=None):
    headers = {"Content-Type": "application/json"}
    token = _env_value("ANTHROPIC_AUTH_TOKEN").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    return urllib.request.Request(url, data=data, headers=headers)


def probe_fcc(model=None, timeout=3):
    """Return the configured Claude/FCC model only when it is certified free."""
    want = model or _env_value(FCC_MODEL_ENV)
    if want and not _fcc_model_allowed(want):
        return None
    try:
        req = _fcc_request(_loopback_url(FCC_BASE).rstrip("/") + "/v1/models")
        with _open_local(req, timeout) as response:
            payload = json.loads(response.read().decode())
        models = [
            item.get("id")
            for item in payload.get("data", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
    except Exception:
        return None
    if want:
        return want if want in models else None
    return next((name for name in models if _fcc_model_allowed(name)), None)


def _hermes_config():
    try:
        config = yaml.safe_load(HERMES_ROUTING_CONFIG.read_text()) or {}
    except (OSError, ValueError, TypeError):
        return None
    policy = config.get("policy") or {}
    if config.get("provider") != "openrouter":
        return None
    if policy.get("paid_tokens") is not False:
        return None
    if policy.get("max_price") != {
        "prompt": 0,
        "completion": 0,
        "request": 0,
        "image": 0,
    }:
        return None
    if config.get("manual_role_requests_enabled") is not True:
        return None
    return config


def probe_hermes(purpose="lightweight_worker"):
    """Return Hermes' configured preferred role model when it is explicit :free."""
    config = _hermes_config()
    if not config or not HERMES_FREE_ROUTER.is_file():
        return None
    role = PURPOSE_ROLE.get(purpose, "FAST_RESEARCHER")
    model = ((config.get("roles") or {}).get(role) or {}).get("preferred")
    return model if isinstance(model, str) and model.endswith(":free") else None


def probe_local(kind):
    """Compatibility probe for the two active zero-cost harness lanes."""
    if kind == "fcc":
        return probe_fcc()
    if kind == "hermes":
        return probe_hermes()
    return None


def local_model_available(model=None, timeout=3):
    """Compatibility helper: FCC first, then Hermes."""
    found = probe_fcc(model, timeout)
    if found:
        return FCC_PROVIDER, found
    found = probe_hermes()
    if found:
        return HERMES_PROVIDER, found
    return None


def check_route(provider, model):
    """Return None only for explicitly zero-cost active routes."""
    if provider == FCC_PROVIDER:
        return None if _fcc_model_allowed(model) else (
            "PAID_ROUTE_REFUSED: FCC Claude model is not explicitly certified zero-cost"
        )
    if provider == HERMES_PROVIDER:
        return None if isinstance(model, str) and model.endswith(":free") else (
            "PAID_ROUTE_REFUSED: Hermes fallback model lacks :free"
        )
    return "UNKNOWN_PROVIDER: %s not on the active harness allowlist" % provider


def _lookup_route(kind, purpose, lookup):
    if lookup is not None:
        return lookup(kind)
    if kind == "fcc":
        return probe_fcc()
    if kind == "hermes":
        return probe_hermes(purpose)
    return None


def plan(d, purpose, at=None, local_lookup=None):
    """Plan FCC-Claude first, Hermes free-role second, otherwise BLOCKED_COST."""
    tried = []
    chosen = None
    for provider, _ in PURPOSE_ROUTES.get(
        purpose, PURPOSE_ROUTES["lightweight_worker"]
    ):
        kind = "fcc" if provider == FCC_PROVIDER else "hermes"
        found = _lookup_route(kind, purpose, local_lookup)
        if not found:
            tried.append(
                {"provider": provider, "reason": "zero-cost route unavailable"}
            )
            continue
        refusal = check_route(provider, found)
        if refusal:
            tried.append({"provider": provider, "model": found, "reason": refusal})
            continue
        chosen = (provider, found)
        break

    if chosen is None:
        run = sha(now() + purpose)
        reason = (
            "BLOCKED_COST: Claude/FCC was not certified free and no Hermes "
            "zero-cost fallback was available; tried %s" % json.dumps(tried)
        )
        d.execute(
            "INSERT INTO mm_model_invocations(run_key,model,provider,"
            "purpose_hash,status,created_at,finished_at,error) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (run, "none", "none", sha(purpose), "blocked", now(), now(), reason),
        )
        return {
            "status": "blocked",
            "run_key": run,
            "reason": reason,
            "tried": tried,
            "model_calls": 0,
            "cost_usd": 0,
        }

    provider, model = chosen
    run = sha(now() + purpose + provider + model)
    d.execute(
        "INSERT INTO mm_model_invocations(run_key,model,provider,"
        "purpose_hash,status,created_at) VALUES(?,?,?,?,?,?)",
        (run, model, provider, sha(purpose), "started", now()),
    )
    return {
        "status": "planned",
        "run_key": run,
        "provider": provider,
        "model": model,
        "model_calls": 0,
        "cost_usd": 0,
    }


def finish(d, run_key, ok, error=None):
    """Mark a planned route complete/failed; failure never upgrades to paid."""
    row = d.execute(
        "SELECT * FROM mm_model_invocations WHERE run_key=?", (run_key,)
    ).fetchone()
    if not row:
        raise ValueError("Unknown run_key")
    d.execute(
        "UPDATE mm_model_invocations SET status=?,finished_at=?,error=? WHERE run_key=?",
        ("completed" if ok else "failed", now(), (error or "")[:500], run_key),
    )
    if not ok:
        raise BlockedCost(
            "route %s/%s failed: %s — no paid fallback"
            % (row["provider"], row["model"], error)
        )


def prepare_external_prompt(prompt: str) -> dict:
    """Redact external-model prompt material before FCC/Hermes use."""
    return prepare_prompt(prompt, public_only=True)


def _fcc_complete(prompt, model, max_tokens, timeout):
    if not _fcc_model_allowed(model):
        raise BlockedCost(
            "Claude/FCC model is not explicitly certified zero-cost; use Hermes fallback"
        )
    url = _loopback_url(FCC_BASE).rstrip("/") + "/v1/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    req = _fcc_request(url, json.dumps(body).encode())
    started = dt.datetime.now(dt.timezone.utc)
    try:
        with _open_local(req, timeout) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError) as exc:
        raise BlockedCost("Claude/FCC route unavailable without paid fallback") from exc
    elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
    text = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not isinstance(text, str) or not text.strip():
        raise BlockedCost("Claude/FCC returned no usable zero-cost answer")
    usage = payload.get("usage") or {}
    reported_cost = usage.get("cost")
    if reported_cost not in (None, 0, 0.0, "0", "0.0"):
        raise BlockedCost(
            "FCC reported non-zero cost; stop Claude route and use Hermes fallback"
        )
    return {
        "text": text,
        "provider": FCC_PROVIDER,
        "model": model,
        "elapsed_s": round(elapsed, 3),
        "cost_usd": 0,
        "base_url": FCC_BASE,
    }


def _hermes_complete(prompt, purpose, timeout):
    """Run the Hermes free-role dispatcher, which live-verifies catalog price=0."""
    configured = probe_hermes(purpose)
    if not configured:
        raise BlockedCost("Hermes zero-cost role fallback is not configured")
    role = PURPOSE_ROLE.get(purpose, "FAST_RESEARCHER")
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".txt", delete=False
    ) as handle:
        handle.write(prompt)
        prompt_path = handle.name
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(HERMES_FREE_ROUTER),
                "--role",
                role,
                "--prompt-file",
                prompt_path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
            env=os.environ.copy(),
        )
    finally:
        try:
            Path(prompt_path).unlink()
        except OSError:
            pass
    if result.returncode != 0:
        raise BlockedCost("Hermes free-role fallback unavailable")
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise BlockedCost("Hermes fallback returned malformed output") from exc
    model = payload.get("actual_model") or payload.get("requested_model")
    answer = payload.get("answer")
    cost = (payload.get("usage") or {}).get("cost")
    if not isinstance(model, str) or not model.endswith(":free"):
        raise BlockedCost("Hermes fallback did not prove a :free model")
    if cost not in (None, 0, 0.0, "0", "0.0"):
        raise BlockedCost("Hermes fallback reported non-zero cost")
    if not isinstance(answer, str) or not answer.strip():
        raise BlockedCost("Hermes fallback returned no usable answer")
    return {
        "text": answer.strip(),
        "provider": HERMES_PROVIDER,
        "model": model,
        "elapsed_s": None,
        "cost_usd": 0,
    }


def local_complete(
    prompt,
    purpose="lightweight_worker",
    max_tokens=64,
    timeout=120,
    lookup=None,
):
    """Execute Claude/FCC first; fall back to Hermes only if Claude is not free/usable."""
    prepared = prepare_external_prompt(prompt)
    if prepared.get("secret_detected"):
        raise BlockedCost("secret-bearing prompt is held for human review")
    safe_prompt = prepared["prompt"]

    fcc_model = _lookup_route("fcc", purpose, lookup)
    if fcc_model and check_route(FCC_PROVIDER, fcc_model) is None:
        try:
            return _fcc_complete(safe_prompt, fcc_model, max_tokens, timeout)
        except BlockedCost:
            pass

    hermes_model = _lookup_route("hermes", purpose, lookup)
    if hermes_model and check_route(HERMES_PROVIDER, hermes_model) is None:
        return _hermes_complete(safe_prompt, purpose, timeout)

    raise BlockedCost(
        "no certified zero-cost inference route available; Claude/FCC was skipped "
        "or failed and Hermes fallback was unavailable"
    )


def routes_report():
    return {
        "policy": {
            "paid_allowed": False,
            "max_cost_usd": 0,
            "primary": "CLAUDE_VIA_FCC",
            "fallback": "HERMES_VERIFIED_FREE_THEN_DEFER",
            "llamacpp_enabled": False,
            "ollama_enabled": False,
            "external_data_rule": "public/non-confidential prompts only; secrets held",
        },
        "routes": {
            purpose: [
                {"provider": FCC_PROVIDER, "model": _env_value(FCC_MODEL_ENV) or None},
                {"provider": HERMES_PROVIDER, "model": probe_hermes(purpose)},
            ]
            for purpose in PURPOSE_ROUTES
        },
    }
