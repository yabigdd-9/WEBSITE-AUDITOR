# REV30 BASELINE

**Generated:** 2026-09-19 00:50 NZST  
**Repository root:** `/Users/dd/WEBSITE-AUDITOR`  
**Spec pinned commit:** `454901b879016b4d967e6987d7e85e5e2edca94f`  
**Current HEAD:** `454901b879016b4d967e6987d7e85e5e2edca94f` (MATCHES SPEC)  
**Branch:** `feature/rev30-execution` (created from clean master)  
**Remote:** `https://github.com/yabigdd-9/WEBSITE-AUDITOR.git`  

---

## 1. Repository Identity & Layout

| Item | Value |
|------|-------|
| Git remote | yabigdd-9/WEBSITE-AUDITOR |
| HEAD commit | 454901b |
| Working tree | clean |
| Symlinks | config, control-plane, migrations, scripts, tests → money-machine/ |
| Money-machine modules | mm_core, mm_email, mm_email_cli, mm_email_network, mm_email_store, mm_intelligence, mm_lead_qualifier, mm_lead_qualify, mm_outreach, mm_audit_workflow, mm_operator |
| Scripts dir | money-machine/scripts/ (supervisor, free_role_router, hermes_adapter, quality_controller, status, system_doctor, money_machine_auditor) |
| Root entrypoint | `mm` → `money-machine/mm` (shell shim → python script) |

## 2. Active Database

| Item | Value |
|------|-------|
| Path | `database/money_machine.db` |
| Integrity | verified via backup/restore path |
| Businesses | 22 (10 HVAC, 9 renovation, 3 audited) |
| Email schema migrations | v3, v4, v5 applied |
| Email candidates | 33 (UNVERIFIED/OBSERVED/CANDIDATE/SUPPRESSED) |
| Suppression records | mm_suppression table populated |
| Deals/stages | DISCOVERED, AUDITED, HUMAN_REVIEW states present |
| Jobs | 0 (no active pipeline jobs) |
| Cash/receipts | 0 (zero external spend verified) |

## 3. Runtime Environment

| Component | Status | Value |
|-----------|--------|-------|
| Python (system) | PRESENT | 3.9.6 (`/usr/bin/python3`) |
| Python (project) | PRESENT | 3.11.16 (`/Users/dd/.local/bin/python3.11`) |
| Project venv | CREATED | `.venv-email/` (used by `mm` via MM_PYTHON) |
| pytest | INSTALLED | 9.1.1 |
| bs4/lxml/yaml/httpx/aiohttp | INSTALLED | via pip |
| email-validator/tldextract/idna | INSTALLED | via pip |
| Node | PRESENT | v26.9.0 |
| npm | PRESENT | 11.19.1 |
| Hermes CLI | PRESENT | v0.21.3 (2026.9.14), gateway on localhost |
| Ollama | ABSENT | Not installed |
| Docker | ABSENT | Not installed |
| Codex CLI | ABSENT | Not installed |
| Playwright (Python) | ABSENT | Not installed |

## 4. Outbound / Release Gate State

| Gate | State |
|------|-------|
| `outreach/execution_gate.py` | LOCKED — always raises `PermissionError` |
| `outreach/send.py` | LOCKED — requires `--i-approve`, consent gate first |
| `routing.yaml` model execution | DISABLED (`model_execution_enabled: false`) |
| `routing.yaml` paid tokens | DISABLED (`paid_tokens: false`) |
| Outbound count | 0 (enforced by code) |
| Suppression active | mm_suppression table, checked before draft/send |

## 5. Provider / Router State

| Component | State |
|-----------|-------|
| Free role router | PRESENT, BLOCKED_COST (no API key) |
| Hermes adapter | PRESENT, BLOCKED_COST (capability-only) |
| OpenRouter catalog | Stale (verified_utc 2026-09-09) — model IDs may have changed |
| Hunter integration | NOT IMPLEMENTED (adapter spec only) |
| Verifalia integration | NOT IMPLEMENTED (adapter spec only) |
| External spend (observed) | NZ$0 |

## 6. Existing Test Results

| Test File | Result |
|-----------|--------|
| `money-machine/test_email_finder.py` | 16/16 PASSED |
| `money-machine/test_email_hardening.py` | 13/13 PASSED |
| `money-machine/test_lead_qualifier.py` | (subset run) PASSED |
| `money-machine/test_outreach.py` | 38/38 PASSED |
| `money-machine/test_polish.py` | 9/9 PASSED |
| `money-machine/test_acceptance.py` | 56/58 passed, 2 SKIPPED |
| **TOTAL** | **132 passed, 2 skipped** |

## 7. Existing Reports

| Report | Status |
|--------|--------|
| `reports/CURRENT_STATE.md` | Dated 2026-09-13, references older repo paths |
| `reports/OPEN_BLOCKERS.md` | 5 blockers documented |
| `reports/PILOT_001_RESULT.md` | Historical pilot result |
| `reports/EMAIL_FINDER_V2_FRESH_VALIDATION.md` | Historical validation |

## 8. Host Resources

| Resource | Value |
|----------|-------|
| OS | macOS 14.8.9 |
| CPU | Intel Core i5-5350U @ 1.80GHz |
| RAM | 8 GB |
| Disk | 113 GB total, 73 GB free (25% used) |
| Scheduler | Hermes gateway running — NOT a cron/launchd job for MM |

## 9. Backup & Rollback

| Item | Value |
|------|-------|
| Backup created | `backups/mm-v2-20260918T130156148789Z-221519/` |
| Backup integrity | Verified (22 businesses restored to /tmp) |
| Git checkpoint | `feature/rev30-execution` branch created |
| Rollback command | `git checkout master` |

## 10. Critical Path Forward

1. **P0 COMPLETE:** Baseline written, backup verified, tests passing, outbound locked.
2. **P1 VERTICAL SLICE:** Process one real business through deterministic pipeline.
3. **P1 BLOCKER:** No local Ollama model for demo copy generation (deterministic fallback available).
4. **NEXT TICKETS:** R02 (legacy contact), R03 (evidence qualification), R04 (unified offers).

## 11. Known Constraints

- No SSH keys or GitHub auth configured (clone worked after repo made public)
- `mm` operator requires `.venv-email` (created)
- External provider verification blocked until credentials/allowance configured
- Model inference blocked (no Ollama, no certified free remote)
- `mm email-find` returns POST_DEPLOYMENT_OBSERVATION (production persistence held)
- `mm outreach-plan` returns planning_holds without signals (correct behavior)

**END BASELINE**
