# WEBSITE-AUDITOR MASTER PLAN

Canonical version: **32.0**  
Status: **CANONICAL_EXECUTION_PLAN**

The full source plan is `WEBSITE_AUDITOR_MASTER_MERGED_PLAN_v32_OBSIDIAN.yaml.md`.

## Non-negotiables

- `paid_allowed=false`
- `max_cost_usd=0`
- no silent paid fallback
- outreach sending disabled by default
- no direct autonomous edits to master
- SQLite/state files are authoritative runtime state
- `./mm` is the canonical operator interface
- launchd / supervisor is the intended continuous control plane
- Obsidian is the human-facing master brain, dashboard, review workspace, and runbook layer
- Obsidian is not the database, queue, pricing authority, approval authority, or send authority
- n8n is optional future infrastructure and is **not** required by the default stack

## Phase order

P0 repository reconciliation → P1 baseline → P2 consolidation → P3 continuous control plane → P4 audit engine → P5 evidence-first findings → P6 NZ discovery → P7 identity → P8 Email Finder V2 → P9 opportunity scoring → P10 remediation → P11 demo factory → P12 quote engine → P13 prospect packet → P14 outreach engine → P15 free-model router → P16 agent team → P17 observability → P18 measured self-improvement.

## Operator workspace

Recommended Obsidian vault: `WEBSITE-AUDITOR-BRAIN`.

Runtime → Obsidian sync is allowed. Markdown → runtime mutation is forbidden except through explicit gated `./mm` commands that independently validate policy.

## Promotion rule

Every implementation change must be isolated, tested, regression-checked, recorded in `CHANGELOG.md` and `reports/CURRENT_STATE.md`, and rejected if it introduces a regression or paid dependency.
