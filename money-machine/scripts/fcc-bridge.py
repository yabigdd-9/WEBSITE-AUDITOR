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

import subprocess
import sys
import os
import json
import time
import signal
import urllib.request
import urllib.error
from pathlib import Path

# Configuration
PROJECT_DIR = Path(__file__).parent.parent
SCRIPT_DIR = PROJECT_DIR / "money-machine" / "scripts"
FCC_HOST = os.environ.get("HOST", "0.0.0.0")
FCC_PORT = int(os.environ.get("PORT", "8082"))
FCC_URL = f"http://{FCC_HOST}:{FCC_PORT}"
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
    """Start FCC server in headless mode"""
    log_info("Starting FCC server...")
    
    running, _ = check_process("fcc-server", "fcc-server")
    if running:
        log_warn("FCC server already running")
        return True
    
    # Check if port is in use
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((FCC_HOST, FCC_PORT))
        sock.close()
        if result == 0:
            log_warn(f"Port {FCC_PORT} already in use (FCC desktop may be running)")
            log_info("Using existing FCC desktop instance")
            return True
    except Exception:
        pass
    
    # Start FCC server
    try:
        proc = subprocess.Popen(
            ["fcc-server"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )
        
        # Wait for startup
        log_info("Waiting for FCC server to start...")
        for i in range(30):
            time.sleep(1)
            try:
                req = urllib.request.Request(f"{ADMIN_URL}/api/status")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        log_ok(f"FCC server started (PID: {proc.pid})")
                        return True
            except Exception:
                pass
        
        log_error("FCC server failed to start")
        return False
    except Exception as e:
        log_error(f"Failed to start FCC server: {e}")
        return False

def stop_fcc_server():
    """Stop FCC server"""
    log_info("Stopping FCC server...")
    running, pids = check_process("fcc-server", "fcc-server")
    if running:
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
        log_ok("FCC server stopped")
    else:
        log_warn("FCC server not running")

def check_fcc_status():
    """Check FCC admin API status"""
    try:
        req = urllib.request.Request(f"{ADMIN_URL}/api/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.load(resp)
    except Exception as e:
        log_warn(f"Cannot reach FCC admin: {e}")
        return None

def run_claude(prompt):
    """Run a prompt through Claude CLI"""
    log_info(f"Running Claude: {prompt[:50]}...")
    
    claude_path = Path("/Users/dd/.local/bin/claude")
    if not claude_path.exists():
        log_error("Claude CLI not found")
        return False
    
    try:
        result = subprocess.run(
            [str(claude_path), "-p", prompt],
            capture_output=True,
            text=True,
            timeout=300,
            env=os.environ.copy()
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log_error("Claude timed out")
        return False
    except Exception as e:
        log_error(f"Claude failed: {e}")
        return False

def run_codex(prompt):
    """Run a prompt through Codex CLI"""
    log_info(f"Running Codex: {prompt[:50]}...")
    
    codex_path = Path("/Users/dd/.local/bin/codex")
    if not codex_path.exists():
        log_error("Codex CLI not found")
        return False
    
    try:
        result = subprocess.run(
            [str(codex_path), "exec", "--no-interactive", prompt],
            capture_output=True,
            text=True,
            timeout=300,
            env=os.environ.copy()
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log_error("Codex timed out")
        return False
    except Exception as e:
        log_error(f"Codex failed: {e}")
        return False

def send_to_fcc(prompt):
    """Send a request to FCC API"""
    log_info(f"Sending to FCC: {prompt[:50]}...")
    
    try:
        # Use FCC's API to generate a response
        # This is a simplified approach - in production you'd use the proper API
        data = json.dumps({
            "model": os.environ.get("MODEL", "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,
            "temperature": 0.7,
        }).encode()
        
        req = urllib.request.Request(
            f"{API_URL}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ.get('ANTHROPIC_AUTH_TOKEN', '')}"
            },
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.load(resp)
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(content)
            return True
    except Exception as e:
        log_error(f"FCC API request failed: {e}")
        # Fall back to Claude CLI
        log_info("Falling back to Claude CLI...")
        return run_claude(prompt)

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
        start_fcc_server()
        show_status()
        
    elif command == "stop":
        stop_fcc_server()
        
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
