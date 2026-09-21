#!/bin/bash
# FCC All-in-One Launcher
# Starts FCC desktop (GUI), FCC server (headless), and bridges Claude + Codex CLIs
#
# This is the master script for running all FCC-related services together.
#
# Usage: ./scripts/launch-fcc-all.sh [command]
#   Commands: desktop, server, bridge, all (default: all)
#
# Prerequisites:
#   - Free Claude Code installed (uv tool install free-claude-code)
#   - Claude Code CLI installed (npm install -g @anthropic-ai/claude-code)
#   - Codex CLI installed (npm install -g @openai/codex)
#   - Environment files: .env and .env.fcc in project root

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Load environment
load_env() {
    log_info "Loading environment..."
    
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        set -a
        source "$PROJECT_DIR/.env"
        set +a
        log_ok "Loaded .env ($(wc -l < "$PROJECT_DIR/.env") lines)"
    fi
    
    if [[ -f "$PROJECT_DIR/.env.fcc" ]]; then
        set -a
        source "$PROJECT_DIR/.env.fcc"
        set +a
        log_ok "Loaded .env.fcc ($(wc -l < "$PROJECT_DIR/.env.fcc") lines)"
    fi
    
    # Generate auth token if not set
    export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-fcc-$(date +%s)-$$}"
    
    log_info "Environment ready"
}

# Check tools
check_tools() {
    local tools=("fcc-desktop" "claude" "codex")
    local missing=()
    
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            missing+=("$tool")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "Missing tools: ${missing[*]}"
        log_info "Install with:"
        log_info "  uv tool install free-claude-code"
        log_info "  npm install -g @anthropic-ai/claude-code @openai/codex"
    fi
}

# Start FCC Desktop (GUI)
start_desktop() {
    log_info "Starting FCC Desktop (GUI)..."
    
    # Check if already running
    if pgrep -f "fcc-desktop" &>/dev/null; then
        log_warn "FCC Desktop already running"
        return 0
    fi
    
    log_info "Launching FCC Desktop..."
    nohup "/Applications/Free Claude Code.app/Contents/MacOS/fcc-desktop" \
        > "${PROJECT_DIR}/.fcc-desktop.log" 2>&1 &
    
    log_ok "FCC Desktop started"
    log_info "Admin UI: http://${HOST:-0.0.0.0}:${PORT:-8082}/admin"
}

# Start FCC Server (headless)
start_server() {
    log_info "Starting FCC Server (headless)..."
    
    # Check if port is in use
    if lsof -i ":${PORT:-8082}" &>/dev/null; then
        log_warn "Port ${PORT:-8082} already in use"
        log_info "FCC Desktop may be using this port"
        return 1
    fi
    
    nohup fcc-server > "${PROJECT_DIR}/.fcc-server.log" 2>&1 &
    log_ok "FCC Server started"
}

# Start bridge services
start_bridge() {
    log_info "Bridge services available:"
    log_info "  Claude CLI: $(which claude 2>/dev/null || echo 'not in PATH')"
    log_info "  Codex CLI:  $(which codex 2>/dev/null || echo 'not in PATH')"
    log_info "  FCC CLI:    fcc-claude, fcc-codex, fcc-server"
    log_ok "Bridge CLIs ready"
}

# Show status
show_status() {
    log_info "=== FCC All-in-One Status ==="
    echo ""
    
    # Processes
    echo -n "FCC Desktop: "
    if pgrep -f "fcc-desktop" &>/dev/null; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${YELLOW}Not running${NC}"
    fi
    
    echo -n "FCC Server: "
    if pgrep -f "fcc-server" &>/dev/null; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${YELLOW}Not running${NC}"
    fi
    
    echo -n "FCC API: "
    if curl -s "http://${HOST:-0.0.0.0}:${PORT:-8082}/admin/api/status" &>/dev/null; then
        echo -e "${GREEN}Accessible${NC}"
    else
        echo -e "${YELLOW}Not accessible${NC}"
    fi
    
    echo ""
}

# Main
COMMAND="${1:-all}"

load_env

case "$COMMAND" in
    desktop)
        start_desktop
        ;;
    server)
        start_server
        ;;
    bridge)
        start_bridge
        ;;
    status)
        show_status
        ;;
    all)
        log_info "=== Starting FCC All-in-One ==="
        check_tools
        start_desktop
        start_server || true
        start_bridge
        echo ""
        show_status
        ;;
    *)
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  desktop  - Start FCC Desktop (GUI)"
        echo "  server   - Start FCC Server (headless)"
        echo "  bridge   - Show bridge CLI info"
        echo "  status   - Show current status"
        echo "  all      - Start everything (default)"
        exit 1
        ;;
esac
