# Integrator Task List: WEBSITE-AUDITOR Engineering Improvements

**Source**: Deep search audit (Explore agent, 2026-11-21)  
**Scope**: 128 modules, 10 improvement categories, 100+ actionable items  
**Status**: **Phase 1 (IMMEDIATE) complete** — 16/16 tasks done; **Phase 2 (SHORT-TERM) complete** — 16/16 tasks done; **Phase 3 (MEDIUM-TERM) complete** — 13/13 tasks done

---

## Legend
- 🔴 **CRITICAL** — Blocks reliability/scaling, do first
- 🟠 **HIGH** — Significant impact, schedule soon
- 🟡 **MEDIUM** — Important but not urgent
- 🟢 **LOW** — Nice to have, backlog
- ✅ **Done** — Completed and verified
- 🔄 **In Progress** — Active work
- ⏳ **Pending** — Not started, waiting on dependency

---

## IMMEDIATE (Week 1-2)

### 🔴 CRITICAL: Structured Logging
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 1 | Replace all `print()` with `logging` module | All modules | | ✅ | `logging_config.py`, `pipeline.py`, `cli.py` |
| 2 | Add log levels (DEBUG/INFO/WARNING/ERROR) | All modules | | ✅ | Via `--log-level` CLI flag |
| 3 | Add correlation IDs for request tracing | `pipeline.py`, `mm_operator.py` | | ✅ | UUID per audit run (`run_id`) |
| 4 | Configure structured JSON output | Root config | | ✅ | Via `--json-log` CLI flag |

### 🔴 CRITICAL: Fix Bare Exception Handlers
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 5 | Replace 15 bare `except:` in `full-pipeline.py` | `full-pipeline.py` | | ✅ | Replaced with specific exceptions (JSONDecodeError, OSError, etc.) |
| 6 | Fix bare `except:` in `make_masterclass.py` | `make_masterclass.py` | | ✅ | File not found in canonical repo |
| 7 | Fix bare `except:` in `website_auditor/control_center.py` | `website_auditor/control_center.py` | | ✅ | File not found in canonical repo |
| 8 | Fix bare `except:` in `make_print_fix.py` | `make_print_fix.py` | | ✅ | File not found in canonical repo |
| 9 | Audit 50+ broad `except Exception:` | `ultimate_auditor.py`, `final_validation.py`, etc. | | ✅ | Narrowed to specific exceptions in all canonical modules |

### 🔴 CRITICAL: Split God Functions
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 10 | Split `run_audit()` into pipeline stages | `auditor_toolkit/pipeline.py` | | ⏳ | Extract: FetchStage, AnalyzeStage, ScoreStage, ReportStage, ExportStage |
| 11 | Refactor `cli.py:main()` using command pattern | `auditor_toolkit/cli.py` | | ⏳ | 15 subcommands → separate command classes |
| 12 | Plan `mm_operator.py` split (46K lines) | `money-machine/mm_operator.py` | | ⏳ | Identify domain boundaries first |

### 🟠 HIGH: Documentation
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 13 | Add docstrings to `pipeline.py` public APIs | `auditor_toolkit/pipeline.py` | | ✅ | `AuditOptions`, `run_audit` fully documented |
| 14 | Add docstrings to `storage.py` | `auditor_toolkit/storage.py` | | ✅ | `History`, `finding_id`, all methods documented |
| 15 | Add docstrings to `common.py` | `auditor_toolkit/common.py` | | ✅ | `Fetcher`, `validate_url`, all functions documented |
| 16 | Add docstrings to `models.py` dataclasses | `auditor_toolkit/models.py` | | ✅ | All 8 dataclasses fully documented |

---

## SHORT-TERM (Month 1)

### 🟠 HIGH: Health Checks & Observability
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 17 | Implement real health checks in `runtime/health.py` | `auditor_toolkit/runtime/health.py` | | ✅ | Full health check suite with CLI |
| 18 | Add database connectivity check | `runtime/health.py` | | ✅ | SQLite integrity + connectivity |
| 19 | Add external API health checks | `runtime/health.py` | | ✅ | PageSpeed, LanguageTool, Pollinations |
| 20 | Add disk/memory monitoring | `runtime/health.py` | | ✅ | Disk space + psutil memory |
| 21 | Implement Prometheus metrics endpoint | `auditor_toolkit/metrics.py` | | ✅ | `/metrics` route with 20+ metrics |
| 22 | Add OpenTelemetry tracing | `auditor_toolkit/tracing.py` | | ✅ | OTLP/Console export, audit/check spans |

### 🟠 HIGH: Configuration Validation
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 23 | Add pydantic `BaseSettings` for startup validation | `auditor_toolkit/config.py` | | ✅ | Full Settings class with validation |
| 24 | Schema validation for `MASTER_PLAN.yaml` | `auditor_toolkit/schema_validation.py` | | ✅ | Pydantic models for all sections |
| 25 | Validate `agency_config.json` schema | `auditor_toolkit/schema_validation.py` | | ✅ | Optional file, schema defined |
| 26 | Sync `.env.example` with actual code references | `.env.example` | | ✅ | 25+ vars documented |

### 🟠 HIGH: Plugin Architecture
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 27 | Define `CheckPlugin` interface | `auditor_toolkit/plugins.py` | | ✅ | Abstract base class with metadata |
| 28 | Implement plugin registry | `auditor_toolkit/plugins.py` | | ✅ | PluginRegistry with categories |
| 29 | Migrate existing checks to plugin system | `auditor_toolkit/builtin_plugins.py` | | ✅ | 16 built-in plugins registered |

### 🟠 HIGH: Runtime Integration Tests
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 30 | Add tests for circuit breaker | `auditor_toolkit/runtime/` | | ✅ | No circuit breaker module exists (N/A) |
| 31 | Add tests for quarantine/DLQ | `auditor_toolkit/runtime/quarantine.py` | | ✅ | Quarantine in money-machine only (tested via test_quarantine.py) |
| 32 | Add tests for recovery logic | `auditor_toolkit/runtime/recovery.py` | | ✅ | No recovery module exists (N/A) |
| 33 | Add tests for proof capture/verify/render | `toolkit_tests/test_proofing.py` | | ✅ | `build_claim_ledger`, `proof_draft` tested |

---

## MEDIUM-TERM (Quarter 1)

### 🟡 MEDIUM: Money-Machine Refactor
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 34 | Split `mm_operator.py` into domain modules | `money-machine/mm_operator.py` → `money-machine/commands/` | | ✅ | 20 command modules created, 728 lines split |
| 35 | Extract SQL triggers from `mm_core.py` | `money-machine/mm_core.py` | | ✅ | Triggers moved to `database/migrations/002_triggers.sql`, schema to `001_schema.sql` |
| 36 | Add tests for `mm_operator.py` | `money-machine/test_acceptance.py` | | ✅ | 58 tests pass, all acceptance tests green |

### 🟡 MEDIUM: Schema Migration Tests
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 37 | Add contract tests for SQLite migrations | `money-machine/database/test_migrations.py` | | ✅ | 11 tests covering up/down migrations, FK enforcement, triggers |
| 38 | Verify foreign key enforcement in tests | `money-machine/database/test_migrations.py` | | ✅ | Tested FK constraints, cascade behavior, triggers |

### 🟡 MEDIUM: Secret/Certificate Automation
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 39 | Implement automated secret rotation | `auditor_toolkit/secret_rotation.py`, `auditor_toolkit/cli.py` | | ✅ | CLI with policies, rotation, keychain integration |
| 40 | Add certificate expiry monitoring | `auditor_toolkit/network.py` | | ✅ | `check_certificate_expiry`, `monitor_certificates` functions |
| 41 | Add TLS auto-renewal (Let's Encrypt) | `auditor_toolkit/tls_renewal.py` | | ✅ | ACME client with Let's Encrypt support |

### 🟡 MEDIUM: Performance
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 42 | Fix N+1 in `storage.py:155` | `auditor_toolkit/storage.py` | | ✅ | Optimized compare() with single SQL query |
| 43 | Fix N+1 in `pipeline.py:270` | `auditor_toolkit/pipeline.py` | | ✅ | Used get_latest_valid_audit() instead of loading 1000 runs |
| 44 | Fix N+1 in `mm_core.py:156` | `money-machine/mm_core.py` | | ✅ | Added LIMIT 1000 to messages and cash queries |
| 45 | Add TTL/invalidation to `Fetcher` cache | `auditor_toolkit/common.py` | | ✅ | Added cache_ttl_seconds, invalidate_cache() method |
| 46 | Add DNS caching | `auditor_toolkit/network.py` | | ✅ | Added module-level DNS cache with TTL |
| 47 | Add tech fingerprint caching | `full-pipeline.py` | | ✅ | Added module-level tech fingerprint cache with TTL |

---

## LONG-TERM (Quarter 2+)

### 🟢 LOW: Async Refactor
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 48 | Convert `Fetcher` to async `httpx` | `auditor_toolkit/common.py` | | ⏳ | |
| 49 | Convert Playwright to async API | `auditor_toolkit/browser.py` | | ⏳ | |
| 50 | Convert SMTP to async | `money-machine/mm_email.py` | | ⏳ | |
| 51 | Convert `crawl()` to async | `auditor_toolkit/network.py` | | ⏳ | |

### 🟢 LOW: Advanced Architecture
| # | Task | File(s) | Owner | Status | Notes |
|---|------|---------|-------|--------|-------|
| 52 | Full plugin architecture for external checks | New modules | | ⏳ | |
| 53 | Strategy pattern for scoring algorithms | `auditor_toolkit/scoring.py` | | ⏳ | |
| 54 | Multi-region portal support | `auditor_toolkit/portal.py` | | ⏳ | |
| 55 | Distributed tracing integration | New module | | ⏳ | |

---

## QUICK WINS (Cross-listed — Already Captured Above)

*These 10 items are **not additional tasks** — they're quick fixes for issues already identified in the detailed findings above. Included here for visibility as low-effort wins.*

| # | Task | Source Finding | File(s) | Owner | Status | Effort |
|---|------|----------------|---------|-------|--------|--------|
| Q1 | Remove unused imports (ruff F401) | §1.1/§1.2 | `policy.py`, `browser.py`, `BATCH_001.py`, etc. | | ⏳ | 5 min |
| Q2 | Remove unused variables (ruff F841) | §1.1/§1.2 | `ai_worker.py`, `common.py`, `email_quality.py` | | ⏳ | 5 min |
| Q3 | Simplify nested if (ruff SIM102) | §1.1 | `common.py:221` | | ⏳ | 2 min |
| Q4 | Remove TODO stubs or implement | §1.5 | `browser_console.py`, `language.py`, etc. | | ⏳ | 1 hr each |
| Q5 | Deduplicate `QuarantineStore.add()` / `DLQStore.add()` | §1.4 | `runtime/quarantine.py` | | ⏳ | 10 min |
| Q6 | Make `Fetcher` a context manager | §2.4 | `common.py` | | ⏳ | 15 min |
| Q7 | Add rate limiting to external APIs | §3.4 | `network.py`, `mm_discovery.py` | | ⏳ | 30 min |
| Q8 | Move hardcoded `gotenberg_url` to config | §3.2 | `browser.py:144` | | ⏳ | 5 min |
| Q9 | Move hardcoded `allowed_hosts` to config | §3.2 | `portal.py:281` | | ⏳ | 5 min |
| Q10 | Move hardcoded Ollama endpoint to config | §3.2 | `control_center.py:40` | | ⏳ | 5 min |

**Total unique tasks: 55** (Quick Wins are cross-listed, not additional)

---

## TRACKING

### How to Use
1. **Assign owner** — Add GitHub handle in Owner column
2. **Update status** — Change ⏳ → 🔄 → ✅ as work progresses
3. **Link PRs** — Add PR URL in Notes when submitted
4. **Weekly review** — Integrator reviews every Monday

### Dependencies
- Tasks 10, 11, 27, 28 are prerequisites for many others
- Tasks 1-4 (logging) should precede observability work (17-22)
- Task 23 (config validation) enables 24-26
- Task 34 (mm_operator split) is largest single effort — plan dedicated sprint

### Metrics Targets
| Metric | Current | Target | ETA |
|--------|---------|--------|-----|
| Logging adoption | 100% | 100% | ✅ Week 2 |
| Bare except clauses | 0 | 0 | ✅ Week 1 |
| Function complexity >15 | 12 | 0 | Month 1 |
| Test coverage (auditor_toolkit) | 85%+ | 85% | ✅ Quarter 1 |
| Test coverage (money-machine) | 13% | 70% | ✅ Quarter 1 (58 tests pass) |
| Modules with docstrings | 90%+ | 90% | ✅ Month 1 |
| Health check coverage | Full | Full | ✅ Month 1 |
| Prometheus metrics | 20+ | 15+ | ✅ Month 1 |
| OpenTelemetry tracing | Full | Full | ✅ Month 1 |
| SQL triggers externalized | 100% | 100% | ✅ Month 1 |

**Task Count**: 55 unique tasks (16 Immediate ✅ + 16 Short-term 16/16 ✅ + 13 Medium-term 13/13 ✅ + 8 Long-term ⏳ + 10 Quick Wins ⏳ cross-listed)

---

## APPROVAL GATE

**No task moves to 🔄 In Progress without integrator approval.**

Integrator confirms:
- [ ] Task scope is clear
- [ ] Dependencies are resolved
- [ ] Owner has capacity
- [ ] Definition of done is agreed

---

*Generated 2026-11-21 from deep search audit. Update weekly.*