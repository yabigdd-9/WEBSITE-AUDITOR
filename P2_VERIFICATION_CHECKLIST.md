# P2 PostgreSQL Cutover — Live Verification Checklist

**Execute in order. Do not proceed to next step until current step passes.**

---

## Pre-Requisites (Owner Must Complete First)

### 1. GitHub Repository Secrets/Variables
Verify via GitHub UI: Settings → Secrets and variables → Actions

| Name | Type | Expected Value | Verified |
|------|------|----------------|----------|
| `WA_POSTGRES_DSN` | Secret | `postgresql://moneymachine_runner.<project_ref>:<password>@db.<project_ref>.supabase.co:5432/postgres?sslmode=verify-full` | ☐ |
| `WA_PIPELINE_STATE_KEY` | Secret | 32-byte Fernet key (base64) | ☐ |
| `WA_PIPELINE_ENABLED` | Variable | `true` | ☐ |
| `WA_PIPELINE_STORAGE` | Variable | `checkpoint` (will change to `postgres` after cutover) | ☐ |
| `MM_REPORT_PUBLIC_KEY_B64` | Variable | Base64 public key for report encryption | ☐ |

### 2. Supabase Project State
Verify via Supabase Dashboard → SQL Editor or CLI

| Check | Method | Expected | Verified |
|-------|--------|----------|----------|
| Migration applied | `supabase/migrations/20261116104934_private_pipeline_store.sql` | Schema `moneymachine` exists with all tables | ☐ |
| Roles created | `SELECT rolname FROM pg_roles WHERE rolname LIKE 'moneymachine%';` | `moneymachine_worker`, `moneymachine_reader` | ☐ |
| RLS enabled | `SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='moneymachine';` | All tables `rowsecurity=true` | ☐ |
| Policies exist | `SELECT * FROM pg_policies WHERE schemaname='moneymachine';` | `worker_access` + `owner_read` per table | ☐ |
| TLS CA available | Dashboard → Settings → Database → SSL Mode | `verify-full` supported | ☐ |
| Connection string | Dashboard → Settings → Database → Connection pooling | Direct (port 5432) connection string | ☐ |

---

## Step 1: Persistence Verification (Two-Runner Durability)

**Action:**
```bash
gh workflow run postgres-persistence-verification.yml -f verify_persistence=true
```

**Watch for:** Both `read-only-preflight` → `first-runner` → `second-runner` complete successfully.

**Verification Criteria:**
| Job | Expected | Verified |
|-----|----------|----------|
| `read-only-preflight` | "Restricted Postgres runtime preflight passed with zero writes" | ☐ |
| `first-runner` | "First runner verified durable pause event; request reservations unchanged" | ☐ |
| `second-runner` | "Independent runner verified persistence; no audit or send was executed" | ☐ |
| Event count | Second runner sees `events >= first-runner count + 1` | ☐ |
| Reservations | Unchanged across both runners (no audit/send) | ☐ |

**If any job fails:** Inspect logs. Common issues:
- `WA_POSTGRES_DSN` secret malformed → fix secret
- Migration not applied → run migration
- TLS verification failed → check Supabase CA
- Role/RLS missing → re-run migration

---

## Step 2: Checkpoint Import Verification (Source Run 44746146509)

**Action:**
```bash
gh workflow run postgres-checkpoint-cutover.yml \
  -f source_run=44746146509 \
  -f import_state=true
```

**Watch for:** `import-state` job completes successfully.

**Verification Criteria:**
| Check | Expected | Verified |
|-------|----------|----------|
| Artifact fetch | Downloads `pipeline-state` from run 44746146509 | ☐ |
| Verify-only | "Trusted encrypted checkpoint verified in memory" | ☐ |
| Import | JSON report with `already_imported: false`, `source_run: "44746146509"` | ☐ |
| Metrics | `prospects_found`, `audits_succeeded`, `contacts_sent: 0` | ☐ |
| No duplicate import | Re-run with same `source_run` → `already_imported: true` | ☐ |

**Critical:** Verify the imported state matches expectations:
- Prospect count matches artifact
- No `contacts_sent > 0` (sending disabled)
- `paid_api_cost: 0`
- `auto_send: "blocked; delivery/compliance gates unverified"`

---

## Step 3: Production Cutover Switch

**Action:**
```bash
gh variable set WA_PIPELINE_STORAGE --body "postgres"
```

**Verification:**
| Check | Expected | Verified |
|-------|----------|----------|
| Variable set | `WA_PIPELINE_STORAGE=postgres` in GitHub UI | ☐ |
| Next scheduled run | Uses `--postgres` storage mode | ☐ |
| Artifact upload | Both `pipeline-state` AND `pipeline-postgres-backup` uploaded | ☐ |

---

## Step 4: End-to-End Verification (Next Scheduled Run)

**Wait for:** Tuesday 24 Nov 2026 04:50 UTC scheduled run (or trigger manually)

**Verification Criteria:**
| Check | Expected | Verified |
|-------|----------|----------|
| `draft-pipeline` job | Succeeds with Postgres backend | ☐ |
| Logs show | "private Postgres" storage authority | ☐ |
| Artifacts | `pipeline-state` + `pipeline-postgres-backup` both present | ☐ |
| Schedule-health | Wed 25 Nov run verifies Tue 24 Nov checkpoint | ☐ |
| Failure alert | No alert triggered (run succeeds) | ☐ |
| Metrics | `contacts_sent: 0`, `paid_api_cost: 0` | ☐ |

---

## Rollback Verification (Before Considering P2 Complete)

**Test Rollback:**
```bash
gh variable set WA_PIPELINE_STORAGE --body "checkpoint"
```

**Verify:**
| Check | Expected | Verified |
|-------|----------|----------|
| Next run | Uses checkpoint mode (artifact-only) | ☐ |
| State | Restored from latest `pipeline-state` artifact | ☐ |
| Postgres data | Preserved (not deleted) | ☐ |
| Re-cutover | Can re-run cutover workflow to restore Postgres | ☐ |

**Then restore:** `gh variable set WA_PIPELINE_STORAGE --body "postgres"`

---

## P3 Dashboard Deployment (After P2 Complete)

Only proceed after P2 Steps 1-4 verified.

| Step | Action | Verified |
|------|--------|----------|
| 1 | Deploy Caddy with valid cert (`caddy run --config deploy/cloud/Caddyfile`) | ☐ |
| 2 | Install systemd service (`sudo cp deploy/cloud/website-auditor-dashboard.service /etc/systemd/system/`) | ☐ |
| 3 | Enable/start service (`sudo systemctl enable --now website-auditor-dashboard`) | ☐ |
| 4 | Set dashboard password (`wa dashboard --set-password --output-root outputs/toolkit`) | ☐ |
| 5 | Verify HTTPS access (`curl -k https://dashboard.yourdomain.com/health`) | ☐ |
| 6 | Verify login + dashboard loads | ☐ |
| 7 | Verify Postgres backend (`wa dashboard --pipeline-postgres --port 8080` locally) | ☐ |

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| P2 Verification | | | |
| P3 Verification | | | |
| Production Release | | | |

---

**Do not mark P2/P3 complete without all checkboxes verified.**