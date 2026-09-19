# Hermes Orchestration Audit

## Architecture Decision
We implemented a **Sidecar Pattern**. The DeepSeek Harness runs as a separate process/container that communicates with the WEBSITE-AUDITOR core exclusively through the `mm_bridge.py` interface. 

## Why this design?
1.  **Isolation:** The AI cannot accidentally modify `website_auditor.py` or delete databases.
2.  **Determinism:** The core logic remains pure Python. The AI only interprets results and triggers next steps.
3.  **Recoverability:** If the Harness crashes, the State Machine (SQLite) persists. Hermes can restart the Harness and resume from the last committed state.

## Flow Verification
1.  **Discover:** Researcher finds domain -> Registers in SM (`DISCOVERED`).
2.  **Audit:** Harness calls `tool_audit_site` -> Script runs -> JSON saved -> SM updates (`AUDITED`).
3.  **Analyze:** Harness reads JSON -> Critic validates -> SM updates (`QUALIFIED`).
4.  **Remediate:** Harness calls `tool_run_remediation` -> Fixes generated -> SM updates (`DEMO_READY`).
5.  **Approve:** Gate checks all flags -> SM updates (`READY_TO_SEND`).
6.  **Send:** SMTP Client sends -> SM records (`SENT`).

## Failure Handling
- **Timeout:** If `tool_audit_site` times out, SM moves to `RETRYABLE_FAILURE`. Hermes schedules retry with exponential backoff.
- **Invalid Data:** If Critic rejects findings, SM moves to `NEEDS_REVIEW`. Human intervention required.
