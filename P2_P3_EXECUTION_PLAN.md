# P2 PostgreSQL Cutover & P3 Dashboard — Execution Plan

**Repository:** `yabigdd-9/WEBSITE-AUDITOR`  
**Branch:** `master`  
**Prepared:** 2026-11-21

---

## P2: PostgreSQL Cutover — Owner-Controlled Authorization Process

### Current State: Infrastructure Code-Complete ✅

| Component | File | Status |
|-----------|------|--------|
| Private Postgres Store | `scripts/postgres_store.py` | ✅ Implemented |
| TLS Verification Action | `.github/actions/supabase-tls/action.yml` | ✅ Implemented |
| Migration SQL | `supabase/migrations/20261116104934_private_pipeline_store.sql` | ✅ Ready |
| Runtime Preflight | `scripts/postgres_runtime_preflight.py` | ✅ Implemented |
| Backup/Restore | `scripts/postgres_backup.py` | ✅ Implemented |
| Persistence Verification WF | `.github/workflows/postgres-persistence-verification.yml` | ✅ Ready |
| Checkpoint Cutover WF | `.github/workflows/postgres-checkpoint-cutover.yml` | ✅ Ready |
| Test Coverage | `toolkit_tests/test_postgres_store.py` | ✅ 22 tests passing |

### Security Posture Verified
- **Role separation:** `moneymachine_runner` (login) → `moneymachine_worker` (RLS writer)
- **Row Level Security:** Enabled + FORCED on all `moneymachine` tables
- **Privilege restriction:** `anon`, `authenticated`, `service_role` denied all access
- **TLS:** `sslmode=verify-full` with Supabase CA; direct/session connections only
- **No cloud upload:** Backups are local paired exports only (0600 perms, SHA-256)

---

### Owner Manual Steps Required (Cannot Be Automated)

#### Step 1: Configure GitHub Repository Secrets
**Action:** Add `WA_POSTGRES_DSN` secret via GitHub UI
```
Settings → Secrets and variables → Actions → New repository secret
Name: WA_POSTGRES_DSN
Value: postgresql://moneymachine_runner.<project_ref>:<password>@db.<project_ref>.supabase.co:5432/postgres?sslmode=verify-full
```
**Requirements:**
- Direct connection (not pooled): `db.<project_ref>.supabase.co`
- User: `moneymachine_runner.<project_ref>`
- `sslmode=verify-full` (enforced by `connection_options()`)
- Port 5432, dbname `postgres`

#### Step 2: Apply Supabase Migration
**Action:** Run migration via Supabase Dashboard or CLI
```bash
# Via Supabase CLI (if configured)
supabase db push --include-all

# Or via Dashboard SQL Editor: paste contents of
# supabase/migrations/20261116104934_private_pipeline_store.sql
```
**Verification:** Migration creates schema `moneymachine` with tables, RLS policies, and roles `moneymachine_worker`/`moneymachine_reader`.

#### Step 3: Run Persistence Verification (Two-Runner Durability Proof)
**Action:** Trigger workflow via GitHub UI or CLI
```bash
gh workflow run postgres-persistence-verification.yml -f verify_persistence=true
```
**What it does:**
1. Read-only preflight validates role + RLS (zero writes)
2. First runner: persists a pause event, records event count
3. Second runner (independent): verifies event persisted, adds another pause event
4. Both verify request reservations unchanged (no audit/send executed)

**Success criteria:** Both runners complete, events persist across runners.

#### Step 4: Authorize Checkpoint Cutover
**Action:** Trigger workflow with latest successful worker run ID
```bash
gh workflow run postgres-checkpoint-cutover.yml \
  -f source_run=44746146509 \
  -f import_state=true
```
**What it does:**
1. Fetches encrypted `pipeline-state` artifact from `source_run`
2. Verifies checkpoint in memory (verify-only step)
3. Imports state atomically into private Postgres (transactional, no audits/sends)
4. Records `checkpoint_import` receipt with source run ID and actor

**Prerequisites:** Steps 1-3 complete; `source_run` must be a successful `schedule` event run on `master`.

#### Step 5: Switch Storage Mode
**Action:** Set repository variable via GitHub UI
```
Settings → Secrets and variables → Actions → Variables → New repository variable
Name: WA_PIPELINE_STORAGE
Value: postgres
```
**Effect:** Next scheduled worker run uses `--postgres` storage; uploads `pipeline-postgres-backup` artifact alongside `pipeline-state`.

#### Step 6: Verify Production Cutover
**Action:** Monitor next scheduled run (Tue 24 Nov 04:50 UTC or later)
- Check workflow run uses Postgres (logs show "private Postgres" storage)
- Verify `pipeline-postgres-backup` artifact uploaded (30-day retention)
- Confirm `draft-pipeline` job succeeds with Postgres backend

---

### Rollback Plan (If Needed)

If Postgres cutover causes issues:
1. **Immediate:** Set `WA_PIPELINE_STORAGE=checkpoint` (reverts to artifact-based)
2. **State recovery:** Next run restores from latest `pipeline-state` artifact (checkpoint mode)
3. **Postgres data:** Preserved in Supabase; can be re-imported via cutover workflow
4. **No data loss:** Checkpoint artifacts remain source of truth until Postgres verified

---

## P3: Protected Owner Dashboard — HTTPS, Auth, Access Controls, Secure DB

### Current State: Local Portal Implemented ✅

| Component | File | Status |
|-----------|------|--------|
| FastAPI App | `auditor_toolkit/portal.py` | ✅ Implemented |
| Argon2 Password Hashing | `setup_password()` | ✅ 12+ char minimum |
| Server-Side Sessions | HMAC-SHA256 tokens, HttpOnly cookies | ✅ |
| CSRF Protection | Double-submit cookie pattern | ✅ |
| Trusted Host Middleware | `127.0.0.1`, `localhost` | ✅ |
| Security Headers | CSP, no-store, nosniff, frame-ancestors | ✅ |
| Rate Limiting | 5 attempts/minute per IP | ✅ |
| Dashboard Routes | `/`, `/monthly`, `/runs/{id}`, `/health` | ✅ |
| Monthly Artifacts | PDF, HTML, email, JSON, revenue, ROI, action | ✅ |
| CLI Entry Point | `wa dashboard --port 8080` | ✅ |

### Missing for Production (P3 Requirements)

| Requirement | Current | Needed |
|-------------|---------|--------|
| **HTTPS/TLS Termination** | HTTP on 127.0.0.1 | Reverse proxy (Caddy/nginx) + valid certs |
| **External Access** | Localhost only | VPN/Tailscale or authenticated public endpoint |
| **Database Integration** | SQLite only | Postgres read replica (`moneymachine_reader` role) |
| **Process Management** | Manual `uvicorn` | Systemd service or supervised |
| **Log Rotation** | stdout | Structured logging + rotation |
| **Health Monitoring** | `/health` endpoint | Uptime checks, alerting |

### Recommended Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│   Client    │────▶│  Caddy/TLS  │────▶│  FastAPI Portal  │
│  (Browser)  │     │  (Port 443) │     │  (127.0.0.1:8080)│
└─────────────┘     └─────────────┘     └────────┬─────────┘
                                                 │
                    ┌────────────────────────────┘
                    ▼
           ┌──────────────────┐
           │  Supabase PG     │
           │  (read replica)  │
           │  moneymachine_   │
           │  reader role     │
           └──────────────────┘
```

### Implementation Steps

#### Step 1: Add Postgres Read Support to Portal
**File:** `auditor_toolkit/portal.py` (new `pipeline_postgres=True` mode exists in tests)
```python
# In create_app(): accept pipeline_postgres parameter
# Use PostgresPipelineStore with moneymachine_reader role
# Connection: direct/session, sslmode=verify-full
```

#### Step 2: Create Caddyfile for HTTPS
**File:** `deploy/cloud/Caddyfile`
```caddy
dashboard.yourdomain.com {
    reverse_proxy 127.0.0.1:8080
    header {
        Strict-Transport-Security "max-age=31536000"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
    }
}
```
**Or use existing domain with DNS challenge.**

#### Step 3: Systemd Service for Portal
**File:** `deploy/cloud/website-auditor-dashboard.service`
```ini
[Unit]
Description=Website Auditor Dashboard
After=network-online.target

[Service]
Type=simple
User=websiteauditor
WorkingDirectory=/mnt/wa-data/WEBSITE-AUDITOR
Environment=MM_ROOT=/mnt/wa-data/WEBSITE-AUDITOR
ExecStart=/mnt/wa-data/WEBSITE-AUDITOR/.venv-email/bin/python -m uvicorn auditor_toolkit.portal:create_app --factory --host 127.0.0.1 --port 8080
Restart=on-failure
UMask=0077

[Install]
WantedBy=multi-user.target
```

#### Step 4: Secure Database Connection for Dashboard
- Use `moneymachine_reader` role (read-only, RLS-enforced)
- Connection: `postgresql://moneymachine_runner.<project_ref>:<password>@db.<project_ref>.supabase.co:5432/postgres?sslmode=verify-full`
- Same TLS verification as worker (`connection_options()` validation)

---

## Execution Order & Dependencies

```
P2 Step 1 (Secrets) ──▶ P2 Step 2 (Migration) ──▶ P2 Step 3 (Persistence Verify)
                                                          │
                                                          ▼
P3 Step 4 (DB Connection) ◀── P2 Step 4 (Cutover) ──▶ P2 Step 5 (Switch Mode)
                                                          │
                                                          ▼
                                                   P2 Step 6 (Verify)
                                                          │
                                                          ▼
                                                   P3 Steps 1-4 (Dashboard)
```

**Critical Path:** P2 Steps 1-4 must complete before P3 can use Postgres backend.

---

## Verification Checklist

### P2 Complete When:
- [ ] `WA_POSTGRES_DSN` secret configured
- [ ] Migration applied to Supabase project
- [ ] `postgres-persistence-verification.yml` passes (two runners)
- [ ] `postgres-checkpoint-cutover.yml` succeeds with `import_state=true`
- [ ] `WA_PIPELINE_STORAGE=postgres` variable set
- [ ] Next scheduled run uses Postgres (artifact `pipeline-postgres-backup` present)

### P3 Complete When:
- [ ] Portal reads from Postgres via `moneymachine_reader` role
- [ ] Caddy/nginx terminates HTTPS with valid cert
- [ ] Systemd service runs portal automatically
- [ ] Dashboard accessible via domain (not localhost)
- [ ] `/health` endpoint monitored

---

## Safety Gates (Do Not Bypass)

1. **No production cutover without owner `workflow_dispatch`** — Both workflows require explicit `import_state=true` / `verify_persistence=true`
2. **No paid model/API activation** — `MM_PAID_ALLOWED=0` enforced in all workflows
3. **No external send enablement** — `MM_EXTERNAL_SEND_ALLOWED=0`, `daily_cap=0`
4. **No direct master edits** — All changes via PR #36 (draft) or feature branches
5. **Rollback tested** — Verify checkpoint mode works before cutover

---

## Next Actions for Owner

1. **Immediate (P2):** Configure `WA_POSTGRES_DSN` secret in GitHub
2. **Immediate (P2):** Apply Supabase migration via Dashboard/CLI
3. **Then:** Run `postgres-persistence-verification.yml` with `verify_persistence=true`
4. **Then:** Run `postgres-checkpoint-cutover.yml` with `source_run=44746146509`, `import_state=true`
5. **Then:** Set `WA_PIPELINE_STORAGE=postgres` variable
6. **Parallel (P3):** Deploy Caddy + systemd service for dashboard HTTPS
7. **Parallel (P3):** Wire portal to Postgres read replica

All automated infrastructure is in place. The remaining steps are owner-authorized operations.