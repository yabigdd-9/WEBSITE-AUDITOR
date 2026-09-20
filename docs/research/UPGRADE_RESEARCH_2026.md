---
title: "WEBSITE-AUDITOR — Deep Upgrade, Optimisation & Tool Discovery Report"
version: "2.0.0"
date: "2026-09-21"
supersedes: "UPGRADE_RESEARCH_2026.draft-01-superseded.md"
scope: "Deep ecosystem research + architecture redesign for WEBSITE-AUDITOR / MoneyMachine"
audience: "operator (Dion) / implementing agent"
---

# WEBSITE-AUDITOR — DEEP UPGRADE & TOOL DISCOVERY REPORT

## 0. Method, evidence standard, and how to read this

**What was done.** The repository was read in full (538 files, ~25k LOC of Python
across 5 competing audit implementations, a 50-table SQLite schema, a leased-queue
state machine, and a partially-built `supervisor/` package). Then ~40 external
sources were searched, and **pricing / licence pages were fetched directly**
rather than trusted from blog summaries.

**Verification legend used in every table:**

| Mark | Meaning |
|---|---|
| ✅V | Licence/pricing **verified this session by fetching the official page or LICENSE file** |
| 🔶R | Reported by a credible secondary source — **verify before depending on it** |
| ⛔ | Trial-only / paid / will create charges — **avoid** |
| ⚠️ | Free, but with a material trap (trains on your data, blocked port, banned use, AGPL network clause) |

### Two headline corrections that change recommendations

1. **`check-if-email-exists` (Reacher) is AGPL-3.0, not MIT.** ✅V The widely
   repeated "MIT" claim is wrong. It is dual-licensed: AGPL-3.0 *or* a paid
   commercial licence. Any use must respect the AGPL boundary.
2. **The public Nominatim/OSM API must NOT be used for systematic business
   discovery.** ✅V The OSMF Acceptable Use Policy lists *"searching for complete
   lists of postcodes, towns etc. and downloading all POIs in an area"* as
   **"strictly forbidden and will get you banned"**, and forbids reselling
   geocoding results. It also caps use at **1 req/s**, requires a real
   User-Agent/Referer, and throttles long-running scripts to **4 req/min**.

Both are load-bearing. (1) affects email verification. (2) affects **business
discovery — the very first stage of the pipeline.**

> Note: the superseded draft-01 recommended *"Overpass API (OSM) + Nominatim —
> INSTALL NOW"* for NZ business discovery. That recommendation is **withdrawn**
> — see §13 and §4 for the compliant replacement.

---

## 1. Ground truth: what is actually running today

Measured live in this workspace, not inferred:

| Check | Observed | Status |
|---|---|---|
| `./mm doctor` | `BLOCKED_RUNTIME: Python email environment missing` | **BROKEN** |
| `money-machine/.venv-email` | symlink → `/Users/yabigdd/MoneyMachine/.venv-email` — path does not exist | **BROKEN SYMLINK** |
| Host `python3` | 3.9.6; code requires ≥3.11 | **MISMATCH** |
| `docker` | not installed | **ABSENT** |
| `ollama` | not installed / daemon not responding | **ABSENT** |
| Local models | none pulled | **ABSENT** |
| Audits on disk | **6** JSON files | effectively cold start |
| SQLite schema | 50 tables incl. `mm_evidence`, `mm_scores`, `mm_metrics`, `mm_experiments`, `mm_learning`, `circuit_breakers`, `rate_buckets`, `worker_registry` | **strong but under-used** |
| Symlink aliases | `config`, `control-plane`, `migrations`, `scripts`, `tests` → `money-machine/` | **hazardous** |
| Hardcoded model | `auditor_toolkit/ai.py` → `/Users/dd/llama-2-7b-chat.Q4_K_M.gguf` | **stale (2023-era)** |
| Vision capability | none anywhere in the tree | **MISSING** |
| Free LLM providers wired | local llama.cpp, local Ollama, OpenRouter, Nous only | **single point of failure** |

**Interpretation.** The *design* is genuinely above average: an evidence-gated
approval chain, a validated state machine, leased work claims with expiry
recovery, circuit breakers, a zero-paid-inference policy enforced in code,
interval-based expected-value scoring, and explicit anti-fabrication specs
(`JUDGE_SPEC.md`, `PROOFER_SPEC.md`). The *operations* are at zero — nothing that
requires a model, a browser, or Python ≥3.11 can execute.

So the highest-value work is **not** "add more tools". It is:

> **(a)** make the existing engine runnable and portable;
> **(b)** fill the three genuinely absent capabilities — **vision**,
> **entity resolution**, **real web-performance measurement**;
> **(c)** break the **OpenRouter single point of failure**;
> **(d)** stop the **discovery stage from being ban-bait**.

---

## 2. TOP 25 HIGHEST-VALUE UPGRADES

Ranked by (impact × probability of success) ÷ effort. Effort: XS/S/M/L.
**[P0]** = do first; these unblock everything else.

| # | Upgrade | Stage | Why it matters | Licence | Effort |
|---|---|---|---|---|---|
| 1 | **[P0] Containerise the whole system** — `python:3.12-slim` base, one root `compose.yaml`, `restart: unless-stopped` | Foundation / all | The single blocking defect. Kills the broken-venv, host-Python-3.9 and macOS-only-path failures at once, and is the precondition for unattended 24/7 running | — | M |
| 2 | **[P0] Replace the Llama-2-7B pin** in `auditor_toolkit/ai.py` with a role-routed local stack (`qwen3-vl:8b` + a small tool-calling model) | AI reasoning, vision | Llama 2 7B has no vision, weak tool calling, and was withdrawn from most registries. It is the *only* model the toolkit can load | Apache-2.0 | S |
| 3 | **[P0] Add Groq + Google AI Studio (Gemini) + Cloudflare Workers AI as first-class free routes** in `mm_model_router.PURPOSE_ROUTES` | AI reasoning, reliability | OpenRouter free is capped at **20 RPM / 50 RPD** (1,000 RPD only after ≥$10 lifetime purchase — ✅V). It is currently the *only* non-local route, so when Ollama is down the pipeline dead-ends in `BlockedCost` | Free tiers | M |
| 4 | **[P0] Adopt the NZBN API as the discovery + identity backbone** (free, no fee, bulk extract, change-event watchlists) | Discovery, identity resolution | Converts discovery from "scrape and hope" into a sanctioned, structured, *watchable* registry feed — and replaces the banned Nominatim POI-harvest approach | Free ✅V | M |
| 5 | **[P0] Fix discovery compliance** — drop public Nominatim for POI harvesting; use Geofabrik `nz-latest.osm.pbf` + a self-hosted instance | Discovery, legal | Prevents IP-ban and keeps the pipeline lawful | ODbL | M |
| 6 | **[P0] Add probabilistic entity resolution with Splink (MIT ✅V)** over SQLite/DuckDB | Identity resolution | A 50-table schema with no dedup engine; `identity_handler` currently only parses a URL host. Splink does 1M records on a laptop in ~1 min | MIT | S |
| 7 | **[P0] Add a real Lighthouse / Core Web Vitals engine (Unlighthouse, MIT ✅V)** behind the existing audit worker | Website auditing | The current audit is static-HTML heuristics. "Your site is slow" is the most sellable finding and is presently **unmeasured** | MIT | S |
| 8 | **[P0] Add an `axe-core` WCAG scan** (MIT OR MPL-2.0 ✅V) to the audit fan-out | Accessibility | Alt-text heuristics ≠ WCAG conformance. Same engine behind Chrome DevTools, and it produces defects that survive the Proofer gate | MIT/MPL-2.0 | S |
| 9 | **[P0] Add vision-based design critique** on full-page screenshots, with **prompt-injection isolation** | Visual analysis | The stated "improved screenshots/mockups" objective is **entirely absent**. Also the strongest outreach hook ("here is your mobile page vs. a clean redesign") | Free tier / local | M |
| 10 | **[P0] Restructure `PURPOSE_ROUTES` into a provider-health-scored router** with quota accounting persisted in `rate_buckets` | Reliability, AI reasoning | Turns a static tuple list into something that degrades gracefully instead of dying | — | M |


| 11 | **[P1] Move email verification to consensus-of-independent-signals**, keep `check-if-email-exists` **only** as an isolated container (AGPL boundary), add a **port-25-blocked fallback** | Email verification | Port 25 outbound is blocked by most residential ISPs, so SMTP probing fails silently today | AGPL-3.0 ⚠️ | M |
| 12 | **[P1] Replace the static disposable-domain blocklist with a refreshable, versioned pipeline**; make catch-all a first-class signal | Email verification | `disposable_email_blocklist.conf` is 124 KB of stale data with a `source.json` that nothing schedules | MIT/PD | S |
| 13 | **[P1] Add broken-link verification with lychee** (MIT/Apache-2.0 ✅V) | Website auditing | Deterministic, fast (Rust), and produces provable defects that survive the Proofer gate — better than the regex scan in `checks.py` | MIT/Apache-2.0 | S |
| 14 | **[P1] Add passive-only security scanning**: `testssl.sh` (GPL-2.0 ✅V) for TLS + the header grading already in `tier1_enrichment` | Security scanning | A TLS grade is high-credibility and low-risk. **Passive only** — never active exploitation against a third party's site | GPL-2.0 | S |
| 15 | **[P1] Add Gatus (Go, ~15 MB) for health checks + a status page** instead of a bespoke health dict | Monitoring | Config-as-code, version-controllable, ~5× lighter than Uptime Kuma (Node, ~80 MB) | 🔶R Apache-2.0 | S |
| 16 | **[P1] Add `promptfoo` (MIT ✅V) as the eval + regression harness**, driven by `mm_experiments` / `mm_learning` | Self-improvement | Gives "learn from outcomes" a real backbone and makes prompt changes testable instead of vibes | MIT | M |
| 17 | **[P1] Add GEPA for prompt optimisation against local/free models**, using as few as 3 examples | Self-improvement | Prompt evolution that beats RL on cost, needs no weight access, and reads natural-language failure traces — a natural fit for the Judge/Proofer specs | 🔶R Apache-2.0 | M |
| 18 | **[P1] Add PDF/proposal rendering via Gotenberg** (MIT ✅V, Docker, headless Chromium) | Reporting, quotes, proposals | One service does HTML→PDF, URL screenshots, PDF/A and **PDF/UA accessibility** — and removes Chromium/font management from the app | MIT | S |
| 19 | **[P1] Add structured screenshot diffing** (odiff MIT / pixelmatch ISC) for before/after evidence | Visual analysis, reporting | Turns `before_after_report.py` from side-by-side HTML into quantified, defensible change evidence | MIT / ISC | S |
| 20 | **[P1] Harden secrets**: Keychain/Docker secrets, per-provider key scoping, `gitleaks` in CI | Security | `UPGRADE_PLAN.md` records two live keys leaked into chat logs and git history, plus `data_collection: allow` in `routing.yaml` | MIT | S |
| 21 | **[P1] Set `data_collection: deny`** and stop routing confidential client content to free tiers whose terms train on inputs | Security / privacy | Verified: Gemini **free** tier = *"Content used to improve our products: Yes"* ✅V. Free-tier calls must be treated as **public disclosure** | — | XS |
| 22 | **[P1] Delete the `config`, `control-plane`, `migrations`, `scripts`, `tests` symlink aliases** | Maintainability | A `tests/` directory that shadows the real one breaks pytest discovery and misleads every tool and agent that walks the tree | — | XS |
| 23 | **[P2] Add vector retrieval (`sqlite-vec`) + local embeddings (Qwen3-Embedding 0.6B, Apache-2.0 ✅V)** | Data, AI reasoning | Enables "have we seen this business / defect / objection before?" and dedup-aware outreach | Apache-2.0 | S |
| 24 | **[P2] Wire Windmill (AGPLv3 ✅V) as the scheduler/ops UI over the Python CLI** — cron, retries, run history, alerts | Workflow architecture | 24/7 scheduling with a UI and audit trail, without rewriting the working state machine | AGPL-3.0 | M |
| 25 | **[P2] Add an NZ outreach-law compliance layer** (Unsolicited Electronic Messages Act 2007 + Privacy Act 2020): recorded permission basis, truthful sender identity, functional unsubscribe, suppression enforcement | Outreach, legal | `mm_suppression` exists but nothing enforces an NZ-specific permission basis. This is the difference between a business and a liability | — | M |

---

## 3. TOP 10 TOOLS TO INSTALL IMMEDIATELY

Ordered by unblocking power. Each is free-forever, self-hostable, and useful
before the next one lands.

| # | Tool | Purpose | Stage | Licence | Docker | Install path | Difficulty |
|---|---|---|---|---|---|---|---|
| 1 | **Docker + Colima** *(precondition for everything below)* | Container runtime | Foundation | Colima Apache-2.0 | n/a | `brew install colima docker docker-compose && colima start` | Easy |
| 2 | **Ollama** (or `llama.cpp`) | Local inference host for all AI roles | AI reasoning | MIT | Yes | `brew install ollama` → `ollama pull qwen3-vl:8b` | Easy |
| 3 | **Unlighthouse** | Full-site Lighthouse / Core Web Vitals | Website auditing | MIT ✅V | Yes | `npx unlighthouse --site <url>` — needs **Node ≥ 22.18.0** ✅V | Easy |
| 4 | **axe-core CLI** | WCAG 2.x conformance scan | Accessibility | MIT OR MPL-2.0 ✅V | Yes | `npm i -g @axe-core/cli` | Easy |
| 5 | **Gotenberg** | HTML/URL→PDF, URL screenshots, PDF/UA | Reporting, mockups | MIT ✅V | Yes | `docker run --rm -p 3000:3000 gotenberg/gotenberg:8` | Easy |
| 6 | **Splink** | Probabilistic entity resolution / dedup | Identity resolution | MIT ✅V | pip, no Spark needed | `pip install splink duckdb` | Easy |
| 7 | **lychee** | Fast async broken-link checker | Website auditing | MIT / Apache-2.0 ✅V | Yes | `brew install lychee` | Easy |
| 8 | **testssl.sh** | TLS/cipher/certificate grading (passive) | Security | GPL-2.0 ✅V | Yes | `brew install testssl` | Easy |
| 9 | **Gatus** | Health checks + status page, config-as-code | Monitoring | 🔶R Apache-2.0 | Yes | Single Go binary / compose service | Easy |
| 10 | **promptfoo** | Eval harness + regression tests for prompts | Self-improvement | MIT ✅V | Yes | `npx promptfoo@latest` | Medium |

**Explicitly NOT in this list, and why** (these appear in the superseded draft):

- **Reacher / `check-if-email-exists`** — held back because it is **AGPL-3.0 ✅V**
  and because **SMTP verification needs outbound port 25, which most residential
  ISPs and many hosts block**. Install it as a *container you call over HTTP*,
  never as a linked library, and always keep the deterministic
  (DNS/MX/blocklist/reputation) path working without it. See §13.
- **Public Nominatim / Overpass API for discovery** — **REJECT**. Policy
  violation that will get the IP banned ✅V. Self-host instead.
- **DeepSeek Harness (`@deepseek-ai/dsh`)** — the pinned `0.1.6-alpha.2` was never
  published to npm (the project's own `UPGRADE_PLAN.md` records `latest` as
  `0.1.5-rc.2`), and Docker is absent. **Remove** rather than resurrect.

---

## 4. BEST FREE / LOCAL AI MODEL STACK BY AGENT ROLE

Everything below runs locally at $0 or on a permanently-free API tier. Sizing
assumes a modest machine: **8–16 GB unified RAM** (Apple Silicon) or an **8 GB
GPU**, with 16 GB / 12 GB-GPU as the comfortable target.

### 4.1 Local model stack (primary, offline-capable)

| Role | Model | Size / VRAM | Licence | Why this one |
|---|---|---|---|---|
| **Orchestrator / Planner** | `qwen3:8b` (or `qwen3:14b` at 16 GB) | ~5.2 GB | Apache-2.0 | Native tool calling in the chat template; runs cleanly through Ollama's `tools` API ✅V |
| **Coder / fix-generator** (remediation snippets) | `qwen2.5-coder:7b` | ~4.7 GB | Apache-2.0 | Purpose-built for code; feeds `remediation-engine.py` |
| **Vision / design critique** | **`qwen3-vl:8b`** | 6.1 GB, **256K ctx** | Apache-2.0 | ✅V: the recommended general-purpose Ollama VLM at the 12 GB tier. On 8 GB use `qwen3-vl:4b` (3.3 GB) |
| **OCR / document & invoice reading** | `glm-ocr` | 2.2 GB, 128K ctx | 🔶R | ✅V: 0.9B OCR specialist — the pick generic "best VLM" lists miss |
| **Ultra-low-VRAM vision** | `minicpm-v4.6` (1.6 GB) or `qwen3-vl:2b` (1.9 GB) | ≤2 GB | 🔶R Apache-2.0 | ✅V: for 4–6 GB machines only |
| **Judge / Critic** | `qwen3:14b` at temp 0 | ~9 GB | Apache-2.0 | `JUDGE_SPEC.md` demands independence + strictness; a 14B at temp 0 is far more consistent than a 4B |
| **Proofer (fact-check)** | `qwen3:14b` temp 0 **plus** deterministic assertions | ~9 GB | Apache-2.0 | Never let a model alone gate a factual claim — pair with code checks |
| **Extraction / Classification** | `qwen3:4b` (temp 0) | ~2.5 GB | Apache-2.0 | Cheap, fast, good enough for taxonomy, sentiment and entity tagging at volume |
| **Embeddings (dedup, retrieval)** | **`qwen3-embedding:0.6b`** | ~0.6 GB | Apache-2.0 ✅V | MTEB multilingual #1 at launch for its class; 32K context; instruction-aware |
| **Embeddings (alt, on-device)** | `embeddinggemma` | 308M, **<200 MB RAM** | Gemma Terms ⚠️ | ✅V: Matryoshka 768→128 dims. Use if RAM is critical; note Google's terms |
| **Embeddings (hybrid retrieval)** | `bge-m3` | 568M | MIT ✅V | ✅V: emits **dense + sparse + ColBERT multi-vector in one forward pass** — collapses embedding + lexical + rerank into one service |

**Model-selection rules**

- Tool calling is a *reliability* metric, not a chat-quality metric. What matters
  is valid parseable JSON matching the schema, correct argument mapping, parallel
  calls, and knowing when **not** to call ✅V.

### 4.2 Remote free-tier stack (secondary, resilience)

The current router knows only `local:*`, `openrouter`, `nous`. Adding the
following turns a fragile single point of failure into a genuinely redundant free
fabric. **Figures are published free tiers and are volatile.**

| Provider | Free quota | Card? | Best role here | Data terms |
|---|---|---|---|---|
| **Google AI Studio (Gemini)** | 5–30 RPM, 15–1,000 RPD by model (Flash ≈10 RPM / 250 RPD) 🔶R | No | **Vision** (screenshot critique), long-context reasoning; `gemini-embedding-2` **text embeddings free of charge** ✅V | ⚠️ **Free tier: "Content used to improve our products: Yes"** ✅V |
| **Groq** | ≈30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD 🔶R | No | **Fast classification & extraction** at volume; sub-second | ⚠️ Confirm current terms |
| **Cloudflare Workers AI** | 10,000 Neurons/day, resets 00:00 UTC 🔶R | No | Burst fallback; OpenAI-compatible | Commercial use listed OK 🔶R |
| **OpenRouter (`:free`)** | **20 RPM / 50 RPD** (<$10 lifetime credits); **1,000 RPD** (≥$10) ✅V | No (basic) | Model variety / last-resort diversity | Commercial use listed OK ✅V |
| **SambaNova Cloud** | 20 RPM / **20 RPD** / 200,000 TPD 🔶R | No | Emergency only — 20 RPD is very tight | 🔶R |
| **Z.AI (GLM-Flash)** | $0/token listed; **quota unpublished** 🔶R | No | Speculative — do not depend on it | 🔶R |
| **Hugging Face Inference** | **$0.10/month credits** 🔶R | No | Evaluation only | 🔶R |
| **NVIDIA NIM** | Free prototyping endpoints, no universal quota 🔶R | Varies | Prototyping only | 🔶R |
| **Cohere** | 1,000 calls/month; Chat 20 RPM; **Embed 2,000 inputs/min**; Rerank 10 RPM 🔶R | No | Embeddings + rerank only | ⚠️ "Evaluation" scope |
| **Mistral Studio** | Free mode, quota unpublished; ~1B tokens/mo claimed 🔶R | No | ⚠️ **Prompts may be used for training** | ⚠️ Training |
| **Cerebras** | 5 RPM / 1M TPD but **30-day trial, card required** ⛔ | **Yes** | **REJECT** — expires | — |
| **Together AI** | $100 signup credit (**trial only**) ⛔ | Yes | **REJECT** as ongoing | — |
| **OpenAI / Anthropic free** | OpenAI 3 RPM on a legacy model; Anthropic **no permanent free API tier** ⛔ | — | **REJECT** | — |

### 4.3 Non-negotiable router policy changes

1. **OpenRouter alone cannot carry a 24/7 pipeline.** 50 RPD is ≈2
   requests/hour. With ≥$10 lifetime credits it becomes 1,000 RPD — workable, but
   **that is a purchase**, so it conflicts with a strict $0 rule. Treat 1,000 RPD
   as an *optional* operator upgrade, never a dependency.
2. **Groq + Gemini free are the real capacity.** Together they give roughly
   1,250+ requests/day at zero cost — enough for scoring, classification and
   enrichment, *provided the router can fail over*.
3. **Every free remote tier must be assumed to be public.** Gemini free trains on
   inputs ✅V; Mistral free may train 🔶R. Therefore:
   - route **only** non-confidential, already-public data (the prospect's own
     public website copy) to remote free tiers;
   - keep **client-confidential** material (contracts, invoices, internal notes)
     on **local models only** — enforced in code, not by convention.
4. **Never silently fall back to a paid model.** The existing `PaidRouteRefused`
   / `BlockedCost` design is correct: preserve it and extend it to new providers
   via an explicit `FREE_TIER_ALLOWLIST`.
5. Set `data_collection: deny` in `config/routing.yaml` (currently `allow`).

- The highest published self-hostable BFCL scores belong to
  Llama-3-Groq-70B-Tool-Use (90.76%), with an **8B variant at 89.06%** for
  single-GPU boxes ✅V. If tool-call reliability becomes the bottleneck, that 8B
  is the drop-in.
- For multi-step tool use + RAG, Cohere **Command-R 35B** is the documented
  specialist ✅V — but it does not fit an 8 GB GPU.
- **`llama3.2-vision` is English-only for image input** ✅V — a real constraint
  given the te reo Māori / bilingual draft capability in `auditor_toolkit/ai.py`.


---

## 5. RECOMMENDED DOCKER SERVICE STACK

Design rules: **localhost-bound by default**, one private compose network,
**no service requires a paid tier**, every service has a healthcheck, and the
whole stack must survive `docker compose down && up` with no data loss.

| Tier | Service | Image / source | Port | RAM (idle) | Licence | Why included |
|---|---|---|---|---|---|---|
| **Core** | `auditor` (the app) | `python:3.12-slim` + this repo | — | ~150 MB | MIT (repo) | Replaces the broken host venv entirely; `restart: unless-stopped` |
| **Core** | `worker` (same image, different command) | — | — | ~150 MB | MIT | Scale with `--scale worker=N`; consumes the leased queue |
| **Core** | `scheduler` (same image) | — | — | ~80 MB | MIT | Cron/loop entrypoint; or delegate to Windmill |
| **AI** | `ollama` | `ollama/ollama` | 11434 | ~200 MB + models | MIT | Local inference; model store on a named volume |
| **Web** | `browser` (Playwright) | `mcr.microsoft.com/playwright` | — | ~400 MB | Apache-2.0 | Screenshots + JS rendering, isolated from app |
| **Web** | `unlighthouse` | Node 22.18+ image | 5678 | ~300 MB | MIT ✅V | Lighthouse/CWV; hits the app over the compose network |
| **Search** | `searxng` | `searxng/searxng` | 8888 | ~120 MB | AGPL-3.0 | Private meta-search for discovery (already in your stack) |
| **Docs** | `gotenberg` | `gotenberg/gotenberg:8` | 3000 | ~250 MB | MIT ✅V | PDF, screenshots, PDF/UA for proposals & reports |
| **Monitor** | `gatus` | `twinproduction/gatus` | 8080 | **~15 MB** | 🔶R Apache-2.0 | Health checks + status page, config-as-code |
| **Monitor** | `glitchtip` *(optional)* | `glitchtip/glitchtip` | 8000 | ~400 MB | MIT | Self-hosted error tracking; needs Postgres |
| **Ops** | `windmill` *(P2, optional)* | `windmill-labs/windmill` | 8000 | ~600 MB | AGPL-3.0 ✅V | Scheduler/UI/retry history. Ships its own Postgres |

### Deliberate exclusions

| Service | Verdict | Reason |
|---|---|---|
| **PostgreSQL** (as the primary DB) | **REJECT for core** | SQLite with WAL + the existing 50-table schema is correct for a single-node local pipeline. Postgres only enters as Windmill's internal DB (its own container) |
| **Twenty CRM** | **REJECT** | AGPL-3.0, ~750 MB, 4 services, and **no native workflow automation or reporting** — *worse* than the bespoke SQLite CRM already present. EspoCRM (GPL-3.0, ~630 MB) is the better of the two, but still replaces working code with a PHP stack you'd have to integrate |
| **Celery + Redis/RabbitMQ** | **REJECT** | Two extra daemons to replace a working SQLite leased-queue. Keep `mm_pipeline.claim()`, which already has lease expiry recovery |
| **Uptime Kuma** | Optional | ~80 MB Node vs Gatus's 15 MB Go. Only pick it if you want the GUI monitor editor over config-as-code |
| **n8n** | Keep if already valuable | Fair-code/sustainable-use licence; not needed once Windmill or the cron supervisor is live — avoid running both |
| **Redis** | **REJECT** | No consumer for it; SQLite + files cover cache and queue |
| **Lightpanda** | **TEST only, not web-tier** | AGPL-3.0 ✅V, and explicitly **has no graphical rendering engine** — it **cannot take screenshots**. Keep for cheap HTML crawl; Playwright stays for rendering |
| **Qdrant** | Optional (P3) | Apache-2.0 and excellent, but `sqlite-vec` in the existing SQLite file is enough for the current data volume (6 audits, ~50 tables) |

### Sizing

An 8 GB machine comfortably runs `auditor + worker + ollama(small) + searxng +
gotenberg + gatus` (~1.2 GB idle). Add Unlighthouse and Playwright during scans
(~1.9 GB peak). Windmill + Postgres + GlitchTip are the only components that
push you past 4 GB and should be deferred to P2/P3.



---

## 6. RECOMMENDED MCP / PLUGIN STACK

**Important architectural finding.** The `microsoft/playwright-mcp` README now
states that **for coding agents, a CLI + SKILLS workflow is preferred over MCP**,
because CLI invocations are more token-efficient — they avoid loading large tool
schemas and verbose accessibility trees into the model context ✅V. Given this
project's hard $0 inference budget and small local model context budgets,
**prefer CLI-as-a-tool over MCP servers wherever both exist.** Reserve MCP for
genuinely stateful, interactive capabilities.

| # | Server / plugin | Purpose | Stage | Licence | Local-only? | Verdict |
|---|---|---|---|---|---|---|
| 1 | **Playwright CLI (+ skill wrapper)** | Browser automation *for agents* | Visual analysis, contact discovery | Apache-2.0 | Yes | **INSTALL NOW** — preferred over MCP per the upstream README ✅V |
| 2 | **Filesystem MCP** | Scoped read/write repo access for agents | All agent lanes | MIT | Yes | INSTALL NOW — scope to `audits/`, `outputs/`, `state/` only |
| 3 | **SQLite MCP** | Query the 50-table pipeline DB | Identity, scoring, monitoring | MIT | Yes | INSTALL NOW — **read-only credentials** for agents |
| 4 | **Playwright MCP** | Interactive/stateful browser sessions | Ad-hoc debugging, mockup capture | Apache-2.0 ✅V | Yes (local Chrome) | TEST — use when CLI is insufficient. Accessibility-snapshot based (no screenshots needed → fewer tokens) ✅V |
| 5 | **SearXNG MCP** | Private web search for research roles | Discovery, research | AGPL-3.0 (SearXNG) | Yes | INSTALL NOW — wraps the SearXNG you already run |
| 6 | **Gotenberg as an HTTP tool** | PDF/screenshot generation | Reporting | MIT ✅V | Yes | INSTALL NOW — call as a plain HTTP tool, no MCP needed |
| 7 | **Firecrawl MCP / self-hosted Firecrawl** | Crawl→clean markdown at scale | Discovery, content analysis | ⚠️ AGPL-3.0 self-host; **cloud is paid** | Self-host only | OPTIONAL — only if lychee + Lightpanda + Trafilatura prove insufficient. ⚠️ **Do not use the hosted API — it bills** |
| 8 | **Chrome DevTools MCP** | Live DOM/CSS/perf introspection for agents | Audit deep-dive, remediation | 🔶R | Yes | OPTIONAL |
| 9 | **`gskill` / GEPA agent skill** | Prompt-optimisation loops invoked by an agent | Self-improvement | 🔶R Apache-2.0 | Yes | OPTIONAL (P2) |
| 10 | **DeepSeek Harness MCP bridge** | Existing guarded bridge to `dsh` | — | — | — | **REJECT / REMOVE** — pinned package never published; Docker absent |

**Anti-patterns to avoid in the plugin stack**

- Do **not** expose mutation-capable tools (send, pay, deploy, delete) to any
  agent lane. The existing
  `integrations/tier1_enrichment/policies/permissions.yml` and
  `approval_gates.yaml` are the right pattern — extend them, don't bypass them.
- Do **not** let an agent read secrets. Mount `.env` only into the app process,
  never into the agent/tool container.
- Do **not** give an agent an arbitrary shell. `auditor_toolkit` already exposes
  a bounded action surface — keep it.

---

## 7. IMPROVED WORKFLOW ARCHITECTURE

### 7.1 What to keep (do not rewrite)

Be explicit about this, because the temptation will be to rebuild. These are
genuinely good and should be preserved verbatim:

- `mm_pipeline.py` — validated state machine (`STATES`, `TRANSITIONS`), leased
  claims with expiry recovery, append-only `pipeline_events` audit trail,
  circuit breakers, `BlockedCost` deferral.
- `mm_approval.py` + `approval_gates.yaml` — evidence-gated human approval with
  `per_message: true`, truthful sender identity, opt-out handling.
- `mm_intelligence.py` — interval-based expected value (`[low, high]`
  probabilities, deal size, margin, human hours). Very few pipelines model
  uncertainty honestly; this one refuses to divide by zero AI cost and declines
  to claim ROI. **Do not replace this with a point estimate.**
- `JUDGE_SPEC.md` / `PROOFER_SPEC.md` — independent adversarial review plus a
  "one fabrication = FAIL" gate, written after a real fabrication incident.
- `tier1_enrichment/` — keyless-first enrichment (W3C validators, urlscan,
  header grading) with a cache. Excellent design pattern: free-by-default,
  keyed sources optional.
- `mm_suppression`, `outreach_send_ledger`, `mm_receipts` — the right primitives.

### 7.2 Stage topology: what changes

```
                    ┌─────────────────────────────────────────────────┐
                    │ SCHEDULER  (Windmill / supervisor --daemon)      │
                    │ cron: discover 6h · audit 1h · verify 15m        │
                    │        · follow-up 1h · health 5m · eval daily   │
                    └───────────────────────┬─────────────────────────┘
                                            │ enqueue(state=…)
┌───────────────────────────────────────────▼─────────────────────────────────────┐
│                        LEASED QUEUE  (SQLite, existing)                          │
│        claim(states, worker_id, lease_seconds) · retry · dead-letter             │
└──┬──────────┬───────────┬───────────┬───────────┬───────────┬──────────┬─────────┘
   │          │           │           │           │           │          │
┌──▼───┐ ┌───▼────┐ ┌────▼────┐ ┌────▼─────┐ ┌───▼────┐ ┌────▼────┐ ┌──▼──────┐
│DISCOV│ │IDENTITY│ │ CONTACT │ │ VERIFY   │ │ AUDIT  │ │  SCORE  │ │  DRAFT  │
└──┬───┘ └───┬────┘ └────┬────┘ └────┬─────┘ └───┬────┘ └────┬────┘ └──┬──────┘
   │         │           │           │           │           │          │
  NZBN    Splink      crawl+      consensus   FAN-OUT:     rubric    templates
  +OSM    +PSL        trafilatura  of 4        ├ toolkit    + EV      + local AI
  extract +DuckDB     +schema.org  signals      ├ Lighthouse intervals  (confidential)
  +SearXNG            +mailto       ⚠︎no port25  ├ lychee                │
  +directories        provenance                ├ axe-core              │
                                                ├ testssl.sh (passive)  │
                                                └ vision critique ──────┘
                                                       │
                          ┌────────────────────────────▼───────────────────────┐
                          │ JUDGE (independent, adversarial) → PROOFER (facts)  │
                          │  any fabricated claim = FAIL, returns upstream      │
                          └────────────────────────────┬───────────────────────┘
                                                       │
                          ┌────────────────────────────▼───────────────────────┐
                          │  HUMAN APPROVAL GATE (unchanged, per-message)        │
                          │  APPROVAL_PENDING → [operator] → SEND (or never)     │
                          └────────────────────────────┬───────────────────────┘
                                                       │
                     OUTCOME CAPTURE → EVAL (promptfoo) → PROMPT/RUBRIC EVOLUTION
                                        (GEPA) → back into prompts
```

### 7.3 Bottlenecks identified and their fixes

| Bottleneck | Evidence in code | Fix |
|---|---|---|
| **Serial subprocess audit** | `mm_workers.audit_handler` shells out to `engines/detect.py` with a 60 s timeout, one site at a time | Fan out to N concurrent audit workers; run the 6 engines in parallel *within* a site via `asyncio.gather` |
| **Subprocess per audit** (`subprocess.run(['python3', …])`) | `mm_workers.py:43` | Import the engine in-process (it is a sibling module) — or make the container the browser/engine host. Removes Python startup cost per site |
| **Single-threaded discovery** | none implemented | NZBN bulk extract loaded once into SQLite, then incremental change-events via watchlist webhooks |
| **No cache reuse across stages** | `tier1_enrichment/cache.py` exists but is scoped to that module | Promote to a shared HTTP cache keyed by URL+method+body-hash with TTL in SQLite |
| **`identity_handler` is a no-op** | `mm_workers.py:28-35` only calls `public_url()` | Real canonicalisation: follow redirect chain → registrable domain (public suffix list) → cross-check against NZBN |
| **Model routing is static** | `PURPOSE_ROUTES` is a literal dict | Provider-health-scored router with quota ledger in `rate_buckets` |
| **Everything AI is blocked** | `mm_model_router.local_complete` raises immediately because no endpoint is up | Docker-service Ollama with a healthcheck; router pre-warms and reports provider status |
| **No prompt-injection defence** | audit evidence is fed to models as plain text | Treat all harvested page content as **untrusted data**: delimit it, strip instruction-like text, never let it alter the system prompt |
| **`mark_sent.py` fabrication precedent** | documented in `PROOFER_SPEC.md` | Keep the ledger-based send proof; assert on `outreach_send_ledger`, never on a boolean someone set |



---

## 8. PARALLEL WORKER / AGENT DESIGN

### 8.1 Two separate concurrency domains

Do not conflate them — they have different constraints.

**Domain A — deterministic workers (cheap, IO-bound).**
HTTP fetch, DNS, TLS, screenshots, Lighthouse, links. Concurrency is bounded by
*politeness and memory*, not cost. Run **4–8 workers**, with a **per-domain rate
limiter of ~1 request / 2 s** and a global cap so no single host gets hammered.
Existing `rate_buckets` is the right home for this.

**Domain B — model-backed agents (scarce, quota-bound).**
Bounded by local VRAM (**effectively 1 concurrent local generation** on a modest
machine) and remote free-tier RPM/RPD. Run **1 local lane + 2 remote lanes**, with
the router serialising per provider.

### 8.2 Recommended worker pool

```
worker pools (docker compose --scale)
├── discover   ×1   (cron-driven, mostly IO, writes candidates)
├── identity    ×1   (Splink + PSL + NZBN; batch, not streaming)
├── contact     ×3   (crawl contact/about pages, polite per-domain limits)
├── verify      ×2   (DNS/MX/blocklist/reputation; SMTP only if port 25 open)
├── audit       ×4   (the expensive one — Lighthouse+axe+lychee+testssl in parallel)
├── score       ×2   (deterministic rubric + EV intervals)
├── vision      ×1   (serialised: one screenshot at a time via local VLM or Gemini)
├── draft       ×1   (local-only for confidential content)
├── gate        ×1   (judge/proofer, temp 0, serialised)
└── maintain    ×1   (watchdogs, log rotation, backup, health)
```

### 8.3 Concurrency rules

1. **One local model, one generation.** A single `OLLAMA_NUM_PARALLEL` slot avoids
   VRAM thrash. Queue rather than parallelise.
2. **Never parallelise across a shared rate-limit budget.** Sum the quota in
   `rate_buckets` before dispatch. `max_concurrent_children: 1` in `routing.yaml`
   is already the right instinct — keep it.
3. **Idempotency keys per (business_id, stage, input_hash).** A crash mid-stage
   must not produce a duplicate model call or a duplicate outbound row. The
   `purpose_hash` in `mm_model_invocations` is a good start; extend it.
4. **Lease shorter than the stage's p99.** A Lighthouse audit can exceed the 60 s
   `AUDIT_TIMEOUT`. Raise the timeout *and* the matching lease, or
   expire-and-recover will double-run expensive work.
5. **Backpressure over queue growth.** If `audit` depth > N, stop *discovering*
   until it drains. Unbounded discovery plus one slow stage is how these systems
   die.
6. **Dead-letter triage as a first-class command**, not manual SQL. The
   `RETRYABLE_FAILURE` / `PERMANENT_FAILURE` states exist; nothing surfaces them.

---

## 9. SELF-IMPROVEMENT LOOP

The repo already has the tables (`mm_experiments`, `mm_learning`,
`mm_score_history`, `mm_metrics`) and the specs (Judge/Proofer) but **no harness**.
Close that gap.

### 9.1 The loop

```
  ┌─── 1. GOLDEN DATASET ──────────────────────────────────────────┐
  │ 8–20 hand-verified cases: URL + correct defect set + correct   │
  │ severity + correct accept/reject verdict. Immutable, versioned.│
  │ Small is fine: GEPA works with as few as 3 examples ✅V         │
  └───────────────────────┬───────────────────────────────────────┘
                          ▼
  ┌─── 2. EVAL HARNESS (promptfoo, MIT ✅V) ───────────────────────┐
  │ promptfoo eval -c promptfooconfig.yaml  → pass/fail per metric │
  │ Metrics: defect precision/recall · severity accuracy ·         │
  │          score MAE vs human · proofer catch-rate ·              │
  │          fabrication rate (must be 0) · quote-range containment │
  └───────────────────────┬───────────────────────────────────────┘
                          ▼
  ┌─── 3. REGRESSION GATE (CI) ────────────────────────────────────┐
  │ Any prompt/rubric change must not regress the golden set.       │
  │ Run on push + nightly. Block merge on fabrication > 0.          │
  └───────────────────────┬───────────────────────────────────────┘
                          ▼
  ┌─── 4. PROMPT EVOLUTION (GEPA, Apache-2.0 🔶R) ─────────────────┐
  │ pip install gepa → reflect on failure traces in natural         │
  │ language → propose targeted prompt mutations → re-eval.         │
  │ Needs no weight access; works against local models via LiteLLM. │
  └───────────────────────┬───────────────────────────────────────┘
                          ▼
  ┌─── 5. OUTCOME FEEDBACK (the real signal) ──────────────────────┐
  │ mm_deals / outreach_send_ledger / replies → per-lead outcome.   │
  │ Compare: did the predicted score band correlate with reply/win? │
  │ Write back into mm_learning; recalibrate the rubric weights.    │
  └───────────────────────┬───────────────────────────────────────┘
                          ▼
  ┌─── 6. STRATEGY A/B (mm_experiments) ───────────────────────────┐
  │ Two outreach framings · two scoring rubrics · two model routes. │
  │ Promote only on a pre-registered decision rule.                 │
  └────────────────────────────────────────────────────────────────┘
```

### 9.2 Non-negotiable guardrails

- **Fabrication rate must be hard-zero**, not "very low". A regression there is a
  release blocker — mirroring the hard line in `PROOFER_SPEC.md`.
- **Never let the optimizer see the golden labels** it is scored against, or it
  will overfit the literal strings. Hold out a validation slice.
- **Calibrate, don't just rank.** `mm_intelligence.score` already refuses
  calibrated-conversion claims; the feedback loop should move its *weights* toward
  measured outcomes, never invent probabilities.
- **Evolution must be reversible.** Version prompts in git with the eval result
  attached; never mutate the live prompt in place.
- **Cap the loop's cost at zero.** GEPA reflection must run against local/free
  routes only, or the self-improvement loop becomes the thing that breaks the $0
  guarantee.

---

## 10. RELIABILITY / FAILOVER DESIGN

### 10.1 Failure modes observed in this repo, and their fixes

| Failure mode | Where it bites | Fix |
|---|---|---|
| **Environment absent** | `.venv-email` symlink → missing path; `./mm` hard-exits | Containerise; `./mm` falls back to a declared `python3.12` or a clear actionable error |
| **Model endpoint down** | `local_complete()` raises `BlockedCost` immediately; no retry, no backoff | Health-probe with backoff; cache last-good route; demote unhealthy providers for a cooldown window |
| **Remote quota exhausted** | OpenRouter 50 RPD hit → whole stage defers | Quota ledger in `rate_buckets`; multi-provider failover; degrade to a deterministic path |
| **Port 25 blocked** | SMTP verification silently fails | Detect once at startup; if blocked, skip the SMTP lane and mark confidence `unknown`, never `invalid` |
| **Stage timeout > lease** | Leased item recovered while still running → double work | Lease = f(timeout × safety); heartbeat extension for long stages |
| **Subprocess engine missing** | `engines/detect.py` invoked via `python3` — host Python may lack deps | Run in the same container/interpreter; assert on import at startup |
| **Disk growth** | `state/worker-logs/` JSONL, no rotation | Use the already-scaffolded `supervisor/logrotate.py`; retention + `.gz` |
| **Schema drift** | 5 SQL migration files vs a 50-table live DB | `mm_migrations` exists — enforce a startup drift check and refuse to run on drift |
| **Backup unverified** | `email_acceptance.py` restores, but nothing schedules it | Nightly `VACUUM INTO` + integrity check + restore rehearsal; keep the existing verification pattern |
| **Silent fabrication** | the `mark_sent.py` precedent | Assert on `outreach_send_ledger` rows only |

### 10.2 Layered degradation ladder

Every stage must declare what it does when its best path is unavailable. The
pipeline should always produce a **lower-confidence answer**, never nothing.

```
AUDIT stage ladder
  1. Full fan-out: Lighthouse + axe + lychee + testssl + toolkit + vision
  2. No browser:     toolkit (static) + lychee + testssl   → mark perf/a11y "unmeasured"
  3. No network:     serve last cached snapshot, mark staleness
                     → NEVER present stale as current
  4. Nothing:        state = RETRYABLE_FAILURE with reason → visible in dead-letter

AI stage ladder
  1. Local model (qwen3 / qwen3-vl) — handles confidential content
  2. Groq / Gemini free — public content only
  3. Cloudflare Workers AI / SambaNova — public content only
  4. OpenRouter :free — last resort
  5. No route: BlockedCost → defer. Do NOT synthesise text.
     auditor_toolkit.ai.fallback_drafts() already exists and is correctly
     marked review_required=True — use it.
```

### 10.3 Concrete additions

| Addition | Value | Licence |
|---|---|---|
| **Gatus** health checks over `auditor`, `ollama`, `searxng`, `gotenberg` **plus queue-depth assertions** | Catches "running but stuck", which pure uptime checks miss | 🔶R Apache-2.0 |
| **Dead-man's-switch push monitor** | Detects a scheduler that stopped firing *at all* | — |
| **Quota ledger + provider cooldown** | Converts 429 storms into orderly deferral | — |
| **Idempotency keys** on every stage | Makes retries safe | — |
| **Snapshot-and-diff for client sites** | Turns "still broken?" into a cheap re-audit — the retention/upsell engine | — |
| **Complete `supervisor/`** (daemon, PID lock, rotation already scaffolded) | The `CONTINUITY_UPGRADE_PLAN.md` P0 items are written but unverified | — |


---

## 11. SECURITY AND SECRET-MANAGEMENT UPGRADES

### 11.1 Immediate — the leaks are already documented

`UPGRADE_PLAN.md` records that `PAGESPEED_API_KEY` **and** `RANKNIBBLER_API_KEY`
were posted into chat logs **and committed to git history**. That is the highest
severity item in the repository.

| # | Action | Why |
|---|---|---|
| 1 | **Rotate both keys now**, then restrict each to its single API surface | Assume compromised |
| 2 | **Purge from git history** (`git filter-repo`) *or* accept the history and rotate permanently | History rewrite is disruptive; rotation is mandatory either way |
| 3 | **Add `gitleaks` to CI** with a repo-specific config | Prevents recurrence; a config snippet already exists in `UPGRADE_PLAN.md` |
| 4 | **Move secrets out of `~/.zshrc`** into macOS Keychain (`security add-generic-password`) or Docker secrets | Shell profiles leak into every subprocess env — including agents |
| 5 | **Scope keys per provider**, and prefer keyless sources first (the existing `tier1_enrichment` pattern) | Fewer keys, smaller blast radius |
| 6 | **Never mount `.env` into agent/tool containers** | An agent holding a key can spend money |
| 7 | **Set `data_collection: deny`** in `config/routing.yaml` | Currently `allow` |
| 8 | **Add pre-commit hooks** (`gitleaks`, `detect-secrets`) | Catch it before commit |
| 9 | **Keep `outreach_send_ledger` + `approval_records` immutable and auditable** | The approval gate *is* the safety system; protect its integrity |

### 11.2 Architectural hardening

- **Egress allowlist.** The app container should reach only `ollama`, `searxng`
  and `gotenberg` on the internal network, plus the specific public APIs it needs.
  A misbehaving model tool then cannot exfiltrate.
- **Read-only root filesystem** for worker containers; write only to mounted
  `state/`, `audits/`, `outputs/`.
- **Non-root** container user.
- **Untrusted-content boundary.** Everything harvested from a prospect's site is
  *data*, not instruction. Strip/escape it before it enters a prompt; never
  concatenate page text into a system prompt. Add a regression test that a page
  containing "IGNORE PREVIOUS INSTRUCTIONS" cannot change a verdict.
- **Rate limiting is also a security control.** Per-domain limits keep scans from
  looking like an attack, protecting both reputation and legality.
- **Passive-only scanning of third-party sites.** `nuclei` and ZAP are dual-use;
  against a site you do not own, active scanning can be unlawful. Restrict to
  passive/baseline modes, document consent, and keep it **off by default**.
- **PII / privacy.** The pipeline ingests real business-contact data. Under the
  NZ Privacy Act 2020 the operator is a data controller: keep a retention policy,

---

## 12. THINGS CURRENTLY MISSING

### 12.1 Capability gaps (the pipeline cannot do these at all today)

| # | Missing capability | Impact | Fix |
|---|---|---|---|
| 1 | **Any vision capability** | No design critique, no before/after mockups, no mobile-vs-desktop comparison, no visual regression — a headline stated objective | `qwen3-vl:8b` locally + Gemini free tier remotely; Playwright/Gotenberg for capture |
| 2 | **Real Core Web Vitals / Lighthouse** | "Site is slow" is unmeasured, so it cannot be asserted, scored or priced | Unlighthouse |
| 3 | **WCAG / axe conformance** | Alt-text heuristics are not accessibility; the Proofer would correctly FAIL these claims | axe-core |
| 4 | **Entity resolution / dedup** | The same business can enter as `example.co.nz`, `www.example.co.nz` **and** a directory listing. The DB already holds `clyne-bennie.co.nz` **and** `www.clyne-bennie.co.nz` as separate audits — this is real, not theoretical | Splink + public-suffix canonicalisation |
| 5 | **Canonical domain resolution** | `identity_handler` only calls `public_url()`; no redirect-chain terminal host, no PSL | Add PSL + redirect resolution |
| 6 | **Screenshot diffing / visual regression** | `before_after_report.py` is side-by-side HTML with no quantified delta | odiff / pixelmatch |
| 7 | **PDF output** | Reports, quotes, proposals, invoices are ad-hoc HTML | Gotenberg |
| 8 | **Versioned email-verification consensus** | Single-path verification with a static 124 KB blocklist | 4-signal consensus scorer |
| 9 | **Provider-health-scored model routing** | One non-local route; no quota accounting; no cooldown | Extend the router |
| 10 | **Monitoring / alerting / status** | No external health signal; you learn of failure by noticing | Gatus |
| 11 | **Error tracking** | Failures live in JSONL nobody reads | GlitchTip (optional) or a log-query CLI |
| 12 | **Eval harness + golden dataset** | Prompts change with no regression signal | promptfoo |
| 13 | **Outcome→learning feedback** | `mm_learning` exists but nothing writes calibrated outcomes back | Feedback loop (§9) |
| 14 | **Broken-link verification at scale** | Links are regex-extracted but never checked | lychee |
| 15 | **Passive TLS grading** | Security findings are header-only | testssl.sh |
| 16 | **Vector memory** | Cannot ask "have we seen this defect or objection before?" | sqlite-vec + qwen3-embedding |
| 17 | **Market-anchored price confidence** | `mm_intelligence.pricing()` is cost-based only; no range tied to comparable jobs | Comparable-job table + confidence band |
| 18 | **Saved-snapshot re-audit loop** | Cannot prove a past client's fix actually worked | Snapshot store + diff |

### 12.2 Hygiene gaps

| # | Missing | Impact |
|---|---|---|
| 19 | **No root `docker-compose.yml` / Dockerfile** | Nothing is portable or restartable |
| 20 | **Broken `./mm` runtime** | The CLI is dead |
| 21 | **`tests/` symlink shadows the real tests** | pytest discovery and tooling confusion |
| 22 | **No gitleaks / pre-commit** | The documented leak will recur |
| 23 | **CI covers only Tier-1 tests + one smoke audit** | The main pipeline has no regression protection |
| 24 | **CI Python 3.11 vs `requires-python` ≥3.11 vs host 3.9** | Environmental drift is guaranteed |
| 25 | **Log rotation unimplemented** (package exists, wiring unclear) | Unbounded disk growth under 24/7 operation |
| 26 | **Dead-letter triage has no CLI** | Recovery requires manual SQL |
| 27 | **No operator runbook** (`CONTINUITY_UPGRADE_PLAN.md` lists it as P2) | New operator is blocked |
| 28 | **`KEY_ROTATION.md` exists but no rotation tooling** | Keys stay stale until they leak |
| 29 | **NZ outreach-law compliance not encoded** | UEMA 2007 / Privacy Act 2020 exposure |
| 30 | **`robots.txt` / ToS compliance is per-check, not systematic** | `AuditOptions.respect_robots` exists, but audits are not provably compliant end-to-end |

  a recorded purpose, and a path to honour correction/deletion requests.
  `mm_suppression` is the start of this, not the whole of it.


---

## 13. THINGS TO REMOVE OR REPLACE

| # | Item | Verdict | Reason | Replacement |
|---|---|---|---|---|
| 1 | `money-machine/.venv-email` symlink → `/Users/yabigdd/MoneyMachine/.venv-email` | **REMOVE** | Broken; hardcodes another user's home path | A real venv *inside the container* — the host needs no Python at all |
| 2 | Symlinks `config`, `control-plane`, `migrations`, `scripts`, `tests` → `money-machine/` | **REMOVE** | `tests/` shadows real tests and breaks discovery; the rest creates two names for one path, which is exactly how "I edited the wrong file" happens | Use real paths |
| 3 | **Public Nominatim / Overpass for POI harvesting** | **REJECT / REMOVE from the plan** | ✅V OSMF policy: *"downloading all POIs in an area"* is *"strictly forbidden and will get you banned"*; reselling geocoding is barred | NZBN bulk extract + watchlists (free); Geofabrik `nz-latest.osm.pbf` for geo, or a **self-hosted** Nominatim |
| 4 | `auditor_toolkit/ai.py` → `/Users/dd/llama-2-7b-chat.Q4_K_M.gguf` | **REPLACE** | Absolute home path; 2023-era model; **no vision**; the pinned SHA256 makes swapping models painful | Env-configured model ids; `qwen3-vl:8b` / `qwen3:8b`; keep a checksum check but make the path configurable |
| 5 | `@deepseek-ai/dsh@0.1.6-alpha.2` + `integrations/deepseek-harness/` | **REMOVE (or freeze as clearly-unused)** | The pinned version was never published (own plan says npm `latest` = `0.1.5-rc.2`); Docker absent; the bridge adds an agent lane with no live consumer | Keep `plugin/`, `policies/` as a *pattern reference* only |
| 6 | Four competing auditors: `website_auditor.py` (384 L), `website_auditor_enhanced.py` (1,088 L), `ultimate_auditor.py` (37 KB), `auditor_toolkit/`, `engines/detect.py` | **CONSOLIDATE** | Five implementations of one capability; the README documents only one; `mm_workers.py` calls yet another (`engines/detect.py`). This is the largest maintainability defect in the repo | Keep **`auditor_toolkit/`** (packaged, installable, versioned finding registry, real tests) + `engines/detect.py` as the worker entrypoint; move the rest to `legacy/` and mark deprecated |
| 7 | `data_collection: allow` in `config/routing.yaml` | **REPLACE with `deny`** | Combined with free-tier providers that train on inputs, this is a client-confidentiality leak | `deny`, plus a local-only allowlist for confidential content |
| 8 | Static `disposable_email_blocklist.conf` (124 KB) + unreferenced `source.json` | **REPLACE** | Stale snapshot; nothing refreshes it; it will silently degrade verification accuracy | Scheduled refresh task + version + provenance record |
| 9 | `LLAMACPP_BASE` / `OLLAMA_BASE` hardcoded defaults (`127.0.0.1:8080` / `:11434`) | **REPLACE** | Only correct on the bare host; wrong the moment you containerise | Compose service DNS (`http://ollama:11434`), overridable by env |
| 10 | Legacy duplicate `mm_*` tables mirroring original tables | **CONSOLIDATE (P2)** | The prior scan already flagged legacy duplication. Dual-write paths are how data drift starts | One canonical table per concept + a documented view for compatibility |
| 11 | Hunter / Verifalia as *primary* verification | **DEMOTE to optional** | Both are paid beyond small free tiers; Verifalia's free allowance is credit-limited/trial ⛔ | Free-first consensus (DNS/MX/blocklist/reputation), then Reacher in a container, then paid only if the operator opts in |
| 12 | `nuclei` **active** templates against third-party sites | **RESTRICT** | Active scanning of a site you don't own can be unlawful and will get you blocked | Passive/baseline only, off by default, consent documented |
| 13 | Firecrawl **hosted** API | **REJECT** | Cloud is paid; self-host is AGPL-3.0 ⚠️ | Self-host only, if needed at all |
| 14 | Celery / Redis / RabbitMQ | **REJECT** | Two extra daemons to replace a working SQLite leased queue | Existing `mm_pipeline.claim()` with lease expiry |
| 15 | Twenty CRM (and to a lesser extent EspoCRM) | **REJECT** | AGPL-3.0, ~750 MB, 4 services, **no native workflow automation or reporting** — less capable than the existing SQLite CRM + `mm_*` tables for this specific pipeline | Keep the bespoke CRM; add a read-only reporting view |
| 16 | Lightpanda **as the rendering tier** | **RESTRICT** | ✅V It has **no graphical rendering engine** — it cannot screenshot. Also AGPL-3.0 | Use it for cheap HTML crawl only; Playwright/Chromium for rendering |
| 17 | `mark_sent.py` | **REVIEW/HARDEN** | `PROOFER_SPEC.md` records it fabricated send events | Make it write only to `outreach_send_ledger` after a real transport receipt |
| 18 | `kill_contacts.py` / `fix_contacts.py` / `seed_data.py` (163-byte scripts) | **QUARANTINE** | Unlabelled mutation scripts with no guards against running on the live DB | Move to `tools/oneoff/` with a `--yes-really` guard |


---

## 14. FULL TOOL DISCOVERY CATALOGUE

Every candidate found, with the verdict you asked for. Sorted by pipeline stage.
**Verdicts: INSTALL NOW · TEST · OPTIONAL · REJECT.**

### 14.1 Business discovery

| Tool / source | Purpose | Why useful here | Licence / price | HW / Docker | API / CLI | Difficulty | Risks / limits | Verdict |
|---|---|---|---|---|---|---|---|---|
| **NZBN API** (`api.business.govt.nz`) | Authoritative NZ business register | ✅V **"There is no fee for using this API."** Bulk JSON/CSV extract (monthly), **change-event watchlists with push notifications**, Business Match service, BIC industry codes. Gives real identity *and* a change feed — the single best discovery upgrade available | **Free ✅V** | trivial | REST; key, optional OAuth2 | Medium (approval + key) | Approval required; Wed 21:00–23:00 NZ maintenance window; not all legacy entity types support watchlists | **INSTALL NOW** |
| **Geofabrik OSM extracts** (`nz-latest.osm.pbf`) | Bulk OSM data off-network | ✅V OSMF's own recommended alternative to API harvesting: *"If you need complete sets of data, get them from the OSM planet or an extract."* Lets you harvest POIs **without** touching the public API | ODbL (free) | ~1 GB extract; `osm2pgsql`/DuckDB | File-based | Medium | ODbL share-alike; attribution | **INSTALL NOW** |
| **Self-hosted Nominatim** | Geocoding + POI search you own | Removes every public-API restriction; unlimited query rate | GPL-2.0 / ODbL | 4–8 GB RAM, Docker | REST | Hard | Heavy for a modest machine; needs the OSM extract | OPTIONAL (P2/P3) |
| **Public Nominatim / Overpass API for POI harvesting** | — | — | — | — | — | — | ✅V **Policy violation: banned, reselling barred, generic LLM-driven use disallowed** | **REJECT** |
| **SearXNG** *(already in stack)* | Private meta-search | No keys, no cost, aggregates many engines; the discovery front door | AGPL-3.0 | ~120 MB, Docker | REST | Easy (installed) | Must self-host; result quality varies | **INSTALL NOW (existing)** |
| **Common Crawl** | Bulk web corpus for candidate extraction | Free petabyte-scale crawl index for finding NZ `.co.nz` sites at scale | Free | large storage/compute | S3 / index files | Hard | Enormous volume; noisy; needs hard filtering | OPTIONAL (P3) |
| **OpenCorporates** | Global registry aggregation | Broader than NZBN | ⚠️ Free tier limited/non-commercial; bulk paid | — | REST | Easy | **Not reliably $0** for commercial use | OPTIONAL / ⛔ bulk |
| **NZ trade directories** (NZS.com, NoCowboys, Yellow NZ, Master Builders, Site Safe) | Trade-directory discovery | Real high-intent NZ trade businesses — your ICP | Public web | n/a | Scrape (respect each ToS/robots) | Medium | ⚠️ Per-site ToS must be checked individually | **TEST** |
| **Google Places API / Maps** | Local business data | Best coverage | ⛔ **Billed**; credit is time-limited and card-gated | — | REST | Easy | Will create charges if misused | **REJECT** |
| **Lightpanda** | Cheap HTML crawl for discovery | ✅V 16× less memory / 9× faster than Chromium on raw fetching; ideal for bulk first-pass discovery | AGPL-3.0 ⚠️ | ~123 MB peak/100 pages; Docker | CDP / Playwright-compatible | Easy | ✅V **No graphical rendering — cannot screenshot.** Incomplete JS/WASM compliance. AGPL network clause | **TEST** (discovery crawl only) |

### 14.2 Identity resolution

| Tool / project | Purpose | Why useful | Licence | HW | API/CLI | Difficulty | Risks | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Splink** | Probabilistic record linkage / dedup | ✅V MIT; DuckDB backend; ✅V *"linking a million records on a laptop in around a minute"*; **unsupervised — no training data needed**; interactive visualisations | MIT ✅V | laptop-class | Python API | Easy | Blocking rules + cluster threshold need tuning | **INSTALL NOW** |
| **DuckDB** | Embedded analytics over SQLite/CSV | Fast joins and aggregations with no server | MIT | ~50 MB | CLI + Python | Easy | Not a transactional store | **INSTALL NOW** |
| **Public Suffix List** (`publicsuffix2`) | Registrable-domain extraction | Canonical `co.nz` handling — essential for `.co.nz`, `.govt.nz`, `.org.nz`, `.net.nz` | MPL-2.0 | trivial | Python lib | Easy | Must be refreshed periodically | **INSTALL NOW** |
| **ProjectDiscovery `httpx` / `dnsx`** | Fast live-host + DNS resolution | Bulk-canonicalises discovered hosts; CSV/JSON output | MIT | Go binary | CLI | Easy | ⚠️ Only probe hosts you are entitled to probe | **TEST** |
| **`recordlinkage`** | Simpler entity resolution | Easy active-learning path | MIT | pip | Python | Easy | Slower / less scalable than Splink | OPTIONAL |
| **Qdrant** | Vector DB for fuzzy entity matching | High-quality ANN search | Apache-2.0 | Docker | REST | Medium | Overkill at current data volume | OPTIONAL (P3) |


### 14.3 Contact discovery

| Tool | Purpose | Why useful | Licence | HW | API/CLI | Difficulty | Risks | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Trafilatura** *(already a dependency)* | Main-content + metadata extraction | Already installed; extend it to pull contact blocks, `mailto:`, schema.org `Organization`/`LocalBusiness` | Apache-2.0 | pip | Python | Easy | — | **INSTALL NOW (extend)** |
| **`mailto:` / `tel:` / schema.org extraction** | First-party contacts | Highest-provenance contacts: published by the business itself | — | — | code | Easy | — | **INSTALL NOW** |
| **Playwright** *(already an optional dep)* | Render JS-driven contact pages | Many NZ sites hide contact info behind JS or interstitials | Apache-2.0 | ~400 MB | Python/CLI | Easy | Heavy; rate-limit politely | **INSTALL NOW** |
| **SearXNG site-scoped queries** | `site:example.co.nz "@example.co.nz"` | Finds indexed staff emails without crawling the whole site | AGPL-3.0 | existing | REST | Easy | Results can be stale/cached | **INSTALL NOW** |
| **Hunter.io** | Email discovery | Convenient; already in use | ⚠️ Free ≈25 searches/mo; paid beyond | — | REST | Easy | **Not $0** at real volume; opaque provenance | OPTIONAL |
| **`theHarvester`** | OSINT email/host collection | Free, broad | GPL-2.0 | pip | CLI | Medium | Noisy; false positives; ToS/ethics care | OPTIONAL |
| **Firecrawl (self-hosted)** | Crawl→clean markdown at scale | Good extraction quality | ⚠️ AGPL-3.0; cloud is paid | Docker | REST | Medium | AGPL; heavy; unnecessary given Trafilatura + Playwright | OPTIONAL |
| **Firecrawl (hosted API)** | — | — | ⛔ Paid | — | — | — | **Will create charges** | **REJECT** |

### 14.4 Email verification

| Tool | Purpose | Why useful | Licence | HW | API/CLI | Difficulty | Risks | Verdict |
|---|---|---|---|---|---|---|---|---|
| **`check-if-email-exists` (Reacher)** | SMTP/MX/disposable/catch-all/role verification | Most complete open verifier: reachability, syntax, MX, disposable, SMTP, deliverability, disabled, full inbox, catch-all, role account | ⚠️ **AGPL-3.0 ✅V** (dual-licensed; a paid commercial option exists — **not MIT**) | Rust binary / Docker (~50 MB) | HTTP backend + CLI + library | Easy | ⚠️ **Needs outbound port 25**, commonly blocked. ⚠️ AGPL §13 network clause — keep it a *separate service* called over HTTP; do **not** link it into your code | **TEST** (isolated container only) |
| **`dnspython`** *(already a dependency)* | MX/SPF/DMARC lookup | Deterministic, free, no SMTP needed — the backbone that works when port 25 is blocked | ISC | pip | Python | Easy | Cannot confirm a mailbox exists | **INSTALL NOW** |
| **SPF / DKIM / DMARC checks** | Domain email posture | Strong defensible signal, *and* a sellable finding for the client | — | — | code | Easy | — | **INSTALL NOW** |
| **Disposable-domain list (refreshable)** | Blocklist | Cheap deterministic filter | MIT / public domain | trivial | code | Easy | Must be versioned + refreshed; currently static | **INSTALL NOW** |
| **`email-validator`** (Python) | Syntax + deliverability heuristics | Lightweight first gate | CC0 | pip | Python | Easy | Heuristics only | **INSTALL NOW** |
| **Verifalia** | Commercial verification | Robust catch-all handling | ⛔ Free allowance credit-limited/trial | — | REST | Easy | **Not $0** | OPTIONAL / ⛔ |
| **ZeroBounce / NeverBounce / Abstract** | Commercial verification | — | ⛔ Paid | — | — | — | **Not $0** | **REJECT** |
| **Gravatar lookup** | Weak identity corroboration | Free corroborating signal (exposed by Reacher) | Free | — | HTTP | Easy | Corroborating only | OPTIONAL |


### 14.5 Website auditing — performance, SEO, accessibility, links, security

| Tool | Purpose | Why useful | Licence | HW | API/CLI | Difficulty | Risks | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Unlighthouse** | Whole-site Lighthouse with UI + smart sampling | ✅V MIT, 4.9k★, **Node ≥ 22.18.0**, fully local, no paid tier. Turns unmeasured "slow site" into a defensible defect set with score history | MIT ✅V | Node 22.18+ & Chrome | CLI (`npx unlighthouse`) | Easy | Needs Node 22.18+; one Chrome per worker | **INSTALL NOW** |
| **Lighthouse / Lighthouse CI** | Single-page CWV + perf/SEO/a11y/best-practice scores; budgets; score history | The canonical engine; LHCI adds assertions and trend history | Apache-2.0 | Chrome | CLI | Easy | Lab data only (no field CWV) | **INSTALL NOW** |
| **`axe-core` CLI** | WCAG 2.x conformance | ✅V dual-licensed MIT **or** MPL-2.0 — genuinely free. The same engine inside Chrome DevTools; produces WCAG-tagged findings | MIT OR MPL-2.0 ✅V | Node | CLI | Easy | Automated rules catch only ~30–50% of issues; never claim full conformance | **INSTALL NOW** |
| **Pa11y** | CI-oriented a11y runner atop axe | Convenient reporting + CI integration | MIT | Node | CLI | Easy | Overlaps axe — pick one to avoid duplicate findings | OPTIONAL |
| **IBM Equal Access Checker** | Second a11y engine for consensus | Independent rule set → stronger evidence when two engines agree | Apache-2.0 | Node | CLI | Easy | More false positives | OPTIONAL |
| **lychee** | Fast async broken-link checker (Rust) | ✅V 3.9k★, **MIT / Apache-2.0** dual; stream-based; Docker; checks HTML, Markdown **and mail addresses**; caching + rate limiting | MIT / Apache-2.0 ✅V | tiny | CLI + GitHub Action | Easy | Does **not** execute JS by default — pair with Playwright for SPA links | **INSTALL NOW** |
| **`linkinator`** | JS-rendered link checking | Complements lychee for SPA/JS links | MIT | Node | CLI | Easy | Slower | OPTIONAL |
| **`sitespeed.io`** | Broader perf suite (Browsertime + coach) | Deepest free perf analysis incl. video/filmstrip | MIT | Node + Docker | CLI | Medium | Heavier config | TEST |
| **CrUX API** | **Real field** Core Web Vitals | Field data beats lab data for credibility ("your real users experience X") | Free (key) | trivial | REST | Easy | Only for sites with enough traffic; small NZ sites often have no data | **TEST** |
| **`web-vitals` JS library** | Measure real CWV on a page you control | Enables post-remediation monitoring — a natural recurring-revenue hook | Apache-2.0 | n/a | JS | Easy | Requires deployment to the client's site | OPTIONAL |
| **`webanalyze`** | Tech-stack detection (Wappalyzer port) | Far more complete than the regex `plugins/tech_stack_detector.py` | MIT | Go binary | CLI | Easy | Fingerprint DB needs updating | **INSTALL NOW** |
| **`testssl.sh`** | TLS/cipher/certificate grading | ✅V GPL-2.0. High credibility, low risk; produces a letter grade a business owner understands | GPL-2.0 ✅V | tiny (bash) | CLI | Easy | Some checks are semi-active — restrict to grading, be polite | **INSTALL NOW** |
| **`sslyze`** | Python TLS scanner | Scriptable alternative | AGPL-3.0 ⚠️ | pip | Python | Easy | AGPL; separate process | OPTIONAL |
| **OWASP ZAP** (baseline/passive) | Passive DAST | Deeper than header checks | Apache-2.0 | Docker ~700 MB | REST/CLI | Medium | ⚠️ **Active scanning of third-party sites can be unlawful** — passive/baseline only, off by default | **TEST (passive)** |
| **`nuclei`** | Template-driven checks | Huge free template library (exposed panels, outdated CMS) | MIT (some templates restrictive ⚠️) | Go binary | CLI | Easy | ⚠️ Dual-use; rate-limit bypass by design; **never** run actively against sites you don't own | **TEST (passive)** |
| **`pip-audit` / `osv-scanner`** | Dependency CVE scan **of your own code** | Protects *you*, not the client — and is fully legitimate | Apache-2.0 | pip | CLI | Easy | — | **INSTALL NOW** |
| **Google PageSpeed Insights API** | Lighthouse-as-a-service | No local Chrome needed | ⚠️ Free **with a key**; the key in this repo is **leaked and must be rotated** | — | REST | Easy | Per-key quota; leaked key | OPTIONAL (rotate first) |
| **Screaming Frog SEO Spider** | Desktop SEO crawler | Excellent | ⛔ Free tier capped at 500 URLs and **not for commercial client work** | desktop | GUI | Easy | **Licence forbids the commercial/client use case you have** | **REJECT** |


### 14.6 Screenshots, rendering, visual analysis, mockups

| Tool | Purpose | Why useful | Licence | HW | API/CLI | Difficulty | Risks | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Playwright (Python)** *(already an optional dep)* | Full-page screenshots, multi-viewport, PDF | Already dependency-declared, and Chromium is installed in this workspace. The rendering tier | Apache-2.0 | ~400 MB/instance | Python/CLI | Easy | Memory; one browser per worker | **INSTALL NOW** |
| **Gotenberg** | HTTP API: URL/HTML→PDF, **URL→screenshot**, PDF/A, **PDF/UA**, merge/split/encrypt, LibreOffice 100+ formats | ✅V MIT, 13.1k★, Docker, **no paid tier or telemetry**. Removes Chromium and font management from the app entirely; PDF/UA is an accessibility selling point | MIT ✅V | ~250 MB idle, Docker | REST | Easy | Needs a Chromium-capable container | **INSTALL NOW** |
| **odiff** | Fast pixel diff with anti-aliasing detection | Turns before/after into a quantified delta instead of two images side by side | MIT | tiny | CLI/Node | Easy | — | **INSTALL NOW** |
| **pixelmatch** | Minimal pixel diff | Zero-dependency fallback | ISC | tiny | JS / Python port | Easy | Slower than odiff | OPTIONAL |
| **BackstopJS** | Visual regression harness | Scenario runner with reference/diff reporting | MIT | Node + Chrome | CLI | Medium | Config-heavy; overkill for one-off mockups | OPTIONAL |
| **`qwen3-vl:8b`** | Local VLM for design critique | 6.1 GB, 256K ctx, Apache-2.0 ✅V — strongest local general-purpose VLM at this tier | Apache-2.0 | 12 GB VRAM / ~7 GB RAM | Ollama | Easy | Slow on CPU; English-centric | **INSTALL NOW** |
| **Gemini free-tier vision** | Remote VLM for design critique | Frontier-quality visual reasoning at $0 | ⚠️ Free tier trains on content ✅V | none | REST | Easy | ⚠️ **Public data only**; never client-confidential images | **TEST** |
| **`glm-ocr`** | OCR specialist | 2.2 GB; extracts text from screenshots, invoices and scanned quotes — feeds the quote/invoice engine | 🔶R | 8 GB | Ollama | Easy | OCR only, no reasoning | **INSTALL NOW (if OCR needed)** |
| **WeasyPrint** | HTML→PDF, pure Python | No Chromium needed; good for simple reports | BSD-3 | pip | Python | Easy | Weaker CSS support than Chromium | OPTIONAL |
| **Typst** | Modern typesetting | Beautiful deterministic PDF output; tiny and fast | Apache-2.0 | tiny binary | CLI | Medium | New template language | OPTIONAL |
| **Pandoc** | Universal document conversion | Markdown→DOCX/PDF/HTML — lets clients receive their preferred format | GPL-2.0 | ~150 MB | CLI | Easy | — | OPTIONAL |
| **ScreenshotOne / Urlbox / Browserless (cloud)** | Hosted screenshot APIs | Convenient | ⛔ Paid (free tiers trial-sized) | — | REST | Easy | **Will create charges** | **REJECT** |
| **AI website-redesign / mockup SaaS** | Auto-generate a "new design" | Exactly the stated goal | ⛔ All paid SaaS | — | REST | Easy | **Not $0** — and they would own your differentiator | **REJECT** |


---


### 14.7 AI models, inference and routing

| Tool | Purpose | Why useful | Licence | HW | API/CLI | Difficulty | Risks | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Ollama** | Local model runtime + OpenAI-compatible API | Zero-cost, offline, single binary; already the assumed endpoint | MIT | 8–16 GB RAM | REST/CLI | Easy | CPU-only inference is slow; one generation at a time | **INSTALL NOW** |
| **`llama.cpp` / `llama-server`** | Lowest-level GGUF inference | Already referenced in your router; best control over quantisation and threads | MIT | as above | REST/CLI | Medium | Manual model management | **INSTALL NOW (keep route)** |
| **LiteLLM** | Unified OpenAI-compatible proxy over 100+ providers | **One** integration surface for Groq, Gemini, Cloudflare, OpenRouter, SambaNova and Ollama — instead of hand-writing an adapter per provider. Also provides budget caps | MIT | pip | Python proxy | Easy | It *can* route to paid models — configure an allowlist **and** a hard $0 budget cap | **INSTALL NOW** |
| **`qwen3:8b` / `qwen3:14b`** | Orchestration, judging, drafting | Apache-2.0; native tool calling ✅V | Apache-2.0 | 5–9 GB | Ollama | Easy | 14B slow on CPU | **INSTALL NOW** |
| **`qwen2.5-coder:7b`** | Remediation code snippets | Purpose-built for code | Apache-2.0 | ~5 GB | Ollama | Easy | — | **INSTALL NOW** |
| **Llama-3-Groq-Tool-Use (8B)** | Highest-reliability local tool calling | ✅V 89.06% BFCL at 8B — best self-hostable tool-caller at this size | 🔶R | ~6 GB | Ollama/GGUF | Easy | Tuned for tools only; poor general chat | **TEST** |
| **Cohere Command-R 35B** | Multi-step tool use + RAG | ✅V documented specialist | 🔶R **CC-BY-NC** ⚠️ | 24 GB+ | Ollama | Medium | ⚠️ **Non-commercial licence — incompatible with selling client work** | **REJECT** |
| **`sentence-transformers`** | Local embeddings runner | Standard, well-supported | Apache-2.0 | pip | Python | Easy | — | **INSTALL NOW** |
| **`qwen3-embedding:0.6b`** | Embeddings for dedup/retrieval | MTEB multilingual #1 at launch for its class ✅V | Apache-2.0 ✅V | ~0.6 GB | Ollama | Easy | — | **INSTALL NOW** |
| **`bge-m3`** | Hybrid dense+sparse+ColBERT embeddings | One forward pass replaces embed + lexical + rerank ✅V | MIT ✅V | ~1 GB | Ollama/models | Easy | Larger index | OPTIONAL |
| **OpenRouter (`:free`)** | Diverse free model access | ✅V 20 RPM / 50 RPD (<$10) → 1,000 RPD | Free tier ✅V | none | REST | Easy | ⚠️ Very low RPD; shared-pool 429s at peak | **INSTALL NOW (with quota ledger)** |
| **Groq** | Fast free inference | ✅V/🔶R ~30 RPM / 1,000 RPD, no card | Free tier 🔶R | none | REST | Easy | Org/model-level limits | **INSTALL NOW** |
| **Google AI Studio (Gemini)** | Free frontier + **vision** | ✅V generous permanent free tier incl. image understanding; `gemini-embedding-2` text embeddings **free of charge** | Free tier ✅V | none | REST/SDK | Easy | ⚠️ **Trains on your content**; limits were cut before; verify live | **INSTALL NOW (public data only)** |
| **Cloudflare Workers AI** | Free daily compute allocation | ✅V/🔶R 10,000 Neurons/day, no card | Free tier 🔶R | none | REST | Easy | Neurons ≠ tokens; eligibility varies | **TEST** |
| **SambaNova Cloud** | Extra free fallback | 🔶R 20 RPM / 20 RPD, no card | Free tier 🔶R | none | REST | Easy | 20 RPD is very tight | OPTIONAL |
| **Hugging Face Inference Providers** | Long-tail model access | 🔶R $0.10/mo free credits | Free tier 🔶R | none | REST | Easy | Tiny credit | OPTIONAL |
| **Cerebras free trial** | Very fast inference | 🔶R 1M TPD | ⛔ **30-day trial, card required** | — | REST | Easy | **Expires; card needed** | **REJECT** |
| **Together AI** | Model variety | 🔶R $100 signup credit | ⛔ Trial | — | REST | Easy | **Expires** | **REJECT** |
| **OpenAI / Anthropic APIs** | Frontier quality | Best models | ⛔ Paid; Anthropic has **no** permanent free API tier 🔶R | — | — | — | **Breaks the $0 rule** | **REJECT** |
| **`vLLM`** | High-throughput local serving | Best throughput with a GPU | Apache-2.0 | needs GPU | REST | Hard | GPU required; overkill now | OPTIONAL |
| **`llama-swap`** | Hot-swap multiple local models | Avoids reload latency across many roles | MIT | RAM | config | Easy | More RAM held | OPTIONAL |

## 15. STEP-BY-STEP IMPLEMENTATION ORDER

| # | Action | Effort |
|---|---|---|
| 1 | Colima + Docker; root `compose.yaml`; `python:3.12-slim` app/worker/scheduler, `restart: unless-stopped` | 1–2 days |
| 2 | Ollama service; pull `qwen3-vl:8b` + `qwen3:8b`; router healthcheck + prewarm | 1 day |
| 3 | Add Groq / Gemini / CF Workers AI routes; `FREE_TIER_ALLOWLIST`; `data_collection: deny` | 1 day |
| 4 | Unlighthouse + axe-core in the audit fan-out | 1–2 days |
| 5 | Splink entity resolution; `canonical_entity_id`; NZBN bulk load | 2 days |
| 6 | Gotenberg + screenshot diff (odiff) for before/after evidence | 1–2 days |
| 7 | Gatus + watchdogs + healthchecks on every service | 1 day |
| 8 | Secrets hardening: Keychain, gitleaks in CI, rotate leaked keys | 0.5 day |
| 9 | promptfoo eval harness + fixture regression tests | 2 days |
| 10 | lychee + testssl.sh passive security lane | 1 day |
| 11 | Windmill scheduler trial (keep existing state machine) | 1 day eval |
| 12 | NZ outreach-law compliance layer (permission basis, unsubscribe, suppression) | 2–3 days |
| 13 | sqlite-vec + local embeddings retrieval (P2) | 2 days |

---

## 16. FINAL OPTIMIZED ARCHITECTURE DIAGRAM

```
              ┌─────────────────────────────────────────────────┐
              │ SCHEDULER  (Windmill / supervisor --daemon)      │
              │ cron: discover 6h · audit 1h · verify 15m        │
              │        · follow-up 1h · health 5m · eval daily   │
              └───────────────────────┬─────────────────────────┘
                                      │ enqueue(state=…)
┌─────────────────────────────────────▼──────────────────────────────────────────┐
│                    LEASED QUEUE  (SQLite, existing — no Celery/Redis)           │
│      claim(states, worker_id, lease_seconds) · retry · dead-letter              │
└──┬─────────┬──────────┬───────────┬───────────┬──────────┬──────────┬─────────┘
   │         │          │           │           │          │          │
┌──▼───┐ ┌───▼────┐ ┌───▼─────┐ ┌───▼──────┐ ┌──▼─────┐ ┌──▼─────┐ ┌─▼──────┐
│DISCOV│ │IDENTITY│ │ CONTACT │ │  VERIFY  │ │ AUDIT  │ │ SCORE  │ │ DRAFT  │
└──┬───┘ └───┬────┘ └────┬────┘ └────┬─────┘ └───┬────┘ └───┬────┘ └───┬────┘
  NZBN    Splink      crawl+     consensus     FAN-OUT:    rubric     templates
  +OSM    +PSL        trafilatura of 4         ├ toolkit    + EV       + local AI
  selfhost+DuckDB     +schema.org  signals      ├ Unlighthouse intervals (confidential
  +SearXNG            +mailto      (no port-25  ├ lychee                stays local)
                      provenance   reliance)    ├ axe-core                   │
                                                ├ testssl.sh (passive)       │
                                                └ vision critique ◄──────────┘
                                                       │
                     ┌─────────────────────────────────▼─────────────────────┐
                     │ JUDGE (independent, adversarial) → PROOFER (facts)     │
                     │  any fabricated claim = FAIL → returns upstream        │
                     └─────────────────────────────────┬─────────────────────┘
                     ┌─────────────────────────────────▼─────────────────────┐
                     │ HUMAN APPROVAL GATE (unchanged, per-message)           │
                     │ APPROVAL_PENDING → [operator] → SEND (or never)        │
                     └─────────────────────────────────┬─────────────────────┘
                    OUTCOME CAPTURE → EVAL (promptfoo / GEPA) → back into prompts

 DATA: SQLite+WAL(+sqlite-vec) · run-ID artifacts · Gatus · GlitchTip (optional)
 AI:   qwen3:8b (tools) · qwen2.5-coder:7b (fixes) · qwen3:14b t0 (judge/proofer)
       qwen3-vl:8b (vision) · qwen3-embedding:0.6b (retrieval) · Groq/Gemini free failover
 AGENTS: Hermes / Goose / OpenCode via CLI-as-tool + scoped MCP · no mutation tools
```

---

## 17. PRIORITIZED BACKLOG

- **P0 (unblocks everything):** Dockerise · Ollama + role-routed model stack ·
  provider-failover routes (Groq/Gemini/CF) · NZBN discovery/identity backbone ·
  discovery compliance (self-hosted OSM) · Splink dedup · Unlighthouse ·
  axe-core · vision design critique · provider-health router.
- **P1 (2–4 weeks):** email-verification consensus (AGPL isolation + port-25
  fallback) · disposable-list refresh · lychee · testssl.sh passive · Gatus ·
  promptfoo · GEPA · Gotenberg · screenshot diffing · secrets hardening ·
  `data_collection: deny` · delete symlink aliases.
- **P2 (1–2 months):** sqlite-vec + embeddings · Windmill scheduler · NZ
  outreach-law compliance layer · dead-letter triage CLI · migration version table.
- **P3 (later):** GlitchTip error tracking · Qdrant (only if sqlite-vec is outgrown) ·
  self-hosted Nominatim · scorer retraining loop.

---

*Machine-readable companion: `UPGRADE_RESEARCH_2026.yaml` (validated with PyYAML).
Licence marks per §0 verification legend. Nothing in this plan creates a charge;
anything with a card requirement or trial expiry is listed as REJECT.*
