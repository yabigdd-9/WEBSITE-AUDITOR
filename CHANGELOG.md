# CHANGELOG

## 2026-09-21 — v32 canonical execution begins

- Adopted **WEBSITE-AUDITOR Master Merged Plan v32** as the canonical execution direction.
- Preserved `paid_allowed=false`, `max_cost_usd=0`, and outreach-send-disabled defaults.
- Confirmed Obsidian is the human-facing operator/master-brain layer only; SQLite, state files, `./mm`, and supervisor policy remain authoritative.
- Explicitly removed n8n from the required/default execution path. Existing n8n branches remain experimental and are not promotion candidates for the default stack.
- Added `money-machine/mm_obsidian.py` with one-way runtime → Obsidian rendering.
- Added `./mm obsidian-sync` and `./mm obsidian-status`.
- Added `WEBSITE-AUDITOR-BRAIN/` workspace root.
- Added tests proving Obsidian is optional and cannot authorize outreach or runtime mutations.
- Added `reports/V32_PHASE_AUDIT.md`.
- Replaced stale `reports/CURRENT_STATE.md` references with the current WEBSITE-AUDITOR repo/workspace and v32 direction.

### Promotion state

Not merged. Focused tests and full regression must be green before promotion.
