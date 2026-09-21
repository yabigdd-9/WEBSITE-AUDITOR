# WEBSITE-AUDITOR — current state

Updated: 2026-09-21  
Canonical local workspace: `/Users/dd/WEBSITE-AUDITOR`  
Canonical repository: `yabigdd-9/WEBSITE-AUDITOR`  
Baseline master inspected: `dafb280308c4686fe4018da842b2b5df59ec85fc`  
Active v32 execution branch: `execution/v32-obsidian-canonical`

## Canonical direction

The active execution specification is **WEBSITE-AUDITOR Master Merged Plan v32**.

- Python 3.11.
- Local-first and deterministic-first.
- Paid model/API usage forbidden by default: `paid_allowed=false`, `max_cost_usd=0`.
- No silent paid fallback.
- Outreach sending disabled by default.
- SQLite + state files + `./mm` remain authoritative.
- launchd / `./mm supervisor` are the intended runtime supervision layer.
- Obsidian is the human-facing master brain/operator workspace only.
- n8n is not required by the default runtime.

## Confirmed recent integration

PR #33 merged the agency revenue/monthly reporting work into master. Before merge, local validation showed:

- agency/monthly suite: 21 passed
- release suite: 16 passed
- real Chromium monthly portal E2E: 1 passed
- draft-only email delivery remained fail-closed

A fresh full repository regression/security run is still required after the v32 Obsidian changes before promotion.

## v32 execution now in progress

The isolated v32 branch adds:

- `money-machine/mm_obsidian.py`: one-way runtime → Obsidian renderer
- `./mm obsidian-sync`
- `./mm obsidian-status`
- `WEBSITE-AUDITOR-BRAIN/` vault root
- tests proving Obsidian is optional and cannot authorize sends/approvals
- `reports/V32_PHASE_AUDIT.md`
- fail-closed `money-machine/supervisor/launchd.py` + `./mm launchd install|status|uninstall`
- local-only Git ignore boundary for generated Obsidian prospect/runtime views
- unused NLTK dependency removed; core dependency declarations aligned
- tracked generated egg-info metadata removed and ignored
- dependency audit now evaluates the declared runtime requirements directly

The vault is explicitly non-authoritative. Editing Markdown cannot mutate SQLite, approve outreach, bypass suppression, change pricing, or enable transport.

## Current safety state

- External send: disabled by default
- Paid inference: forbidden by policy
- Obsidian runtime dependency: false
- n8n default dependency: false
- Direct-to-master autonomous self-improvement: forbidden
- High-risk changes: human review required

## Highest-priority remaining gates

1. Run focused Obsidian tests and full regression on the v32 branch.
2. Prove supervisor kill/restart recovery and complete launchd validation.
3. Finish one canonical NZ discovery + identity-resolution path.
4. Re-run Email Finder V2 precision/regression gates.
5. Complete missing deterministic audit checks and P10-P13 commercial artifact flow.
6. Expand observability and measured challenger promotion after the above are green.

See `reports/V32_PHASE_AUDIT.md` for the phase-by-phase assessment.
