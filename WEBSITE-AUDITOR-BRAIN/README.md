# WEBSITE-AUDITOR-BRAIN

This folder is the Obsidian-facing operator workspace for WEBSITE-AUDITOR v32.

It is intentionally **not** the runtime source of truth. Canonical state remains in SQLite, state files, and the `./mm` control plane.

Use:

```bash
./mm obsidian-sync
./mm obsidian-status
```

The sync direction is runtime → Obsidian only. Editing Markdown cannot approve outreach, bypass suppression, change pricing, mutate pipeline state, or authorize sends.

Expected generated folders:

- `00-DASHBOARD`
- `01-MASTER-PLAN`
- `02-LEADS`
- `03-PROSPECTS`
- `04-AGENTS`
- `05-APPROVALS`
- `06-EXPERIMENTS`
- `07-REPORTS`
- `08-RUNBOOK`

Obsidian may be closed or absent without affecting WEBSITE-AUDITOR runtime.


## Git/privacy behavior

Generated dashboard, prospect, approval, agent, experiment, report and runbook folders are ignored by Git. They remain local to the operator machine unless deliberately exported elsewhere. This prevents routine syncs from committing prospect/runtime state.
