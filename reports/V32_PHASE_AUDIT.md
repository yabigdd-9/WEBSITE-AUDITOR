# WEBSITE-AUDITOR v32 phase audit

Date: 2026-09-21  
Canonical repo: `/Users/dd/WEBSITE-AUDITOR`  
Baseline master inspected: `dafb280308c4686fe4018da842b2b5df59ec85fc`  
Execution branch: `execution/v32-obsidian-canonical`

Status meanings: **DONE** = current implementation substantially satisfies the v32 gate; **PARTIAL** = useful implementation exists but one or more v32 gates remain unproven; **MISSING** = no canonical implementation found.

| Phase | Status | Evidence / remaining gate |
|---|---|---|
| P0 repository reconciliation | PARTIAL | Canonical GitHub/master exists and experimental branches are separated. Old plans/branches still need archival/retirement and the Downloads experiment cannot be inspected from GitHub. |
| P1 green baseline | PARTIAL | Python 3.11 runtime guard exists. v32 branch removes unused vulnerable NLTK, aligns core dependency declarations, removes tracked egg-info metadata, and keeps secret scanning blocking. Fresh CI/security/full regression must still complete green before the gate is DONE. |
| P2 code consolidation | PARTIAL | Root `./mm` delegates to the MoneyMachine operator; older audit entrypoints still coexist. Deprecation map/one canonical auditor declaration needs completion. |
| P3 continuous control plane | PARTIAL | Supervisor CLI, PID lock, heartbeat, leases/retries/DLQ primitives exist. v32 branch now adds a fail-closed launchd wrapper; local install plus kill/restart proof are still required before the gate is DONE. |
| P4 audit engine | PARTIAL | Deterministic hygiene, Playwright/browser support, robots/sitemap/security checks exist. Lighthouse/Lychee and complete fetch-chain acceptance remain unproven. |
| P5 evidence-first findings | DONE/PARTIAL | Evidence-first records and deterministic scoring exist; full traceability across every legacy finding path still needs regression evidence. |
| P6 NZ discovery | PARTIAL | Historical discovery implementations exist, but one clean canonical NZ discovery lane is not yet established on current master. |
| P7 identity resolution | PARTIAL | Identity/domain handling exists in several modules. Weighted identity confidence across NZBN/business/domain/email is not yet demonstrated as one canonical pipeline. |
| P8 Email Finder V2 | DONE/PARTIAL | Provenance, explicit verification states, catch-all/guess restrictions and NO_VERIFIED_EMAIL behavior exist. Fresh full precision/regression run still required. |
| P9 opportunity scoring | DONE | `auditor_toolkit/opportunity.py` contains deterministic inspectable commercial opportunity scoring separate from technical weakness. |
| P10 remediation engine | PARTIAL | Remediation engine exists; v32 automation classes and artifact acceptance need canonical completion. |
| P11 demo factory | PARTIAL | Demo/QA capabilities exist; automated before/after evidence flow is not fully canonical. |
| P12 quote engine | PARTIAL | Deterministic pricing/quote functions exist; v32 package/versioned pricing contract needs end-to-end proof. |
| P13 prospect packet | PARTIAL | Historical packets exist; one canonical complete packet schema/gate needs enforcement. |
| P14 outreach engine | DONE/PARTIAL | Current master is fail-closed/draft-only. Transport remains disabled by default as required. Outcome/cooldown/cap controls need one current acceptance suite. |
| P15 free model router | PARTIAL | Model router and local/free direction exist. No-silent-paid-fallback must be revalidated across every provider route. |
| P16 agent team | PARTIAL | Hermes/agent roles and DeepSeek shadow lane exist. Branch/worktree isolation policy is documented but not enforced by one control-plane gate. |
| P17 observability | PARTIAL | health, worker logs, heartbeats and reports exist. v32 unified health/metrics/errors/queue/dead-letter CLI surface is incomplete. |
| P18 self-improvement | PARTIAL | Experiment/challenger concepts exist. Golden dataset + measured promotion gate is not yet complete. |
| Obsidian operator workspace | IMPLEMENTING | v32 branch adds read-mostly renderer, vault root, `obsidian-sync`, `obsidian-status`, and non-authority tests. |
| n8n default dependency | DONE | v32 canonical direction is no n8n dependency in the default runtime. Any n8n work remains experimental only and must not be merged as a required runtime component. |

## Immediate execution order from this audit

1. Finish and locally test the Obsidian operator workspace.
2. Fresh full regression/security baseline on current v32 branch.
3. Prove supervisor kill/restart recovery and add/verify launchd support.
4. Finish canonical NZ discovery and identity resolution.
5. Re-run Email Finder V2 precision/regression gates.
6. Complete missing P4 audit checks and P10-P13 commercial artifact pipeline.
7. Expand observability and measured challenger/self-improvement only after the above gates are green.

## Safety state

- `paid_allowed=false`
- `max_cost_usd=0`
- external outreach sending disabled by default
- Obsidian is non-authoritative
- no Markdown edit can bypass SQLite/runtime approval, suppression, duplicate, quote, or send controls
- n8n is not part of the required/default stack
