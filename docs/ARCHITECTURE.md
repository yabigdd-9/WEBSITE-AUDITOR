# Cloud platform architecture and Phase 0 inventory

Inspection: 2026-11-16, base `e8da967379e38508fe3fee43ac6b49f202e35bbd`.
Fetched origin/master before changes. MIT repository; optional services retain
separate terms. No production deployment is authorized by this implementation.

## Dependency map

```text
reviewed config/cloud-prospects.json + clients.txt
  -> cloud_prospect_pipeline.policy_rows
  -> eligibility / suppression / robots / retry budget
  -> cloud_review_only_opportunities.run_review_sites
  -> wa / auditor_toolkit (canonical Fetcher, checks, evidence)
  -> evidence-qualified internal scope draft
  -> checkpoint OR private SQLite pipeline store
  -> owner-verified outcome import (no sending)

scheduled canonical reviews -> report_vault (owner public key)
  -> encrypted Actions artifact -> owner offline decrypt -> review_ledger SQLite

local mm discovery -> mm_pipeline / mm_core SQLite -> local supervisor
local auditor_toolkit History -> authenticated loopback portal
```

## Feature-gap matrix

Statuses describe source inspection; no fresh production readiness is asserted.

| Component | Classification | Evidence / gap |
| --- | --- | --- |
| Canonical audit + SSRF-safe fetcher | Implemented but not production-verified in this session | auditor_toolkit; cloud caller bounds pages, depth, bytes, runtime |
| Scheduled Actions orchestration | Implemented but not production-verified in this session | cloud-scheduled-audits.yml; two daily runs; concurrency; read-only token |
| Encrypted public-key report vault | Implemented but not production-verified in this session | report_vault.py; owner key stays offline; 30-day artifacts |
| Audit-to-draft queue | Partially implemented | cloud_prospect_pipeline.py; reviewed intake, bounded retries, encrypted checkpoint; artifact expiry is not durable DB |
| Existing persistent databases | Implemented but not integrated | mm_core SQLite, auditor_toolkit History, offline review_ledger; no configured hosted DB identified |
| Discovery | Implemented but not integrated with cloud acquisition | mm_discovery curated/NZBN/OSM exports and loopback SearXNG; cloud uses reviewed manifest only |
| Finding qualification | Implemented | observed evidence and complete audit gate; no sales-intent inference |
| Commercial scoring | Implemented but not integrated with cloud queue | mm_opportunity_scoring; requested five-dimension weights not wired |
| Remediation/demo/quote/packet | Implemented but not integrated with cloud queue | toolkit modules; cloud produces unpriced internal scope only |
| Owner dashboard | Partially implemented | portal.py authenticates local audit History only; no remote owner dashboard for pipeline records |
| Outcome/approval history | Partially implemented | exact current draft hash on approval import; no production send eligibility adapter |
| Sending | Blocked by owner activation and provider/consent evidence | no approved canonical live transport; cap zero |
| Client project lifecycle | Missing from cloud integration | accepted quote records exist; no linked project/milestone creation |
| Supervisor | Implemented but not integrated with cloud persistence | local daemon leases/recovery; Actions is scheduled, not continuous |
| Durable encrypted archive | Blocked by storage approval | do not extend public artifact lifetime into a database claim |
| Managed DB / remote auth / production verification | Blocked by external service configuration and deployment approval | no service provisioned |

## Duplicate functionality and integration decisions

Preserve canonical auditor; legacy website_auditor.py variants are compatibility
callers, not new scanners. Keep local MoneyMachine and History schemas intact.
Review ledger is an offline import tool, not the cloud queue. Preserve both vault
formats: public-key report encryption and symmetric worker checkpoints have
separate trust boundaries. Reuse existing path validation rather than moving
plaintext state into the public checkout. The portal remains loopback restricted
until a reviewed HTTPS/auth deployment exists.

## Configuration and release gates

Cloud: MM_REPORT_PUBLIC_KEY_B64 (public repository variable),
MM_ENCRYPTED_REPORT_OUT and RUNNER_TEMP (temporary paths), WA_PIPELINE_STATE_KEY
(secret symmetric checkpoint key), WA_PIPELINE_ENABLED (activation variable),
BOOTSTRAP, WA_RECOVERY_RUN, WA_OUTCOMES_ENCRYPTED, GitHub runner IDs/token.
Safety: MM_PAID_ALLOWED=0, MM_ALLOW_EXTERNAL_FREE_MODELS=0,
MM_EXTERNAL_SEND_ALLOWED=0 and canonical transport disabled/cap zero.
Local portal: owner-created Argon2 password file and server-side sessions.
Other optional model/email secrets are not needed by this cloud path.
Never collect private report keys in CI, DB or chat.

CI: ci.yml full Python/portable MoneyMachine; toolkit-tests.yml lint, pip check,
wheel and optional browser E2E; security.yml gitleaks + strict pip-audit;
CodeQL and SonarCloud; dedicated offline cloud/vault/ledger suites.
Current required branch-protection checks could not be inspected: gh REST and
GraphQL requests returned Forbidden. Connector commit lookup confirms merged
PRs #79/#80/#77/#76; commit workflow lookup returned no runs, which is not proof
of absence or success. See PRODUCTION_VERIFICATION.md.

## Ordered backlog / smallest integration path

1. Phase 1: private SQLite adapter for existing queue; transaction/migration,
   independent-process persistence, identity constraints and backup/restore tests.
   Existing SQLite is first preference. A persistent trusted filesystem is needed
   for hosted use; ephemeral Actions disks cannot meet this gate.
2. Phase 2: connect existing discovery normalization/provenance to reviewed intake;
   deduplicate and quarantine; require source-specific terms/permission before
   enabling acquisition. Never let discovery alone authorize an audit.
3. Phase 3: persist audit attempt history and evidence; deterministic suitability
   breakdown, remediation and configured-rate proposals using existing modules.
4. Phase 4: extend existing authenticated portal with private pipeline views;
   HTTPS, remote auth, storage and deployment design before hosted activation.
5. Phase 5: version-bound decisions, suppression, mock transport only; NZ consent,
   sender identification and unsubscribe evidence before any live activation.
6. Phase 6: accepted proposal version -> project/milestones -> handover evidence.
7. Phase 7: persistent shared quotas, encrypted archive provider, restore exercise,
   dependency/security checks and bounded production verification after approval.

Managed alternatives to evaluate before activation: Supabase Postgres (RLS,
connection/pause/storage quotas); Neon Postgres (compute/storage/pause limits);
private SQLite on an already approved durable host (single writer, volume and
backup requirements). No current prices, quotas, account or service availability
have been verified. Do not provision any option based on assumed free allowances.

## Subsequent integration status

The opt-in private PipelineStore and its CI are implemented on PR #82; hosted
persistence remains unverified. Phase 2 adds offline export intake through the
existing mm_discovery adapters, pending-review candidates, provenance and explicit
reviewed-queue links. See IMPLEMENTATION_PROGRESS.md for exact evidence/status.
These additions do not establish live source acquisition, remote dashboard or
production readiness. Supabase account discovery found existing projects but no
repo-to-project mapping; the owner mapping question is pending.
