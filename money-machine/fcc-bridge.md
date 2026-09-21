# FCC Bridge - Free Claude Code Integration

This directory contains scripts to integrate **Free Claude Code (FCC)** with **Claude CLI** and **Codex CLI** for a unified AI coding experience.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FCC All-in-One                          │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│ FCC Desktop │ FCC Server  │  Claude CLI │   Codex CLI      │
│   (GUI)     │  (Headless) │  (Anthropic)│   (OpenAI)       │
│   Port 8082 │   Port 8082 │             │                  │
├─────────────┴─────────────┴─────────────┴──────────────────┤
│                    FCC Bridge (this project)                │
│  - Unified env loading (.env + .env.fcc)                   │
│  - Process management                                       │
│  - Status monitoring                                       │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **Free Claude Code** (FCC)
   ```bash
   uv tool install free-claude-code
   ```

2. **Claude Code CLI** (Anthropic)
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

3. **Codex CLI** (OpenAI)
   ```bash
   npm install -g @openai/codex
   ```

## Configuration

### Environment Files

- **`.env`** - Project environment variables (API keys, tokens, etc.)
- **`.env.fcc`** - FCC-specific configuration (model settings, provider keys)

Both files are automatically loaded by the bridge scripts.

### Key Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_AUTH_TOKEN` | FCC proxy auth token (auto-generated if not set) |
| `OPENROUTER_API_KEY` | OpenRouter API key (for Claude models) |
| `NVIDIA_NIM_API_KEY` | NVIDIA NIM API key (for Nemotron models) |
| `MODEL` | Default model selector |
| `HOST` | Server host (default: 0.0.0.0) |
| `PORT` | Server port (default: 8082) |

## Scripts

### `fcc-bridge.sh`
Bash script for managing FCC services.

```bash
# Start all services
./money-machine/scripts/fcc-bridge.sh all

# Start FCC server only
./money-machine/scripts/fcc-bridge.sh server

# Show Claude CLI info
./money-machine/scripts/fcc-bridge.sh claude

# Show Codex CLI info  
./money-machine/scripts/fcc-bridge.sh codex

# Show status
./money-machine/scripts/fcc-bridge.sh status
```

### `fcc-bridge.py`
Python script for advanced bridging operations.

```bash
# Start services
python money-machine/scripts/fcc-bridge.py start

# Stop services
python money-machine/scripts/fcc-bridge.py stop

# Show status
python money-machine/scripts/fcc-bridge.py status

# Run prompt through Claude CLI
python money-machine/scripts/fcc-bridge.py claude "Explain this code"

# Run prompt through Codex CLI
python money-machine/scripts/fcc-bridge.py codex "Fix this bug"

# Send request to FCC API
python money-machine/scripts/fcc-bridge.py fcc "What is Python?"
```

### `launch-fcc-all.sh`
Master launcher for all FCC services.

```bash
# Start everything
./money-machine/scripts/launch-fcc-all.sh all

# Start desktop only
./money-machine/scripts/launch-fcc-all.sh desktop

# Show status
./money-machine/scripts/launch-fcc-all.sh status
```

## Usage Examples

### Start Everything
```bash
cd /Users/dd/WEBSITE-AUDITOR
./money-machine/scripts/launch-fcc-all.sh all
```

### Use Claude CLI (bridged to FCC)
```bash
# The Claude CLI will use FCC's configured API keys
claude -p "Review this code for security issues"
```

### Use Codex CLI
```bash
codex exec "Refactor this function"
```

### Query FCC Directly
```bash
curl -X POST http://0.0.0.0:8082/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -d '{
    "model": "nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 1000
  }'
```

## Admin Interface

FCC provides a web admin interface at:
- **URL**: http://0.0.0.0:8082/admin
- **API**: http://0.0.0.0:8082/v1

The admin UI allows you to:
- Configure API keys for different providers
- Select models
- View usage statistics
- Configure proxies

## Environment Loading Order

1. `.env` (project environment)
2. `.env.fcc` (FCC-specific overrides)
3. CLI arguments / environment overrides

Later sources override earlier ones.

## Troubleshooting

### FCC not starting
```bash
# Check logs
tail -f .fcc-desktop.log
tail -f .fcc-server.log

# Check port
lsof -i :8082

# Kill existing processes
pkill -f fcc-desktop
pkill -f fcc-server
```

### CLI tools not found
```bash
# Verify installations
which claude
which codex
which fcc-server

# Reinstall if needed
uv tool install free-claude-code
npm install -g @anthropic-ai/claude-code @openai/codex
```

### API key issues
```bash
# Check configured keys in FCC admin
curl http://0.0.0.0:8082/admin/api/config | python3 -m json.tool

# Apply keys via API
curl -X POST http://0.0.0.0:8082/admin/api/config/apply \
  -H "Content-Type: application/json" \
  -d '{"OPENROUTER_API_KEY": "your-key-here"}'
```

## File Structure

```
money-machine/scripts/
├── fcc-bridge.sh      # Bash bridge controller
├── fcc-bridge.py      # Python bridge controller
├── launch-fcc-all.sh  # All-in-one launcher
└── ...
```
