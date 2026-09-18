# REV30 BASELINE

**Generated:** 2026-09-19 00:50 NZST  
**Repository root:** `/Users/dd/WEBSITE-AUDITOR`  
**Spec pinned commit:** `454901b879016b4d967e6987d7e85e5e2edca94f`  
**Current HEAD:** `454901b879016b4d967e6987d7e85e5e2edca94f` (MATCHES SPEC)  
**Branch:** `master` — clean working tree  
**Remote:** `https://github.com/yabigdd-9/WEBSITE-AUDITOR.git`  

## 1. Repository Identity & Layout

| Item | Value |
|------|-------|
| Git remote | yabigdd-9/WEBSITE-AUDITOR |
| HEAD commit | 454901b |
| Working tree | clean |
| Symlinks | config, control-plane, migrations, scripts, tests → money-machine/ |
| Money-machine modules | mm_core, mm_email, mm_email_cli, mm_email_network, mm_email_store, mm_intelligence, mm_lead_qualifier, mm_lead_qualify, mm_outreach, mm_audit_workflow, mm_operator |
| Scripts dir | money-machine/scripts/ (supervisor, free_role_router, hermes_adapter, quality_controller, status, system_doctor, money_machine_auditor) |
| Root entrypoint | `mm` → `money-machine/mm` |

## 2. Active Database

| Item | Value |
|------|-------|
| Path | `database/money_machine.db` |
| Integrity | verified via backup/restore path |
| Businesses | 22 (10 HVAC, 9 renovation, 3 audited) |
| mm_jobs | 0 |
| Email candidates | 33 (UNVERIFIED/OBSERVED/CANDIDATE/SUPPRESSED) |
| Migrations | 3, 4, 5 applied |
| Email schema migrations | v3 applied (v4, v5 pending or pre-applied) |
| Suppression records | table exists, no standalone suppression.csv in outreach |

## 3. Runtime Environment

| Component | Status | Value |
|-----------|--------|-------|
| Python (system) | PRESENT | 3.9.6 |
| Python (project) | PRESENT | 3.11.16 (`/Users/dd/.local/bin/python3.11`) |
| Project venv | ABSENT | No `.venv-email` or `.venv` |
| pytest | ABSENT | Not installed |
| bs4/lxml/yaml/httpx/aiohttp | ABSENT | Not installed |
| Node | PRESENT | v26.9.0 |
| npm | PRESENT | 11.19.1 |
| Hermes CLI | PRESENT | v0.21.3 (2026.9.14), gateway running on localhost |
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
| Suppression active | Table exists, checked before draft/send |

## 5. Provider / Router State

| Component | State |
|-----------|-------|
| Free role router | PRESENT, BLOCKED (no API key, blocked_cost) |
| Hermes adapter | PRESENT, BLOCKED_COST (capability-only) |
| OpenRouter catalog | Stale (verified_utc 2026-09-09) — model IDs may have changed |
| Hunter integration | NOT IMPLEMENTED (adapter spec only) |
| Verifalia integration | NOT IMPLEMENTED (adapter spec only) |
| External spend (observed) | NZ$0 |

## 6. Existing Tests

| Test File | Can Run? |
|-----------|----------|
| `money-machine/test_email_finder.py` | NO — missing bs4/lxml |
| `money-machine/test_email_hardening.py` | NO — missing deps |
| `money-machine/test_email_integration.py` | NO — missing deps |
| `money-machine/test_lead_qualifier.py` | NO — missing deps |
| `money-machine/test_outreach.py` | NO — missing deps |
| `money-machine/test_polish.py` | NO — missing deps |
| `money-machine/test_acceptance.py` | NO — missing deps |

**Blocker:** Python dependencies and test runner not installed. This is the P0 first fix.

## 7. Existing Reports

| Report | Status |
|--------|--------|
| `reports/CURRENT_STATE.md` | Dated 2026-09-13, references older repo paths |
| `reports/OPEN_BLOCKERS.md` | 5 blockers documented (cost, review, approval, runtime, scope) |
| `reports/PILOT_001_RESULT.md` | Historical pilot result |
| `reports/EMAIL_FINDER_V2_FRESH_VALIDATION.md` | Historical validation |

## 8. Host Resources

| Resource | Value |
|----------|-------|
| OS | macOS 14.8.9 |
| CPU | Intel Core i5-5350U @ 1.80GHz |
| RAM | 8 GB |
| Disk | 113 GB total, 73 GB free (25% used) |
| Scheduler | Hermes gateway running (PID 83380) — NOT a cron/launchd job for MM |

## 9. Critical Path Summary

1. **P0 SAFETY:** Outbound is locked. No paid fallback. Database intact. Suppression active.
2. **P0 BLOCKER:** Python environment + test runner missing → `mm` CLI blocked, tests cannot run.
3. **P0 BLOCKER:** No local Ollama model, no certified free remote route → model tasks impossible.
4. **P1 GOAL:** One complete vertical slice on one real business.

## 10. Known Constraints

- No SSH keys or GitHub auth configured (clone worked after repo made public)
- `mm` operator blocked until `.venv-email` created or `MM_PYTHON` set
- Tests blocked until pytest + deps installed
- External provider verification blocked until credentials/allowance configured
- Model inference blocked (no Ollama, no certified free remote)

**END BASELINE**
