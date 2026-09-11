"""Explicit free-only model requests. No CRM connection, tool execution or outreach."""
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[2]
API = "https://openrouter.ai/api/v1"


class RouteError(RuntimeError):
    def __init__(self, message, attempts=None):
        super().__init__(message)
        self.attempts = attempts or []


def request(path, key=None, payload=None):
    headers = {"Accept": "application/json", "User-Agent": "MoneyMachine-role-router"}
    if key:
        headers["Authorization"] = "Bearer " + key
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=100) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read(16384)
        try:
            data = json.loads(body)
        except ValueError:
            data = {"error": {"message": "Non-JSON upstream error"}}
        return error.code, data


def credential():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    from dotenv import dotenv_values
    key = dotenv_values(Path.home() / ".hermes/.env").get("OPENROUTER_API_KEY")
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
    if policy.get("max_price") != {"prompt": 0, "completion": 0, "request": 0, "image": 0}:
        raise RouteError("All price caps must be zero")
    for role, spec in config["roles"].items():
        chain = [spec["preferred"], *spec.get("fallbacks", [])]
        if len(chain) != len(set(chain)) or not all(isinstance(m, str) and m.endswith(":free") for m in chain):
            raise RouteError("Invalid or non-free route for " + role)


def route(config, role, prompt, key, catalog, transport=request, image_data=None, creator_model=None):
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
                "sort": "price", "data_collection": config["policy"].get("data_collection", "allow"),
                "max_price": {"prompt": 0, "completion": 0, "request": 0, "image": 0}}}
        try:
            code, body = transport("/chat/completions", key, payload)
        except (OSError, TimeoutError):
            attempts.append({"model": slug, "status": "network_failure"})
            continue
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
        if cost is not None and Decimal(str(cost)) != 0:
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
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / "control-plane/config/routing.yaml").read_text())
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
            image_data=image_data, creator_model=args.creator_model)
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
