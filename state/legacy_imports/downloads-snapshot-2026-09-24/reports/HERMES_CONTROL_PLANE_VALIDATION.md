# WEBSITES/BUISNESSaudits — Hermes validation

Status: PARTIAL. Capability detection PASS. Inference smoke BLOCKED_COST; not executed.

The installed CLI is Hermes 0.21.2 (2026.9.11). Help exposes `chat`, `--query-file`, `--oneshot`, `--provider`, and `--safe-mode`. The repaired adapter invokes only version/help capability commands, captures stdout/stderr and return codes, rejects missing/empty executables or malformed interfaces, and propagates nonzero outcomes. The supported query syntax is recorded; `hermes run` is absent from the active adapter.

The smoke entrypoint returns machine-readable BLOCKED_COST with smoke_executed=false and exit 2. Ollama has no installed model. No configured external provider was certified zero-cost and isolated from tools. No provider keys were read for inference, no model was downloaded, and no fallback was attempted. A working model runner remains unimplemented until this prerequisite is met.

Missing executable, nonzero/provider-unavailable response and malformed help are tested with mocks. Free-role router tests cover bounded free-route policy independently; passing them does not authorize a live provider call. Malformed evidence, judge rejection and approval bypass are separately tested in the deterministic workflow.

Delegator → executor → judge → proofer passes for the two file-only pilot packets. These are structured deterministic stages, not autonomous Hermes agents or independent humans. All stages carry status, summary, evidence, risks and next action. The model-powered chain remains BLOCKED with the inference smoke.

Evidence: hermes-probe.json, hermes-smoke.json, environment.json, test-summary.json and pilot packet stages. Rollback: reverse the repair patch; original scripts are in the preflight archive and Git baseline.

Evidence is in the sibling outputs/evidence directory. All times in evidence are UTC; this run occurred 13 September 2026 in Pacific/Auckland.
