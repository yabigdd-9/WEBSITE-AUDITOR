# WEBSITES/BUISNESSaudits — compatibility entrypoint

The current operator is the root `mm`; see [current README](../README.md) and [current state](../reports/CURRENT_STATE.md). The instructions below are historical and may reference the original layout.

# MoneyMachine

A local, evidence-based operator. It does not send messages or call models.

From this directory:

- `./mm run-day` — current human queue, evidence gaps and real money status.
- `./mm money` — one next revenue action.
- `./mm learn` — actual-outcome readout; no invented winners.
- `./mm price --problem lead_capture` — transparent scope and cost scenarios.
- `./mm doctor` — tool presence, empty stubs and database health.
- `.venv-email/bin/python scripts/email_acceptance.py` — regression, shadow accuracy and rollback checks on disposable copies.
- `./mm backup` — checksummed backup; use before maintenance.

Start with `reports/CODEX_EMAIL_FINDER_BASELINE_2026-09-08.md` and `reports/EMAIL_FINDER_ACCEPTANCE_RESULTS.md`.

Email V2 prioritizes evidence and precision. `./mm email-status 5` explains the selected address, identity, MX, confidence and sources. `./mm email-find ID` performs one bounded public-site/DNS check; it never changes CRM stages or sends anything. `./mm email-shadow` replays the frozen 18-business benchmark. `./mm email-v1 ID` displays historical claims as unverified; `./mm email-rollback` retains all evidence and holds new approvals. Setup and full rollback instructions are in `reports/EMAIL_FINDER_V2_IMPLEMENTATION.md`.

`VERIFIED_HIGH` means supported public business attribution with current mail routing. SMTP/catch-all status remains unknown unless evidence says otherwise; public attribution does not prove delivery or contact permission. Guesses and medium-confidence records cannot enter the ready/approval/send workflow.

The source of truth is `database/money_machine.db`. Receipt imports require a human-reviewed evidence envelope and an unchanged local artifact. They are attestations, not independent bank or mail-provider verification. Never manufacture them. Approval and send recording are separate commands; neither sends anything. Exact content, recipient and proposal price must remain unchanged.

Heat Force and Evoke's previous packets are invalidated pending requalification. ATL Heat Pumps, Christchurch Renovations and Butterfield Bathrooms remain suppressed. Model execution and automatic fallback remain disabled for MoneyMachine.
