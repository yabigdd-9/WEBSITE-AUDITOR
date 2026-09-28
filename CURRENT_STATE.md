# WEBSITE-AUDITOR — Current State

_Last updated: 2026-09-29 · branch `integration/v44-local-machine-convergence` · PR #52_

## Canonical direction

- **Repository:** `/Users/dd/WEBSITE-AUDITOR`
- **Audit engine:** `auditor_toolkit/` with thin `wa` CLI.
- **Operator CLI:** `./mm` → `money-machine/mm`.
- **Runtime authority:** SQLite + `./mm supervisor`.
- **Supervisor:** user launchd, single-instance, heartbeat/lease recovery.
- **FCC:** separate user launchd, loopback-only on `127.0.0.1:8082`.
- **Model policy:** exact-certified FCC route first; otherwise Hermes live-verified `:free` role route; otherwise DEFER.
- **FCC presets/catalog:** operator-controlled and preserved; Money Machine certification is separate from the FCC server's default preset.
- **Local llama.cpp / Ollama:** not active Money Machine routes.
- **Cost policy:** `paid_allowed=false`, `max_cost_usd=0`; no automatic paid fallback.
- **External data policy:** repository default `data_collection: deny`; only explicitly attested public/synthetic prompts may opt into a data-collecting free endpoint per request.
- **Outreach:** fail-closed; human review required; external sends default to zero.
- **Human workspace:** Obsidian; n8n is not part of the default runtime.

## v44 release-candidate status

| Area | Status | Evidence / remaining acceptance |
| --- | --- | --- |
| Automated CI | ✅ PASS | PR #52 head `a0ebdb38`: CI, Security, Local toolkit and SonarCloud all green. |
| Local runtime | ✅ Implemented | Dual launchd runtime for FCC + Money Machine, loopback FCC boundary, restart/recovery and duplicate-worker protections. |
| Network guard | ✅ Implemented | Multi-host probe plus all-resolved-address fallback; degraded mode does not block deterministic local work. |
| Discovery | ✅ Implemented | Bounded recurring discovery, local imports + loopback SearXNG, provenance and dedupe before queueing. |
| Identity | ✅ Implemented | Weighted deterministic NZBN/name/domain/contact evidence; weak single-signal matches cannot auto-elevate confidence. |
| Opportunity scoring | ✅ Implemented | Commercial qualification remains separate from technical weakness. |
| Model router | ✅ Implemented | FCC only when the exact route is explicitly certified zero-cost; Hermes `:free` fallback live-verifies catalog pricing; no paid fallback. |
| Privacy boundary | ✅ Implemented | Secrets/contact details/local paths are redacted; secret-bearing prompts are held; repository default remains `data_collection: deny`. |
| Outreach safety | ✅ Implemented | Paid calls and external sends are fail-closed at zero by default. |
| Documentation | ◐ Updating | v44 state is canonical here; older reports are historical snapshots and must not be treated as current release state. |
| Host acceptance | ◐ REQUIRED | Current-head doctor/health, current-head bounded live free-model smoke, real Chromium E2E, optional Lighthouse/Lychee, optional local SearXNG. |
| 24h soak | ⏳ REQUIRED | Must complete on the exact final release-candidate head with no duplicate workers, healthy heartbeat/leases/DLQ, $0 paid usage and zero external sends. |

## Current release blockers

There are no known failing repository gates on the current PR head. PR #52 remains **draft** until host acceptance and the final unattended soak are recorded.

The remaining release blockers are:

1. Pull the exact final PR #52 head onto the Mac and run `./mm doctor` + `./mm health`.
2. Run one bounded current-head live free-model smoke through the Money Machine route and verify `cost_usd=0`.
3. Run real Chromium E2E on the same head; run Lighthouse/Lychee only if installed/required.
4. If local SearXNG is part of the deployment, verify `127.0.0.1:8888` and one bounded discovery run; otherwise record it as optional/not enabled.
5. Run a **24+ hour unattended soak** on the unchanged release-candidate head.
6. Record final evidence, mark PR #52 ready for review, then merge only after human review.

## Release acceptance criteria

A release candidate is acceptable only when all of the following remain true:

- supervisor stays single-instance and heartbeating;
- no unexpected lease growth or dead-letter growth;
- network guard recovers correctly and does not produce false degraded state from one address family;
- `paid_calls == 0`;
- `external_sends == 0`;
- `paid_model_fallback == false`;
- FCC remains loopback-only;
- FCC presets/provider catalog are not destructively pruned by Money Machine setup;
- Money Machine does not treat an FCC model as usable unless it is explicitly certified;
- Hermes external fallback uses only live-verified `:free` models with zero price caps;
- no confidential/customer material is sent to data-collecting free endpoints;
- working tree remains clean during the soak.

## PR #52

- **Branch:** `integration/v44-local-machine-convergence`
- **Base:** `master`
- **State:** open draft
- **Current verified head when this file was updated:** `a0ebdb38`
- **Automated gates:** CI ✅ · Security ✅ · Local toolkit ✅ · SonarCloud ✅
- **Merge policy:** do not merge merely because GitHub reports mergeable; finish host acceptance + soak, then mark ready for review.

## Historical material

Older v32/v43 reports, FABLE reports, prior local-model experiments, and historical `reports/CURRENT_STATE.md` / `reports/phase-status.json` entries are retained as evidence. They are not authoritative for the current v44 release unless explicitly updated to reference this state.

