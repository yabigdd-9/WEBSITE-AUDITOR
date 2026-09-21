#!/bin/bash
# FCC Bridge - Links FCC-server with Claude CLI and Codex
# This script starts FCC in server mode and bridges it to Claude/Codex CLIs
#
# Usage: ./scripts/fcc-bridge.sh [command]
#   Commands: claude, codex, all (default: all)
#
# Environment: source .env and .env.fcc before running

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check dependencies
check_deps() {
    local missing=()
    
    if ! command -v fcc-server &>/dev/null; then
        missing+=("fcc-server")
    fi
    if ! command -v claude &>/dev/null; then
        missing+=("claude")
    fi
    if [[ "$1" == "codex" || "$1" == "all" ]]; then
        if ! command -v codex &>/dev/null; then
            missing+=("codex")
        fi
    fi
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing dependencies: ${missing[*]}"
        log_info "Install with: uv tool install free-claude-code && npm install -g @anthropic-ai/claude-code && npm install -g @openai/codex"
        exit 1
    fi
}

# Load environment
load_env() {
    log_info "Loading environment from .env and .env.fcc..."
    
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        set -a
        source "$PROJECT_DIR/.env"
        set +a
        log_ok "Loaded .env"
    else
        log_warn ".env not found at $PROJECT_DIR/.env"
    fi
    
    if [[ -f "$PROJECT_DIR/.env.fcc" ]]; then
        set -a
        source "$PROJECT_DIR/.env.fcc"
        set +a
        log_ok "Loaded .env.fcc"
    else
        log_warn ".env.fcc not found at $PROJECT_DIR/.env.fcc"
    fi
    
    # Ensure required vars
    export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-fcc-$(date +%s)}"
    export HOST="${HOST:-0.0.0.0}"
    export PORT="${PORT:-8082}"
}

# Kill existing processes
cleanup() {
    log_info "Cleaning up existing processes..."
    pkill -f "fcc-server" 2>/dev/null || true
    pkill -f "fcc-desktop" 2>/dev/null || true
    sleep 1
}

# Start FCC server
start_fcc_server() {
    log_info "Starting FCC server on ${HOST}:${PORT}..."
    
    # Check if port is already in use
    if lsof -i ":${PORT}" &>/dev/null; then
        log_warn "Port ${PORT} is already in use"
        log_info "FCC desktop may already be running. Use fcc-desktop for GUI mode."
        return 1
    fi
    
    # Start FCC server in background
    nohup fcc-server > "${PROJECT_DIR}/.fcc-server.log" 2>&1 &
    FCC_PID=$!
    echo $FCC_PID > "${PROJECT_DIR}/.fcc-server.pid"
    
    # Wait for server to start
    log_info "Waiting for FCC server to start..."
    local retries=30
    while [[ $retries -gt 0 ]]; do
        if curl -s "http://${HOST}:${PORT}/admin/api/status" &>/dev/null; then
            log_ok "FCC server started (PID: $FCC_PID)"
            return 0
        fi
        sleep 1
        ((retries--))
    done
    
    log_error "FCC server failed to start within 30 seconds"
    return 1
}

# Start Claude CLI bridge
start_claude() {
    log_info "Claude CLI is available at: $(which claude)"
    log_info "Usage: claude -p \"your prompt here\""
    log_info "For interactive mode: claude"
    log_info ""
    log_info "Claude can use FCC's configured API keys via OpenRouter proxy."
    log_ok "Claude CLI ready"
}

# Start Codex CLI bridge  
start_codex() {
    log_info "Codex CLI is available at: $(which codex)"
    log_info "Usage: codex exec \"your prompt here\""
    log_info "For interactive mode: codex"
    log_ok "Codex CLI ready"
}

# Show status
show_status() {
    log_info "=== FCC Bridge Status ==="
    
    if [[ -f "$PROJECT_DIR/.fcc-server.pid" ]]; then
        local pid=$(cat "$PROJECT_DIR/.fcc-server.pid")
        if kill -0 "$pid" 2>/dev/null; then
            log_ok "FCC server running (PID: $pid)"
        else
            log_warn "FCC server PID file exists but process not running"
        fi
    else
        log_warn "No FCC server PID file"
    fi
    
    if curl -s "http://${HOST}:${PORT}/admin/api/status" &>/dev/null; then
        log_ok "FCC admin API accessible at http://${HOST}:${PORT}/admin"
    else
        log_warn "FCC admin API not accessible"
    fi
    
    log_info ""
    log_info "CLI tools:"
    log_info "  Claude: $(which claude 2>/dev/null || echo 'not found')"
    log_info "  Codex:  $(which codex 2>/dev/null || echo 'not found')"
    log_info "  FCC:    $(which fcc-server 2>/dev/null || echo 'not found')"
    
    log_info ""
    log_info "Admin UI: http://${HOST}:${PORT}/admin"
    log_info "API:      http://${HOST}:${PORT}/v1"
}

# Main
COMMAND="${1:-all}"

check_deps "$COMMAND"
load_env

case "$COMMAND" in
    server)
        cleanup
        start_fcc_server
        ;;
    claude)
        load_env
        start_claude
        ;;
    codex)
        load_env
        start_codex
        ;;
    status)
        show_status
        ;;
    all)
        log_info "=== Starting FCC Bridge (All Services) ==="
        cleanup
        
        # Start FCC server
        if start_fcc_server; then
            log_ok "FCC server is running"
        else
            log_warn "FCC server not started (desktop may be running)"
        fi
        
        # Show Claude/Codex availability
        start_claude
        start_codex
        
        # Show status
        echo ""
        show_status
        ;;
    *)
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  server   - Start FCC server only"
        echo "  claude   - Show Claude CLI info"
        echo "  codex    - Show Codex CLI info"
        echo "  all      - Start everything (default)"
        echo "  status   - Show current status"
        exit 1
        ;;
esac
