---
title: "WEBSITE-AUDITOR — Deep Upgrade / Optimization / Tool Discovery Report"
version: "2.0.0"
date: "2026-09-21"
status: "RESEARCH COMPLETE — READY TO IMPLEMENT"
cost_target: "NZD $0/month operating cost"
platform: "macOS (Apple Silicon) + Docker"
priority_order: "free > open-source > self-hostable > local-first > lightweight"
legend:
  verdicts: ["INSTALL NOW", "TEST", "OPTIONAL", "REJECT"]
  difficulty: ["Easy", "Medium", "Hard"]
  priorities: ["P0 (this week)", "P1 (this month)", "P2 (this quarter)", "P3 (someday)"]
---

# WEBSITE-AUDITOR — Deep Upgrade, Optimization & Tool Discovery Report

> **Scope:** Full ecosystem scan + architecture redesign of the WEBSITE-AUDITOR / Money-Machine
> pipeline: *discover → identify → contact → verify → audit → score → recommend → mockup →
> quote → outreach → track → learn → improve.*

## Current state (verified by code inspection)

- Strong deterministic core: `mm_pipeline.py` state machine (leased work queue, circuit
  breakers, exponential backoff, dead-letter states, append-only `pipeline_events`).
- 25+ audit checks (`website_auditor.py`), Playwright browser lane with axe-core
  (`auditor_toolkit/browser.py`), history SQLite with immutable runs.
- Zero-cost model router (`mm_model_router.py`): local llama.cpp/Ollama → OpenRouter `:free`
  → `BlockedCost`. Schema constrains `cost_usd = 0`. ✅ Excellent — keep.
- Approval gates (`approval_gates.yaml`): external send denied by default, per-message
  approval, suppression list, compliance gate in outreach engine. ✅ Keep and extend.
- Gaps: no business *discovery* engine (prospects are hand-seeded), no entity resolution,
  single SMTP-probing-disabled email verification, no real monitoring/alerting, no
  eval/self-improvement harness, secrets on disk (2 keys already exposed per
  `UPGRADE_PLAN.md` — **ROTATE if not done**), 3 near-duplicate pipeline implementations
  (`full-pipeline.py`, `ultimate_auditor.py`, `website_auditor_enhanced.py`) plus a
  duplicated `control-plane/` vs `money-machine/` tree.

---

## 1. TOP 25 HIGHEST-VALUE UPGRADES

| # | Upgrade | Stage | Verdict | Difficulty | Cost |
|---|---------|-------|---------|-----------|------|
| 1 | **Litestream** (continuous SQLite replication/backup; verified: active, Apache-2.0, file/S3/SFTP destinations) | Data | INSTALL NOW | Easy | Free (Apache-2.0) |
| 2 | **SOPS + age** secrets management (kill plaintext keys) | Security | INSTALL NOW | Easy | Free (MPL) |
| 3 | **Uptime Kuma** monitoring + **ntfy** push alerts | Monitoring | INSTALL NOW | Easy | Free (MIT) |
| 4 | **Overture Maps places** (verified: CDLA-Permissive-2.0/Apache-2.0 — no share-alike; ~59M+ businesses incl. websites/categories; monthly releases; query direct from S3 GeoParquet with DuckDB, zero download) + **OSM/Overpass** as live complement | Discovery | INSTALL NOW | Medium | Free (permissive) |
| 5 | **NZBN API** (verified free: register at api.business.govt.nz; returns legal name, addresses, status, watchlist/change alerts) + **Companies Office** register | Discovery/Identity | INSTALL NOW | Easy | Free (NZ Govt open API) |
| 6 | **Splink 4** entity resolution (verified: MIT, DuckDB backend, links ~1M records/min on a laptop, unsupervised — no training data needed; actively maintained by UK MoJ) | Identity | INSTALL NOW | Medium | Free (MIT) |
| 7 | **Lighthouse CI** batch audits (lab Core Web Vitals, budgets, history) | Auditing | INSTALL NOW | Easy | Free (Apache) |
| 8 | **lychee** broken-link checker (Rust, 50–100× faster than a Python loop) | Auditing | INSTALL NOW | Easy | Free (MIT/Apache) |
| 9 | **testssl.sh** + **OWASP ZAP baseline** (replace hand-rolled TLS/header checks) | Security audit | INSTALL NOW | Easy | Free |
| 10 | **promptfoo** eval harness (regression-test all prompts/models) | Self-improvement | INSTALL NOW | Medium | Free (MIT, self-host) |
| 11 | **Dozzle** live Docker log viewer (replaces grep-the-JSONL debugging) | Monitoring | INSTALL NOW | Easy | Free (MPL) |
| 12 | **CrUX API + PageSpeed Insights API** (field CWV data, ~25k/day free quota) | Auditing | INSTALL NOW | Easy | Free w/ key |
| 13 | **Qwen3 / Gemma 3 local model refresh** via Ollama (llama-2-7b is badly outdated) | AI reasoning | INSTALL NOW | Easy | Free |
| 14 | **sqlite-vec** embeddings + local `bge-small`/`gte-small` for semantic dedupe & evidence search | Data/AI | TEST | Medium | Free |
| 15 | **changedetection.io** (watch directories/competitor sites/prospect pages for changes) | Discovery/Monitoring | TEST | Easy | Free (Apache) |
| 16 | **Hatchet or Dramatiq+Valkey** if/when the custom queue outgrows SQLite leases (not yet — see §6) | Workflow | OPTIONAL | Medium | Free |
| 17 | **Typst** for quotes/proposals/PDF reports (faster, better typography than HTML-print) | Quotes/Reports | TEST | Medium | Free (Apache/MIT) |
| 18 | **Reacher / check-if-email-exists** self-host verifier (catch-all, disposable, MX, SMTP) as consensus next to Verifalia free tier. Verified: actively maintained (9.9k★, monorepo `reacherhq/check-if-email-exists`, Docker `reacherhq/backend`), dual AGPL-3.0/commercial — free for internal use; needs outbound port 25 (residential ISPs often block it — test first) | Email verification | TEST | Medium | Free (AGPL-3.0, internal use) |
| 19 | **disposable-email-domains** + **mailchecker** blocklists (you have a static conf — automate refresh) | Email verification | INSTALL NOW | Easy | Free |
| 20 | **mailpit** (Docker SMTP catch-all for safe end-to-end outreach testing) | Outreach safety | INSTALL NOW | Easy | Free (MIT) |
| 21 | **GlitchTip** (self-hosted Sentry-compatible error tracking) | Monitoring | TEST | Easy | Free (MIT) |
| 22 | **OpenTelemetry traces** only if needed; otherwise structured JSONL + Dozzle is enough | Observability | OPTIONAL | Hard | Free |
| 23 | **Apprise** (one lib → 100+ alert channels: ntfy/Gotify/Telegram/email) for watchdog alerts | Reliability | INSTALL NOW | Easy | Free (MIT) |
| 24 | **Langfuse (self-host)** LLM observability — trace/score every model invocation, feeds the improvement loop | Self-improvement | TEST | Medium | Free (MIT self-host) |
| 25 | **browser-use / Playwright-MCP** for agentic browsing research (behind sandbox + egress allowlist) | Research agents | TEST | Medium | Free |


---

## 2. TOP 10 TOOLS TO INSTALL IMMEDIATELY

```bash
# 1. Backups — continuous SQLite replication to local dir (or free R2/B2 tier)
brew install litestream
litestream replicate database/money_machine.db file://$PWD/backups/mm

# 2. Secrets — stop storing keys in ~/.zshrc / git
brew install sops age
age-keygen -o ~/.config/sops/age/keys.txt
sops config/secrets.enc.yaml

# 3. Broken links (Rust binary, chews whole sites in seconds)
brew install lychee
lychee --max-concurrency 16 --exclude-mail https://example.co.nz

# 4. TLS/security headers done properly
brew install testssl
testssl --jsonfile out.json example.co.nz

# 5. Lighthouse CI
npm i -g @lhci/cli
lhci autorun --collect.url=https://example.co.nz

# 6. Blocklist auto-refresh (replaces static disposable_email_blocklist.conf)
curl -sL https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf \
  -o config/disposable_email_blocklist.conf   # cron weekly

# 7. Mailpit — safe SMTP sandbox
docker run -d --name mailpit -p 8025:8025 -p 1025:1025 axllent/mailpit

# 8. Uptime Kuma + ntfy alerts
docker run -d --name kuma -p 3001:3001 louislam/uptime-kuma
docker run -d --name ntfy -p 8086:80 binwiederhier/ntfy serve

# 9. Dozzle — live container/pipeline logs
docker run -d --name dozzle -p 8888:8080 -v /var/run/docker.sock:/var/run/docker.sock amir20/dozzle

# 10. Modern local models (llama-2-7b in auditor_toolkit/ai.py is from 2023 — replace)
ollama pull qwen3:8b          # reasoning/planning/judging
ollama pull qwen2.5-coder:7b  # coding
ollama pull gemma3:4b         # fast classification/extraction
ollama pull qwen3:4b-instruct # tool calling
```

---

## 3. BEST FREE/LOCAL AI MODEL STACK BY AGENT ROLE

Hardware assumption: Apple Silicon, 16–32 GB unified memory. All via Ollama/llama.cpp (GGUF/MLX, Q4_K_M or 4-bit MLX). **$0 forever, offline-capable.**

| Role | Primary (local) | Fallback (local, smaller) | Emergency external (free) | RAM |
|------|----------------|---------------------------|---------------------------|-----|
| Planner / Orchestrator | `qwen3:14b` (if 32GB) else `qwen3:8b` | `qwen3:4b` | OpenRouter `:free` (existing router ✅) | ~10 GB |
| Coder | `qwen2.5-coder:7b` | `qwen2.5-coder:3b` | existing OpenRouter free route | ~5 GB |
| Extraction / Classification (bulk) | `gemma3:4b` | `gemma3:1b` | n/a (must stay local, high volume) | ~3 GB |
| Judge / Critic | `qwen3:8b` — different family from drafter (your routing.yaml already requires distinct-model review ✅) | `phi4-mini` | OpenRouter free | ~6 GB |
| Proofreading | deterministic first: **LanguageTool self-hosted Docker** (`erikvl87/languagetool`) — the pipeline currently calls public api.languagetool.org (rate-limited); self-host removes that | `gemma3:1b` for style | — | ~1 GB |
| Vision (screenshot/design analysis) | `qwen2.5vl:7b` | `gemma3:4b` (vision) | OpenRouter free vision | ~6 GB |
| Tool calling / agents | `qwen3:4b-instruct` | `llama3.2:3b` | — | ~3 GB |
| Embeddings (dedupe/evidence search) | `bge-small-en-v1.5` or `nomic-embed-text` via Ollama + sqlite-vec | — | — | <1 GB |

**Key change:** delete the pinned `llama-2-7b-chat.Q4_K_M.gguf` integrity check in
`auditor_toolkit/ai.py` and generalise `verify_model()` to a manifest of approved models
(name → sha256) so models rotate without code edits.

**KEEP:** `mm_model_router.py` policy (local → free-external → `BlockedCost`,
`cost_usd=0` schema constraint, invocation logging). Already best-in-class for a $0 system.


---

## 4. RECOMMENDED DOCKER SERVICE STACK

Minimal, ~3 GB RAM total idle. Single `docker-compose.yml`:

```yaml
services:
  searxng:        # private meta-search for discovery (containerize what you already use)
    image: searxng/searxng:latest
    ports: ["8080:8080"]
  languagetool:   # self-hosted proofreading (no public-API rate limit)
    image: erikvl87/languagetool:latest
    ports: ["8010:8010"]
  mailpit:        # SMTP sandbox for outreach testing
    image: axllent/mailpit:latest
    ports: ["8025:8025", "1025:1025"]
  kuma:           # uptime + cron-job heartbeat monitoring
    image: louislam/uptime-kuma:1
    volumes: ["kuma:/app/data"]
    ports: ["3001:3001"]
  ntfy:           # push alerts to phone/desktop
    image: binwiederhier/ntfy:latest
    command: serve
    ports: ["8086:80"]
  dozzle:         # live log viewer
    image: amir20/dozzle:latest
    volumes: ["/var/run/docker.sock:/var/run/docker.sock"]
    ports: ["8888:8080"]
  changedetection: # watch directories/competitors/prospect sites
    image: ghcr.io/dgtlmoon/changedetection.io:latest
    ports: ["5000:5000"]
    volumes: ["cd-data:/datastore"]
volumes: { kuma: {}, cd-data: {} }
```

**Deferred (only if scale demands):** `langfuse` (LLM traces), `glitchtip` (error tracking — needs small postgres sidecar), `zap` (run as a weekly job, not a service), `meilisearch` (only if >50k businesses), `postgresql+pgvector` (only if SQLite concurrency actually becomes the bottleneck — measure first).

**Rejected for $0/self-host fit:** n8n (fair-code license; `mm_pipeline` is already better orchestration), Temporal (heavyweight), Prometheus+Grafana (overkill vs Kuma+Dozzle), Portainer (nice-to-have only).

---

## 5. RECOMMENDED MCP / PLUGIN STACK

MCP servers that give the local agent stack safe, structured access — all local, all free:

| MCP Server | Purpose | Verdict |
|------------|---------|---------|
| **playwright-mcp** (`@playwright/mcp`) | Agentic browsing/screenshots for research agents | INSTALL (sandbox + egress allowlist) |
| **fetch MCP** (official) | Guarded HTTP fetch for agents | INSTALL |
| **sqlite MCP** (official) | Read-only DB introspection for agents | INSTALL (read-only!) |
| **filesystem MCP** (official, scoped to `outputs/`) | Artifact read/write | INSTALL (scope tightly) |
| **github MCP** | Issue/PR automation for remediation delivery | TEST |
| **memory MCP** | Cross-run agent memory (knowledge graph) | TEST |
| **SearXNG MCP** (community) | Search access for researcher agents | TEST |
| sequential-thinking / most others | Marginal vs prompt discipline | REJECT for now |

**Repo plugin system** (`plugins/`): keep the pattern; add `lychee_runner.py`,
`lighthouse_runner.py`, `testssl_runner.py`, `splink_resolver.py`, `crux_fetcher.py`
as plugins rather than core edits.


---

## 6. IMPROVED WORKFLOW ARCHITECTURE

**Do NOT adopt Celery/Temporal/Hatchet yet.** The `mm_pipeline.py` leased-queue state
machine on SQLite is genuinely good and exactly right for this scale. Upgrade it instead:

1. **Keep the state machine; fix the missing discovery entry point.** Add a `DISCOVERY`
   worker feeding the `DISCOVERED` state from: Overpass/Overture queries (niche × region
   grid), NZBN/Companies Office lookups, SearXNG directory scraping, changedetection.io webhooks.
2. **Concurrency model:** stage leases already allow N parallel workers per stage. Run:
   4× discovery, 2× audit (Playwright is RAM-hungry), 4× email-finder (concurrency
   currently 1 in `email_finder.json` — raise to 3 with per-domain politeness),
   1× outreach-draft, 1× QA/judge. All as `mm run-worker <stage> --concurrency N` under
   the SupervisorDaemon from the CONTINUITY plan (P0.1).
3. **Cron/scheduling:** `ofelia` Docker cron or a `launchd` plist for: nightly discovery
   sweep, weekly blocklist refresh, weekly Lighthouse re-audit of converted clients,
   daily Litestream backup verify, hourly `mm run-pipeline` tick.
4. **Resumability:** already present (`.pipeline-state.json` + leased queue). Extend the
   resume pattern to the *browser* stage (cache rendered DOM 24h like HTTP responses).

---

## 7. PARALLEL WORKER / AGENT DESIGN

```
                    ┌──────────────────────────────┐
                    │  SupervisorDaemon (P0.1)     │
                    │  PID lock, log rotate, beats │
                    └──────────────┬───────────────┘
        ┌──────────────┬───────────┼────────────┬───────────────┐
        ▼              ▼           ▼            ▼               ▼
   Discovery(4)   Identity(2)   Audit(2)    Contact(4)      Outreach(1)
   OSM/Overture   Splink dedupe Static+PW   email-finder    drafts only
   NZBN/COS       canonical dom Lighthouse  Verifalia+      ComplianceGate
   SearXNG        NZBN match    lychee      Reacher consens + ApprovalGate
        └──────────────┴───────────┴────────────┴───────────────┘
                              ▼
                 Judge/QA (1, distinct model)
                              ▼
                 APPROVAL_PENDING (human, per-message)
```

Rules (already in your configs — enforce in code everywhere): no recursive spawning,
proof-required-before-complete, judge ≠ creator model, role responses never touch CRM/send.

---

## 8. SELF-IMPROVEMENT LOOP

```
outcomes (replies, conversions, bounces, complaints)
   → labelled dataset in SQLite (outcome per prospect id)
   → promptfoo eval suite (nightly, local models, $0):
       • extraction accuracy vs hand-labelled gold set (50 businesses)
       • outreach-draft quality rubric scored by judge model
       • audit-finding precision/recall vs manual review sample
   → regression gate: new prompt/model must not drop any metric >2%
   → weekly report: which scoring weights in lead_scoring.py predict replies?
       (logistic regression on outcomes → auto-suggest INDUSTRY_WEIGHTS deltas)
   → Langfuse (optional): trace every model call, tag with prospect outcome
```

Concretely: create `evals/` with (a) `gold_emails.jsonl` — 50 manually verified
contacts, (b) `gold_audit.jsonl` — 20 manually verified findings, (c) `promptfoo.yaml`
wired to Ollama, (d) CI step `promptfoo eval` on every prompt change.


---

## 9. RELIABILITY / FAILOVER DESIGN

- **Circuit breakers:** you have them — add per-source breakers for Overpass/SearXNG/PSI
  with `tenacity` + `pybreaker`, and a **fallback chain** per stage (maps: Overpass →
  Overture parquet → SearXNG; verification: Verifalia → Reacher → DNS+SMTP-lite → mark
  UNVERIFIED, never guess).
- **Rate limiting:** token bucket per external host (`limits` lib); Overpass = politeness
  1 rps, round-robin 3 public instances.
- **Crash recovery:** leased jobs auto-expire (you have this) + supervisor heartbeats +
  Docker `restart: unless-stopped` + `launchd` KeepAlive for the host-level daemon.
- **Offline-first:** every stage must degrade to cached data (you cache HTTP 24h — extend
  to DNS/MX and CrUX/PSI responses for 7d).
- **Alerting:** Apprise → ntfy for: queue depth > X for 1h, dead-letter growth,
  disk < 10%, Litestream lag, model endpoint down.
- **Self-heal:** watchdog cron runs `mm doctor` (extend existing `health()`): checks
  leases, breakers, model endpoints, DB integrity (`PRAGMA integrity_check`), and
  auto-remediates known issues (restart worker, clear expired leases, requeue stale
  RETRYABLE_FAILURE).

---

## 10. SECURITY & SECRET-MANAGEMENT UPGRADES

1. **Rotate now if not done:** `PAGESPEED_API_KEY`, `RANKNIBBLER_API_KEY` (exposed per UPGRADE_PLAN.md).
2. **SOPS+age** for all secrets; `sops exec-env` to inject into pipeline env. Delete keys from `~/.zshrc`.
3. **gitleaks** pre-commit + CI (`brew install gitleaks`); blocklist: `config/`, `*.db`, `state/`.
4. **Browser agents sandbox:** Playwright with egress allowlist (you already block non-GET —
   extend to a domain allowlist for agentic browsing), no persisted cookies, separate Docker
   network with no LAN access.
5. **Prompt-injection defense for crawled content:** treat all page text as untrusted — wrap
   in delimiters, never let page content reach tool-calling context, strip scripts/instructions
   before LLM ingestion (trafilatura helps — keep it).
6. **Dependency hygiene:** `pip-audit` in CI, pin with `uv lock`, weekly Dependabot/Renovate.
7. **DB at rest:** SQLite file perms 600; Litestream backups age-encrypted.

---

## 11. THINGS CURRENTLY MISSING

| Missing | Impact | Fix |
|---|---|---|
| Real business discovery engine | Pipeline is feed-starved (hand-seeded prospects) | §1 #4–5 |
| Entity resolution / dedupe | Duplicate businesses across sources → double outreach (reputation risk) | Splink |
| Second email verifier / consensus | Single point of failure + Verifalia free-tier cap (~25/day) | Reacher self-host + DNS/SMTP-lite |
| Catch-all domain detection | False "verified" emails | Reacher `is_catch_all` + MX heuristics |
| Field CWV data | Lab-only performance claims (weak sales evidence) | CrUX/PSI API (free) |
| Eval harness / gold datasets | No way to know if changes help or hurt | §8 |
| Log rotation & alerting | Disk growth; silent failures | Dozzle + logrotate (CONTINUITY P0.3) + Apprise |
| Secrets manager | Two keys already burned | §10 |
| Model manifest system | Pinned 2023 model blocks upgrades | §3 |
| Bounce/reply ingestion | No feedback loop for self-improvement | IMAP poller → outcomes table |
| Canonical pipeline entrypoint | 3+ competing pipeline scripts confuse everything | §12 |


---

## 12. THINGS TO REMOVE OR REPLACE

| Remove/Replace | Why | With |
|---|---|---|
| `llama-2-7b` pinned model | 2023 model, far weaker than free 2026 alternatives | qwen3/gemma3 manifest (§3) |
| `full-pipeline.py` vs `ultimate_auditor.py` vs `website_auditor_enhanced.py` triplication | 3 divergent pipelines = bugs fixed 3× or not at all | One: `auditor_toolkit` as the engine, thin CLI wrappers |
| `control-plane/` vs `money-machine/` duplicate tree (identical file lists) | Drift hazard — pick one, archive the other to `_archive/` | `money-machine/` |
| Public `api.languagetool.org` calls | Rate-limited, sends text externally | self-hosted LanguageTool container |
| Hand-rolled TLS/header checks | testssl.sh + ZAP are deeper and maintained | plugins wrapping them |
| Static disposable-domain list | Stales within weeks | weekly auto-refresh from upstream repo |
| Python broken-link loop | Slow, error-prone | lychee |
| n8n | Fair-code license, overlaps mm_pipeline | remove `automation/n8n` or mark optional |

---

## 13. STEP-BY-STEP IMPLEMENTATION ORDER

**Week 1 (P0 — safety & backups):**
1. Rotate exposed keys; adopt SOPS+age; gitleaks in pre-commit.
2. Litestream backup job + verify restore (`litestream restore` drill).
3. Docker stack up: kuma, ntfy, dozzle, mailpit, languagetool (§4 compose).
4. Model refresh: pull qwen3/gemma3 set, generalise `verify_model()` to manifest, rerun draft tests.
5. Archive `control-plane/` duplicate; designate `auditor_toolkit` as sole engine.

**Week 2–3 (P1 — feed the machine):**
6. Discovery worker: Overpass grid (niche×suburb) → NZBN validation → `DISCOVERED`.
7. Splink dedupe between discovery and queue insert.
8. lychee + testssl + Lighthouse CI plugins into audit stage; CrUX/PSI field data.
9. Blocklist auto-refresh cron; Reacher self-host experiment (consensus verifier).

**Month 2 (P2 — intelligence):**
10. Eval harness: gold datasets + promptfoo nightly.
11. Bounce/reply ingestion → outcomes table → scoring-weight tuner.
12. changedetection.io monitors; Apprise alerting everywhere.
13. Typst quote/proposal renderer.

**Quarter (P3 — scale):**
14. sqlite-vec semantic search; Langfuse if model-call volume justifies.
15. browser-use research agent (sandboxed) for prospect deep-dives.
16. Consider Postgres/Meilisearch only on measured pain.


---

## 14. COMMANDS / CONFIG EXAMPLES

```bash
# Discovery sweep (Overpass, plumbers in Christchurch) — politeness 1 rps
curl -sG 'https://overpass-api.de/api/interpreter' \
  --data-urlencode 'data=[out:json];nwr["craft"="plumber"](-43.7,172.4,-43.3,172.9);out center;' \
  -o state/discovery/overpass_plumbers_chch.json

# Splink dedupe
pip install splink duckdb
python -m scripts.dedupe_businesses --in db/businesses.parquet --out db/businesses_deduped.parquet

# Lighthouse batch (lab CWV, all HOT leads)
lhci collect --url=https://example.co.nz --numberOfRuns=3 && lhci upload --target=filesystem

# Field data (CrUX — 25k free queries/day with API key)
curl "https://chromeuxreport.googleapis.com/v1/records:queryRecord?key=$PSI_KEY" \
  -d '{"url":"https://example.co.nz"}'

# Eval gate on prompt change
npx promptfoo@latest eval -c evals/promptfoo.yaml --env OLLAMA_BASE_URL=http://127.0.0.1:11434

# Weekly crons (ofelia in compose): blocklist refresh, lighthouse client re-audit,
# litestream verify, gold-eval run
```

---

## 15. FINAL OPTIMIZED ARCHITECTURE DIAGRAM

```
┌──────────────────────────────────────────────────────────────────────────┐
│ SUPERVISION: SupervisorDaemon (PID/logrotate/heartbeats) + launchd       │
│ OBSERVE:     Uptime Kuma · Dozzle · GlitchTip · Apprise→ntfy             │
│ SECRETS:     SOPS+age (age-encrypted, never on disk in plaintext)        │
│ DATA:        SQLite WAL + Litestream (encrypted backups) + sqlite-vec    │
├──────────────────────────────────────────────────────────────────────────┤
│ DISCOVERY (4x)     IDENTITY (2x)      AUDIT (2x)        CONTACT (4x)     │
│ Overpass/Overture  Splink dedupe      static checks     contact crawl    │
│ NZBN / Companies   canonical domain   Playwright+axe    email permutate  │
│ Office (free APIs) NZBN match         Lighthouse CI     Verifalia +      │
│ SearXNG (selfhost) provenance log     lychee, testssl   Reacher consens- │
│ changedetection →                     CrUX/PSI field    us + catch-all   │
│ webhooks                              (25k/day free)    MX/DNS/disposable│
├────────────────────── leased-queue state machine (mm_pipeline) ──────────┤
│ SCORE → QUOTE → MOCKUP(qwen2.5vl review) → OUTREACH DRAFT (gemma/qwen    │
│ local) → JUDGE (distinct model) → ComplianceGate → APPROVAL_PENDING      │
│ (human per-message) → Gmail/SMTP (mailpit in dev) → outcomes ingested    │
│ via IMAP poller → eval loop (promptfoo gold sets, weight tuner, prompt   │
│ A/B) → feeds back into SCORE weights & prompt library                    │
└──────────────────────────────────────────────────────────────────────────┘
   Every external call: token-bucket rate limit + circuit breaker +
   cached fallback + BlockedCost (never silently paid)
```

---

## 16. PRIORITIZED BACKLOG

### P0 — this week (safety)
- [ ] Rotate `PAGESPEED_API_KEY`, `RANKNIBBLER_API_KEY`; adopt SOPS+age; gitleaks CI
- [ ] Litestream backups + restore drill
- [ ] Deploy core Docker stack (kuma, ntfy, dozzle, mailpit, languagetool)
- [ ] Replace llama-2-7b with qwen3/gemma3 manifest; rerun tests
- [ ] Archive `control-plane/` duplicate; single engine = `auditor_toolkit`

### P1 — this month (feed & verify)
- [ ] Overpass/Overture discovery worker + NZBN/Companies-Office validation
- [ ] Splink entity resolution before queue insert
- [ ] lychee / testssl / Lighthouse-CI / CrUX plugins
- [ ] Disposable blocklist auto-refresh; Reacher consensus verifier (TEST)
- [ ] SupervisorDaemon + logrotate + watchdog `mm doctor` (from CONTINUITY plan)

### P2 — this quarter (intelligence)
- [ ] Gold datasets + promptfoo nightly evals + regression gate
- [ ] IMAP outcome ingestion → scoring-weight auto-tuner
- [ ] changedetection.io monitors; Apprise alerting
- [ ] Typst quotes/proposals; qwen2.5vl mockup review lane

### P3 — someday (scale)
- [ ] sqlite-vec semantic evidence search; Langfuse LLM observability
- [ ] browser-use research agent (sandboxed, egress allowlist)
- [ ] Postgres/pgvector + Meilisearch migration (only on measured need)
- [ ] DSPy/GEPA prompt auto-optimization once eval harness is stable

---

*Cost audit: every item above is free/open-source or within a verified free tier
(CrUX/PSI ~25k req/day; Verifalia ~25 credits/day free). Nothing in this plan can
silently create charges — any future paid consideration must fail closed via the
existing `BlockedCost` + approval-gate pattern.*


---

## 17. VERIFIED FACTS (checked against primary sources 2026-09-21)

Key claims in this report verified against official sources:

| Claim | Source | Result |
|---|---|---|
| Reacher self-host email verifier | github.com/reacherhq/backend | ⚠️ `reacherhq/backend` repo **ARCHIVED Dec 2024**; active code is monorepo `reacherhq/check-if-email-exists`. Dual license **AGPL-3.0 / commercial** — free for internal use as an isolated Docker service; do not embed in proprietary distributed code. Needs outbound SMTP port 25 (often blocked on residential connections — test before relying on it). Verdict stays **TEST**, not INSTALL NOW. |
| NZBN API free | nzbn.govt.nz | ✅ Confirmed "free to connect to and use" — register at **api.business.govt.nz**. Returns Primary Business Data (legal name, business type, contact details, addresses) + **watchlist/change alerts** (useful for client monitoring). |
| Overture Maps places | docs.overturemaps.org | ✅ **CDLA-Permissive-2.0 / Apache-2.0**, explicitly no ODbL share-alike. ~59M+ places (Foursquare/Microsoft/meta sources), **monthly releases** (latest verified: 2026-08-19.0), queryable **directly from S3 GeoParquet with DuckDB** — zero download cost. |
| Litestream | github.com/benbjohnson/litestream | ✅ Actively maintained, **Apache-2.0**, file/S3/SFTP/WebDAV/GCS destinations, safe WAL replication. Note: creates `_litestream_lock` table in source DB — expected, do not drop. |
| Overture NZ coverage | inferred from sources | Foursquare+meta sources give strong SMB coverage incl. NZ; cross-check a sample of 20 known NZ businesses before relying on it as primary (OSM/Overpass remains the live-data complement). |

**Verdict changes vs first draft:** Reacher downgraded in confidence (archived backend repo → use monorepo; AGPL boundary must be respected). All other INSTALL NOW items verified clean.
