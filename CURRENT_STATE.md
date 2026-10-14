# WEBSITE-AUDITOR — Current State

_Last reconciled: 2026-09-28 · canonical base: `master` · active upgrade: `upgrade/v43-simple-intelligence`_

## Canonical stack

- **Audit engine:** `auditor_toolkit/` with the `wa` CLI.
- **Operator/control plane:** `./mm` → `money-machine/mm`.
- **State/queue:** SQLite + bounded files under `state/`.
- **Supervisor:** `./mm supervisor` with host supervision.
- **Human workspace:** Obsidian, read-mostly and non-authoritative.
- **Cost policy:** local/free first; paid model/API fallback disabled.
- **Outreach:** human review required; live transport remains fail-closed by default.
- **n8n:** not part of the canonical runtime.

## Landed on master

- v32 canonical execution stack and human-approval boundaries.
- deterministic discovery, identity, evidence, opportunity, remediation, demo and quote layers.
- evaluation/proof/local-SEO/technology/runtime upgrade work.
- PR #40 repository hardening and CI/Sonar cleanup.
- PR #41 retirement/archive of obsolete MoneyMachine entrypoints.

## v43 — simple intelligence

The current upgrade intentionally avoids a large AI architecture. It adds a small deterministic
decision layer on top of existing evidence and removes duplicated decision logic where practical.

### Implemented on the v43 branch

- `auditor_toolkit/decision.py`: versioned priority score, confidence, reason codes, blockers and next action.
- MoneyMachine's existing six-component score delegates to the canonical intelligence module.
- PR #39's safe transaction-flow probe has been ported onto current master rather than merging the stale branch.
- Flow probing remains read-only: no form submission, payment or checkout; cross-origin requests are blocked.
- Nightly monitoring is being migrated from legacy scripts to `auditor_toolkit.run_audit`.
- Nightly baselines use bounded latest/previous snapshots instead of creating an endless timestamped Git history.

## Current safety invariants

- No paid model calls are required by v43.
- No autonomous outreach/send behavior is added.
- No scoring or model output can authorize outreach.
- No autonomous production-site modification is added.
- Human review remains required.
- Changes are isolated on an upgrade branch; `master` is not written directly.

## Remaining v43 gates

1. CI compile + unit/regression suites.
2. Opt-in Chromium transaction-flow E2E on a host with Playwright installed.
3. Review any compatibility failures caused by centralising the MoneyMachine score.
4. Exercise one real nightly run and confirm only bounded baseline files change.
5. After CI/host evidence, merge through review; then close superseded PR #39.

## Next intelligence after v43

Only after the deterministic layer is stable:

- outcome calibration by reason code/niche/region;
- false-positive and acceptance-rate reporting;
- local-model summaries/explanations;
- recommendations for weight changes that require human approval.

LLMs should explain evidence, not invent evidence, set prices, approve outreach, or control deterministic gates.
