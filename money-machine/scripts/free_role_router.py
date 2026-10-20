"""Explicit free-only model requests. No CRM connection, tool execution or outreach."""
import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "money-machine") not in sys.path:
    sys.path.insert(0, str(ROOT / "money-machine"))
import mm_financial_admission as admission  # noqa: E402

API = "https://openrouter.ai/api/v1"


class RouteError(RuntimeError):
    def __init__(self, message, attempts=None):
        super().__init__(message)
        self.attempts = attempts or []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Provider redirects are disabled", headers, fp)


def _http_request(path, key=None, payload=None):
    headers = {"Accept": "application/json", "User-Agent": "MoneyMachine-role-router"}
    if key:
        headers["Authorization"] = "Bearer " + key
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(req, timeout=100) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("Provider response exceeds the supported bound")
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as error:
        body = error.read(16384)
        try:
            data = json.loads(body)
        except ValueError:
            data = {"error": {"message": "Non-JSON upstream error"}}
        return error.code, data


def _admitted_request(path, key, payload, transport):
    try:
        if path != "/chat/completions" or not isinstance(payload, dict):
            raise admission.AdmissionError("Unsupported inference operation")
        return admission.get_coordinator().execute(
            "openrouter", payload.get("model"), API + path, payload.get("max_tokens"),
            lambda: transport(path, key, payload))
    except admission.AdmissionError as exc:
        raise RouteError("Shared financial admission refused: " + str(exc)) from exc
    except (OSError, ValueError, TypeError) as exc:
        raise RouteError("Uncertain provider dispatch; fallback stopped for accounting review") from exc


def request(path, key=None, payload=None):
    """Public transport: inference admission also applies to direct callers."""
    if payload is not None:
        return _admitted_request(path, key, payload, _http_request)
    try:
        admission.get_coordinator().require_provider("openrouter")
    except admission.AdmissionError as exc:
        raise RouteError("External provider metadata disabled without account evidence") from exc
    if path != "/models":
        raise RouteError("Unsupported provider metadata operation")
    return _http_request(path, key)


def _env_file_value(path, name):
    """Read one simple KEY=VALUE entry without requiring python-dotenv."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if not sep or key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        return value or None
    return None


def credential():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    key = _env_file_value(Path.home() / ".hermes/.env", "OPENROUTER_API_KEY")
    if key:
        return key
    path = Path.home() / ".hermes/auth.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    for entry in data.get("credential_pool", {}).get("openrouter", []):
        if entry.get("auth_type") == "api_key" and not entry.get("disabled") and entry.get("access_token"):
            return entry["access_token"]
    raise RouteError("OpenRouter credential missing; connect using Hermes model/setup")


def free_model(model):
    prices = model.get("pricing", {})
    try:
        return (model.get("id", "").endswith(":free")
            and all(k in prices for k in ("prompt", "completion"))
            and all(Decimal(str(v)) == 0 for v in prices.values()))
    except (InvalidOperation, TypeError):
        return False


def validate(config):
    policy = config["policy"]
    if config.get("provider") != "openrouter" or policy.get("paid_tokens") is not False:
        raise RouteError("Only OpenRouter zero-paid-token requests are permitted")
    if policy.get("require_parameters") is not True:
        raise RouteError("require_parameters must remain true")
    if policy.get("data_collection") != "deny":
        raise RouteError("Repository routing policy must default data_collection to deny")
    if policy.get("max_price") != {"prompt": 0, "completion": 0, "request": 0, "image": 0}:
        raise RouteError("All price caps must be zero")
    for role, spec in config["roles"].items():
        chain = [spec["preferred"], *spec.get("fallbacks", [])]
        if len(chain) != len(set(chain)) or not all(isinstance(m, str) and m.endswith(":free") for m in chain):
            raise RouteError("Invalid or non-free route for " + role)


def route(config, role, prompt, key, catalog, transport=_http_request, image_data=None,
          creator_model=None, allow_data_collection=False):
    validate(config)
    if not config.get("manual_role_requests_enabled"):
        raise RouteError("Explicit role requests are paused")
    if role not in config["roles"]:
        raise RouteError("Unknown role; no default model substitution")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 24000:
        raise RouteError("A bounded, non-empty prompt of at most 24000 characters is required")
    spec = config["roles"][role]
    chain = [spec["preferred"], *spec.get("fallbacks", [])]
    attempts = []
    for slug in chain:
        model = catalog.get(slug)
        if model is None:
            attempts.append({"model": slug, "status": "absent_from_catalog"})
            continue
        if not free_model(model):
            raise RouteError("Catalog no longer proves zero cost: " + slug, attempts)
        if image_data and "image" not in model.get("architecture", {}).get("input_modalities", []):
            attempts.append({"model": slug, "status": "image_unsupported"})
            continue
        content = prompt if image_data is None else [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data}},
        ]
        payload = {"model": slug, "messages": [{"role": "user", "content": content}],
            "max_tokens": 2048, "stream": False,
            "provider": {"require_parameters": True, "allow_fallbacks": True,
                "sort": "price",
                "data_collection": "allow" if allow_data_collection else "deny",
                "max_price": {"prompt": 0, "completion": 0, "request": 0, "image": 0}}}
        try:
            code, body = _admitted_request("/chat/completions", key, payload, transport)
        except (OSError, TimeoutError) as exc:
            attempts.append({"model": slug, "status": "dispatch_outcome_unknown"})
            raise RouteError("Uncertain provider dispatch; fallback stopped for accounting review", attempts) from exc
        error = body.get("error") or {}
        meta = error.get("metadata") or {} if isinstance(error, dict) else {}
        if code == 429 and (meta.get("limit_source") == "openrouter_free_tier_daily"
                or "free-models-per-day" in str(error)):
            attempts.append({"model": slug, "status": "account_daily_quota", "http_status": code,
                "reset_unix_ms": meta.get("headers", {}).get("X-RateLimit-Reset")})
            raise RouteError("Daily free quota exhausted; wait for reset, never purchase credits automatically", attempts)
        if code in (401, 402):
            attempts.append({"model": slug, "status": "authentication_or_billing_block", "http_status": code})
            raise RouteError("Authentication/billing block; no fallback or paid request made", attempts)
        if code != 200 or error:
            attempts.append({"model": slug, "status": "endpoint_unavailable", "http_status": code})
            continue
        usage = body.get("usage") or {}
        cost = usage.get("cost")
        if cost is None or isinstance(cost, bool) or Decimal(str(cost)) != 0:
            raise RouteError("Unexpected reported cost; stop all requests and investigate", attempts)
        choice = (body.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip() or choice.get("finish_reason") == "length":
            attempts.append({"model": slug, "status": "empty_or_truncated_answer"})
            continue
        actual = body.get("model", slug)
        if actual.removesuffix(":free") != slug.removesuffix(":free"):
            raise RouteError("Unexpected response model; do not silently accept another route", attempts)
        attempts.append({"model": slug, "status": "response", "http_status": code})
        return {"role": role, "requested_model": slug, "actual_model": actual,
            "answer": content, "usage": {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "cost")},
            "attempts": attempts, "fallback_used": slug != chain[0], "response_id": body.get("id"),
            "independent_review": None if role not in ("JUDGE", "CRITIC") or not creator_model else
                actual.removesuffix(":free") != creator_model.removesuffix(":free"),
            "approval_granted": False, "external_send_performed": False}
    raise RouteError("All permitted free routes unavailable; stopped", attempts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--image", type=Path, help="Synthetic/public PNG or JPEG only")
    parser.add_argument("--creator-model", help="For JUDGE/CRITIC independent-review checks")
    parser.add_argument("--public-or-synthetic", action="store_true",
        help="Explicitly allow data-collecting free endpoints for public/synthetic prompts")
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / "money-machine/config/routing.yaml").read_text())
    prompt = args.prompt_file.read_text()
    image_data = None
    if args.image:
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(args.image.suffix.lower())
        if mime is None or args.image.stat().st_size > 2 * 1024 * 1024:
            parser.error("Image must be PNG/JPEG, at most 2 MB")
        image_data = "data:" + mime + ";base64," + base64.b64encode(args.image.read_bytes()).decode()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    log = {"at": stamp, "role": args.role, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
    try:
        validate(config)
        status, catalog = request("/models")
        if status != 200:
            raise RouteError("Cannot verify live catalog; no model request made")
        result = route(config, args.role, prompt, credential(), {m["id"]: m for m in catalog["data"]},
            image_data=image_data, creator_model=args.creator_model,
            allow_data_collection=args.public_or_synthetic)
        log.update({k: v for k, v in result.items() if k != "answer"}, status="response")
        print(json.dumps(result, indent=2))
        exit_code = 0
    except (RouteError, OSError) as error:
        log.update(status="blocked", reason=str(error), attempts=getattr(error, "attempts", []))
        print(json.dumps(log, indent=2))
        exit_code = 2
    folder = ROOT / "logs/free-role-routing"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (stamp + ".json")).open("x") as stream:
        json.dump(log, stream, indent=2)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
