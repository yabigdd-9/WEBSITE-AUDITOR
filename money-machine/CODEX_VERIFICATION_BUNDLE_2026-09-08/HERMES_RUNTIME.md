# Hermes Runtime
**Generated:** 2026-09-07T19:03:40.127357+00:00

## Executable
- **Path:** /Users/yabigdd/.local/bin/hermes
- **Version:** v0.21.0 (2026.8.31)
- **Install directory:** /Users/yabigdd/.hermes/hermes-agent
- **Install method:** git
- **Python environment:** /Users/yabigdd/.hermes/hermes-agent/venv/bin/python (Python 3.14.7)

## Active Processes
| PID | Process | Role |
|-----|---------|------|
| 71234 | /Applications/Hermes.app/Contents/MacOS/Hermes | Main Hermes desktop app |
| 71264 | Hermes Helper (Renderer) | UI renderer |
| 71243 | Hermes Helper (GPU) | GPU process |
| 71288 | Hermes Helper (Audio) | Audio service |
| 71244 | Hermes Helper (Network) | Network service |
| 71196 | python -m hermes_cli.main gateway run --external-supervisor | Gateway supervisor |
| 71194 | python -m hermes_cli.stderr_timestamp | Error log timestamp |
| 71274 | python -m hermes_cli.main serve --host 127.0.0.1 --port 0 | Local serve |
| 79284 | hermes_kernel_runner.py | Kernel runner (session) |
| 78719 | hermes_kernel_runner.py | Kernel runner (session) |
| 78654 | hermes_kernel_runner.py | Kernel runner (session) |
| 78194 | hermes_kernel_runner.py | Kernel runner (session) |

## Concurrency Configuration
- **max_concurrent_children:** 1
- **max_retries_per_stage:** 2
- **max_stage_repeats:** 2
- **duplicate_task_guard:** true
- **recursive_delegation_guard:** true
- **proof_required_before_complete:** true

## Retry Configuration
- **max_retries_per_stage:** 2
- **max_stage_repeats:** 2

## Timeouts
- No explicit timeout overrides in config.yaml
- Default foreground timeout: 180s (terminal), 300s (browser), 600s (max foreground)
- Background processes: notify_on_complete for bounded tasks

## Checkpoints
- **proof_required_before_complete:** true (routing.yaml)
- **duplicate_task_guard:** true
- **recursive_delegation_guard:** true

## Current Orchestration Path
- **Mode:** manual_deterministic (model_execution_enabled: false)
- **Primary orchestrator:** Hermes Agent (desktop app + gateway)
- **Active session:** meituan/longcat-2.0:free via provider nous
- **Config version:** 41
