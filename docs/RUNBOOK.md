---
name: dlq-triage
description: Procedures for dead-letter queue item triage and mitigation.
metadata:
  type: reference
---


# Dead-Letter Queue (DLQ) Triage
When `mm health` reports dead_letter_count > 0:
1.  **Identify:** Run `./mm dead-letter` to list items.
2.  **Analyze:** Examine `state/errors.jsonl` and `worker-logs/` for the `business_id` in question.
3.  **Triage:**
    *   **Transient:** If network/temporary, use `./mm pipeline-enqueue` to retry.
    *   **Malformed:** If input URL/data is corrupted, move to `data-quarantine` via `./mm data-quarantine`.
    *   **Bug:** If reproducible code fault, report in GitHub.
4.  **Clear:** Once resolved or quarantined, clear the DLQ status for the item.

# Host Acceptance Evidence Gathering

Before merging to master, verify host compatibility and baseline integrity:

1. **Doctor/Integrity:**
   - `./mm doctor --profile research-only` (Verify DB, models disabled, tools)
   - `./mm health` (Verify queue, pipeline health)

2. **Full Baseline Suite:**
   - `.venv/bin/pytest toolkit_tests -q`
   - `.venv/bin/pytest money-machine/test_acceptance.py -q`
   - `WA_BROWSER_E2E=1 .venv/bin/pytest toolkit_tests/test_browser_e2e.py -q`

3. **Discovery & Search (if SearXNG is configured):**
   - Verify SearXNG is running at `http://127.0.0.1:8888`
   - `./mm discover-search --query "..." --region "..." --endpoint "http://127.0.0.1:8888"`

4. **Obsidian Sync:**
   - `./mm obsidian-status` (Verify vault connectivity)

Capture all outputs to `reports/host-evidence-YYYY-MM-DD.json` or equivalent.
