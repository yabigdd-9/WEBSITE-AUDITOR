#!/usr/bin/env python3
"""
FCC Bridge - Connects FCC-server with Claude CLI and Codex CLI
Provides a unified interface for using all three AI coding tools.

Usage:
    python scripts/fcc-bridge.py [command]

Commands:
    start   - Start FCC server and bridge CLIs
    stop    - Stop all services
    status  - Show status of all services
    claude  - Run a prompt through Claude CLI
    codex   - Run a prompt through Codex CLI
    fcc     - Send a request to FCC API
"""

import ipaddress
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Configuration
PROJECT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_DIR = PROJECT_DIR / "money-machine" / "scripts"
if str(PROJECT_DIR / "money-machine") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "money-machine"))
import mm_model_router as model_router  # noqa: E402

FCC_HOST = os.environ.get("HOST", "127.0.0.1")
FCC_PORT = int(os.environ.get("PORT", "8082"))
def local_fcc_url(host, port):
    """The local bridge must never send credentials over remote HTTP."""
    if not 1 <= port <= 65535:
        raise ValueError("Invalid FCC port")
    if host == "localhost":
        address = host
    else:
        ip = ipaddress.ip_address(host)
        if not ip.is_loopback:
            raise ValueError("FCC bridge requires a loopback host")
        address = f"[{ip}]" if ip.version == 6 else str(ip)
    return f"http://{address}:{port}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "FCC redirects are disabled", headers, fp)


def open_local_request(req, timeout):
    # Bypass proxies as well as redirects: this transport is local-only.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    return opener.open(req, timeout=timeout)


FCC_URL = local_fcc_url(FCC_HOST, FCC_PORT)
ADMIN_URL = f"{FCC_URL}/admin"
API_URL = f"{FCC_URL}/v1"

# Colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"

def log_info(msg):
    print(f"{BLUE}[INFO]{NC} {msg}")

def log_ok(msg):
    print(f"{GREEN}[OK]{NC} {msg}")

def log_warn(msg):
    print(f"{YELLOW}[WARN]{NC} {msg}")

def log_error(msg):
    print(f"{RED}[ERROR]{NC} {msg}")

def load_env():
    """Load .env and .env.fcc into environment"""
    log_info("Loading environment...")

    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()
        log_ok(f"Loaded {env_file}")

    fcc_env = PROJECT_DIR / ".env.fcc"
    if fcc_env.exists():
        for line in fcc_env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()
        log_ok(f"Loaded {fcc_env}")

    # Ensure required vars
    if "ANTHROPIC_AUTH_TOKEN" not in os.environ:
        os.environ["ANTHROPIC_AUTH_TOKEN"] = f"fcc-{int(time.time())}"

    global FCC_HOST, FCC_PORT, FCC_URL, ADMIN_URL, API_URL
    FCC_HOST = os.environ.get("HOST", "127.0.0.1")
    FCC_PORT = int(os.environ.get("PORT", "8082"))
    FCC_URL = local_fcc_url(FCC_HOST, FCC_PORT)
    ADMIN_URL = f"{FCC_URL}/admin"
    API_URL = f"{FCC_URL}/v1"

    log_ok("Environment loaded")

def check_process(name, pattern):
    """Check if a process is running"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split("\n")
            return True, pids
        return False, []
    except Exception:
        return False, []

def start_fcc_server():
    """Service activation belongs to the verified supervisor rollout workflow."""
    log_error("FCC service activation held pending verified ownership and rollout authority")
    return False

def stop_fcc_server():
    """Never terminate processes identified only by a name match."""
    log_error("FCC service stop held pending verified process ownership")
    return False

def check_fcc_status():
    """Check FCC admin API status"""
    try:
        req = urllib.request.Request(f"{ADMIN_URL}/api/status")
        with open_local_request(req, timeout=5) as resp:
            return json.load(resp)
    except Exception as e:
        log_warn(f"Cannot reach FCC admin: {e}")
        return None

def run_claude(prompt):
    """Agent CLIs cannot prove a bounded included request; keep them held."""
    log_error("Claude CLI disabled: internal request count and billing are unverified")
    return False

def run_codex(prompt):
    """Do not launch an unmetered agent as a model fallback."""
    log_error("Codex CLI disabled: internal request count and billing are unverified")
    return False

def send_to_fcc(prompt):
    """Use the same admitted, redacted model operation as MoneyMachine."""
    try:
        prepared = model_router.prepare_external_prompt(prompt)
        if prepared.get("secret_detected"):
            raise model_router.BlockedCost("Secret-bearing prompt requires review")
        model = os.environ.get("MODEL") or model_router._env_value(model_router.FCC_MODEL_ENV)
        result = model_router._fcc_complete(prepared["prompt"], model, 2048, 60, base_url=FCC_URL)
        print(result["text"])
        return True
    except (model_router.BlockedCost, OSError, ValueError):
        log_error("FCC request held or failed; no CLI fallback is permitted")
        return False

def show_status():
    """Show status of all services"""
    print(f"\n{BLUE}=== FCC Bridge Status ==={NC}\n")

    # FCC status
    status = check_fcc_status()
    if status:
        print(f"{GREEN}FCC Server:{NC} Running")
        print(f"  Model: {status.get('model', '?')}")
        print(f"  Provider: {status.get('provider', '?')}")
        print(f"  Admin: {ADMIN_URL}/admin")
        print(f"  API: {API_URL}/v1")
    else:
        print(f"{YELLOW}FCC Server:{NC} Not accessible")

    print()

    # CLI tools
    tools = {
        "Claude CLI": "/Users/dd/.local/bin/claude",
        "Codex CLI": "/Users/dd/.local/bin/codex",
        "FCC-server": "fcc-server",
        "FCC-desktop": "/Applications/Free Claude Code.app/Contents/MacOS/fcc-desktop",
    }

    for name, path in tools.items():
        exists = Path(path).exists() if path.startswith("/") else True
        status_icon = f"{GREEN}✓{NC}" if exists else f"{RED}✗{NC}"
        print(f"  {status_icon} {name}: {path}")

    print()

    # Running processes
    print(f"{BLUE}Running Processes:{NC}")
    for name, pattern in [
        ("FCC-server", "fcc-server"),
        ("FCC-desktop", "fcc-desktop"),
        ("Claude", "claude"),
        ("Codex", "codex"),
    ]:
        running, pids = check_process(name, pattern)
        icon = f"{GREEN}✓{NC}" if running else f"{YELLOW}○{NC}"
        pid_info = f" (PID: {', '.join(pids[:3])})" if running and pids else ""
        print(f"  {icon} {name}{pid_info}")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    # Load environment
    load_env()

    if command == "start":
        print(f"\n{BLUE}=== Starting FCC Bridge ==={NC}\n")
        if not start_fcc_server():
            sys.exit(3)

    elif command == "stop":
        sys.exit(0 if stop_fcc_server() else 3)

    elif command == "status":
        show_status()

    elif command == "claude":
        if len(sys.argv) < 3:
            log_error("Usage: fcc-bridge.py claude <prompt>")
            sys.exit(1)
        prompt = " ".join(sys.argv[2:])
        success = run_claude(prompt)
        sys.exit(0 if success else 1)

    elif command == "codex":
        if len(sys.argv) < 3:
            log_error("Usage: fcc-bridge.py codex <prompt>")
            sys.exit(1)
        prompt = " ".join(sys.argv[2:])
        success = run_codex(prompt)
        sys.exit(0 if success else 1)

    elif command == "fcc":
        if len(sys.argv) < 3:
            log_error("Usage: fcc-bridge.py fcc <prompt>")
            sys.exit(1)
        prompt = " ".join(sys.argv[2:])
        success = send_to_fcc(prompt)
        sys.exit(0 if success else 1)

    else:
        log_error(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
