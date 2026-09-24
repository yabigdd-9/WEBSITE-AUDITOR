"""Local integration inventory. Health probes never reveal credentials."""
from __future__ import annotations

import json
import os
import socket
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from integrations.security import redact


def _tcp(url: str, timeout: float = 0.5) -> tuple[str, str | None]:
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(url)
        with socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or (443 if parsed.scheme == "https" else 80)), timeout):
            return "healthy", None
    except OSError as exc:
        return "unavailable", type(exc).__name__


def _http(url: str, path: str = "/", timeout: float = 0.75) -> tuple[str, str | None]:
    try:
        with urlopen(Request(url.rstrip("/") + path, headers={"Accept": "application/json"}), timeout=timeout) as response:
            return ("healthy" if response.status < 500 else "degraded"), None
    except Exception as exc:
        return "unavailable", type(exc).__name__


def _loopback_http(url: str, path: str, timeout: float = 0.75) -> tuple[str, str | None]:
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        return "blocked_non_loopback", "non_loopback_endpoint"
    return _http(url, path, timeout)


def _http_details(url: str, paths: tuple[str, ...]) -> tuple[str, str | None, str | None, list[str]]:
    """Probe only an explicitly configured loopback OmniRoute endpoint."""
    from urllib.parse import urlsplit, urlunsplit
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        return "blocked_non_loopback", "non_loopback_endpoint", None, []
    base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    last_error = None
    for path in paths:
        try:
            with urlopen(Request(base + path, headers={"Accept": "application/json"}), timeout=0.75) as response:
                data = json.loads(response.read(64_000))
                caps = data.get("capabilities", []) if isinstance(data, dict) else []
                if isinstance(caps, dict):
                    caps = [key for key, enabled in caps.items() if enabled]
                a2a = bool(data.get("a2a") or data.get("a2a_enabled") or "a2a" in caps) if isinstance(data, dict) else False
                protocol = "a2a" if a2a else "http"
                return ("healthy" if response.status < 500 else "degraded", None, protocol, ["a2a"] if a2a else [])
        except Exception as exc:
            last_error = type(exc).__name__
    return "unavailable", last_error, "http", []


def _omniroute_feature_status(url: str, path: str) -> tuple[str, str | None, dict | None]:
    """Read an installed OmniRoute loopback status endpoint using its CLI auth."""
    from urllib.parse import urlsplit, urlunsplit
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        return "blocked_non_loopback", "non_loopback_endpoint", None
    try:
        # Reuse the installed CLI's supported machine-derived auth provider; never
        # return or log the credential itself.
        from pathlib import Path
        import shutil
        binary = shutil.which("omniroute")
        if not binary:
            return "not_configured", None, None
        cli_root = next((parent / "bin" / "cli" / "utils" / "cliToken.mjs"
                         for parent in Path(binary).resolve().parents
                         if (parent / "bin" / "cli" / "utils" / "cliToken.mjs").is_file()), None)
        if cli_root is None:
            return "unknown", "local_auth_provider_missing", None
        # Node is used only as the package's documented local token provider;
        # keeping token generation in OmniRoute avoids duplicating auth logic.
        helper = "const {getCliToken} = await import(process.argv[1]); process.stdout.write(await getCliToken())"
        result = subprocess.run([shutil.which("node") or "node", "--input-type=module", "-e", helper, cli_root.as_uri()],
                                capture_output=True, text=True, timeout=1, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return "unknown", "local_auth_unavailable", None
        token = result.stdout.strip()
        base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
        request = Request(base + path, headers={"Accept": "application/json", "x-omniroute-cli-token": token})
        with urlopen(request, timeout=0.75) as response:
            data = json.loads(response.read(64_000))
    except HTTPError as exc:
        return ("disabled" if exc.code == 404 else "unknown"), (None if exc.code == 404 else f"HTTP{exc.code}"), None
    except Exception as exc:
        return "unknown", type(exc).__name__, None
    if not isinstance(data, dict):
        return "unknown", "invalid_status_response", None
    enabled = data.get("enabled", data.get("running", data.get("online")))
    running = data.get("online", data.get("running", enabled))
    reported = str(data.get("status", "")).lower()
    if reported in {"disabled", "offline", "running", "online", "healthy"}:
        running = reported in {"running", "online", "healthy"}
        if reported == "disabled":
            enabled = False
    health = "healthy" if running is True else "disabled" if enabled is False else "offline" if running is False else "unknown"
    return health, None, data


def _command(name: str) -> tuple[str, str | None]:
    import shutil
    return ("installed", None) if shutil.which(name) else ("not_configured", None)


def integrations_status() -> dict:
    root = os.environ.get("MM_ROOT", "")
    fcc = os.environ.get("FCC_BASE_URL", "http://127.0.0.1:8082")
    ollama = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    # The installed local OmniRoute config was discovered to point at port 20128.
    # Honor an explicit override, otherwise probe only this verified loopback default.
    omni = os.environ.get("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128")
    hook = os.environ.get("MM_WEBHOOK_BASE_URL", "http://127.0.0.1:8093")
    a2a_gateway = os.environ.get("MM_A2A_GATEWAY_BASE_URL", "http://127.0.0.1:8094")
    checks = [
        ("Hermes", None, "local CLI", "Cline delegation and MCP client", lambda: _command("hermes")),
        ("Cline", None, "local CLI", "local coding agent", lambda: _command("cline")),
        ("OpenCode", None, "local CLI", "local coding agent", lambda: _command("opencode")),
        ("OmniRoute", omni or None, "http", "model router; MCP/A2A status probed from installed CLI", lambda: _http_details(omni, ("/api/health",))[:2] if omni else ("not_configured", None)),
        ("FCC", fcc, "http", "Claude/Codex compatibility proxy", lambda: _tcp(fcc)),
        ("Ollama", ollama, "http", "local OpenAI-compatible models", lambda: _tcp(ollama)),
        ("GitHub MCP", "github-mcp-server", "stdio", "official GitHub MCP; read-only mode in project examples", lambda: _command("github-mcp-server")),
        ("Obsidian MCP", os.environ.get("OBSIDIAN_MCP_URL", "http://127.0.0.1:8765/mcp"), "streamable-http", "Vault as MCP plugin; selected vault", lambda: _tcp(os.environ.get("OBSIDIAN_MCP_URL", "http://127.0.0.1:8765/mcp"))),
        ("WEBSITE-AUDITOR MCP", "stdio", "stdio", "bounded first-party server available; client connection not asserted", lambda: ("available", None)),
        ("Webhook receiver", hook, "http", "loopback event receiver", lambda: _tcp(hook)),
        ("WEBSITE-AUDITOR A2A gateway", a2a_gateway, "A2A JSON-RPC", "repo-owned role gateway; free-role router only", lambda: _loopback_http(a2a_gateway, "/health")),
    ]
    items = []
    for name, endpoint, protocol, capability, probe in checks:
        health, error = probe()
        items.append({"name": name, "endpoint": endpoint, "protocol": protocol,
                      "capability": capability, "health": health, "last_error": error,
                      "safety": {"paid_allowed": False, "max_cost_usd": 0, "send_enabled": False}})
    omni_status = next((item for item in items if item["name"] == "OmniRoute"), None)
    obsidian_item = next((item for item in items if item["name"] == "Obsidian MCP"), None)
    if obsidian_item:
        obsidian_item["vault_id"] = os.environ.get("OBSIDIAN_VAULT_ID", "b5d58a08e16fab4e")
    if omni and omni_status:
        health, error, protocol, capabilities = _http_details(omni, ("/api/health",))
        omni_status.update(health=health, last_error=error, protocol=protocol or "http", capabilities=capabilities)
        for feature, path in (("OmniRoute MCP", "/api/mcp/status"), ("OmniRoute A2A", "/api/a2a/status")):
            health, error, details = _omniroute_feature_status(omni, path)
            enabled = bool(details and details.get("enabled", details.get("running", details.get("online", False))))
            item = {"name": feature, "endpoint": "OmniRoute local runtime", "protocol": (details or {}).get("transport") or "local status API",
                    "capability": "installed server capability; no client connection asserted", "health": health,
                    "last_error": error,
                    "safety": {"paid_allowed": False, "max_cost_usd": 0, "send_enabled": False}}
            if feature.endswith("A2A"):
                item["capabilities"] = ["a2a"] if enabled else []
            items.append(item)
    return redact({"generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                   "integrations": items, "routing": {"primary": "OmniRoute when configured", "compatibility": "FCC", "local": "Ollama",
                   "paid_allowed": False, "max_cost_usd": 0, "fallback": "DEFER"},
                   "repository_configured": True})


def format_integrations_status(status: dict) -> str:
    """Render the redacted integration registry for an operator terminal."""
    lines = ["Integration status"]
    generated = status.get("generated_at")
    if generated:
        lines.append(f"Generated: {generated}")
    for item in status.get("integrations", []):
        endpoint = item.get("endpoint") or "local"
        lines.append(f"\n{item.get('name', 'Unknown')}: {str(item.get('health', 'unknown')).upper()}")
        lines.append(f"  Protocol: {item.get('protocol', 'unknown')} | Endpoint: {endpoint}")
        if item.get("capability"):
            lines.append(f"  Capability: {item['capability']}")
        if item.get("last_error"):
            lines.append(f"  Last error: {item['last_error']}")
        if item.get("capabilities"):
            lines.append(f"  Confirmed capabilities: {', '.join(item['capabilities'])}")
        safety = item.get("safety", {})
        if safety:
            lines.append(
                "  Safety: paid_allowed={paid}; max_cost_usd={cost}; send_enabled={send}".format(
                    paid=safety.get("paid_allowed", "unknown"),
                    cost=safety.get("max_cost_usd", "unknown"),
                    send=safety.get("send_enabled", "unknown"),
                )
            )
    routing = status.get("routing", {})
    if routing:
        lines.extend([
            "\nRouting",
            f"  Primary: {routing.get('primary', 'unknown')} | Compatibility: {routing.get('compatibility', 'unknown')} | Local: {routing.get('local', 'unknown')}",
            f"  Safety: paid_allowed={routing.get('paid_allowed', 'unknown')}; max_cost_usd={routing.get('max_cost_usd', 'unknown')}; fallback={routing.get('fallback', 'unknown')}",
        ])
    return "\n".join(lines)
