---
generated_by: ./mm obsidian-sync
authoritative: false
runtime_authority: SQLite + ./mm + launchd
send_authority: false
title: WEBSITE-AUDITOR Control Centre
---

# WEBSITE-AUDITOR Control Centre

Human-facing workspace only. Editing this vault never authorizes outreach, changes
SQLite state, bypasses suppression, changes pricing, or overrides ./mm policy.

## Canonical controls

- ./mm supervisor status
- ./mm supervisor health
- ./mm status
- ./mm obsidian-sync
- ./mm obsidian-status

## Safety

- Paid model/API fallback: disabled
- Live outreach: disabled by default
- Canonical runtime state: SQLite + state files
- Runtime supervisor: launchd + ./mm supervisor
- Agent orchestrator: Hermes
- n8n default runtime dependency: none
