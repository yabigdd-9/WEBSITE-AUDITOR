# Website Auditor Toolkit Validation

Validation date: 2026-09-21 NZT.

## Passing checks

- Focused source tests: `7 passed in 4.46s`
  - Log: `/Users/dd/Documents/Codex/2026-09-20/https-chat-qwen-ai-s-69ae734d-2/work/toolkit-tests-restored-final.log`
- Focused lint: `All checks passed`
  - Log: `/Users/dd/Documents/Codex/2026-09-20/https-chat-qwen-ai-s-69ae734d-2/work/ruff-toolkit-restored-final.log`
- Model integrity:
  - Path: `/Users/dd/llama-2-7b-chat.Q4_K_M.gguf`
  - Size: `4081004224`
  - SHA-256: `08a5566d61d7cb6b420c3e4387a39e0078e1f2fe5f055f3a03887385304d4bfa`
  - Log: `/Users/dd/Documents/Codex/2026-09-20/https-chat-qwen-ai-s-69ae734d-2/work/doctor-restored-final.log`

## Generated artifacts

- Complete mocked fixture:
  - Run ID: `20260920T160129-ebcadf1adc40`
  - Status: `complete`
  - Health score: `32`
  - Severity score: `68`
  - Defect count: `8`
  - Latest copy: `/Users/dd/Documents/Codex/2026-09-20/https-chat-qwen-ai-s-69ae734d-2/outputs/complete-fixture-latest`
- No-network DNS sample:
  - Run ID: `20260920T155833-9a1e2757db89`
  - Status: `partial`
  - Fetch check: `error`
  - Health score: `null`
  - This confirms missing network/DNS cannot become a healthy result.

## Residual limits

- Full legacy test suite is not green in this sandbox. The latest run had `229 passed`, `2 skipped`, and `4 failed`; the failures were two legacy `mm_operator.py` subprocess timeouts and two pipeline-loop tests depending on `/Users/dd/agent-trials/hermes/database/money_machine.db`.
- Browser/PDF end-to-end work still needs a non-sandboxed local macOS run. In this sandbox, Chromium launch failures are surfaced instead of converted into success.
- Real llama.cpp generation was not accepted as passing because CPU generation timed out in the earlier smoke. The model file itself is verified, and deterministic fallback drafts pass.

