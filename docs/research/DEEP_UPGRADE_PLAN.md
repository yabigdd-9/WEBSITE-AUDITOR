# WEBSITE-AUDITOR Deep Upgrade Plan
Date: 2026-09-21 | Constraint: $0, local-first, macOS+Docker

Evidence-first core already strong: auditor_toolkit + wa.py, full-pipeline.py resume, email-finder V2, scoring, remediation, SQLite.
Gaps: no queue/supervisor, single-lane fetch, single-verifier email, no eval loop, no screenshot/PDF service, secrets/health missing, 3x duplicate auditors.

## 1. Top 25 Upgrades
1. Crawl4AI primary extractor (trafilatura+bs4 fallback) - discovery/audit/contact
2. Playwright + Lightpanda dual-browser - audit/visual
3. Gotenberg Chromium screenshots + HTML-to-PDF - visual/reporting
4. Local email consensus (dnspython+SMTP+blocklist+Reacher) - verification
5. OSM Overpass + SearXNG discovery backbone - discovery
6. Dramatiq + Redis queue (retries, DLQ, pools) - workflow
7. SQLite WAL + FTS5 + sqlite-vec - data (Postgres only at >1M leads)
8. axe-core vendored wired into Playwright - a11y
9. Nuclei http/misconfig-light + local header grade - security (passive only)
10. tldextract + Splink/dedupe - identity resolution
11. Qwen3/Hermes local roster by role - AI reasoning (see section 3)
12. Promptfoo + DeepEval + Langfuse self-host - self-improvement
13. Uptime Kuma + Beszel - monitoring (replaces nightly_watchdog.py)
14. Supervisor daemon CONTINUITY P0 - reliability, required for 24/7
15. MCP lane: Playwright + SQLite + Fetch - plugins
16. MinIO + Litestream - artifacts + DB backup
17. n8n formalized flows - workflow (keep human approval gate)
18. Mailpit + Gmail OAuth via Keychain - outreach safety
19. Gitleaks + pip-audit + ruff in CI - security (fixes exposed keys)
20. Gotenberg PDF from existing report.html - reporting
21. lychee linkchecker (Rust) - broken links 50x faster
22. py-microdata schema validator - SEO rich results locally
23. PSI API keyed-only cached keyless-first - perf (keep tier1 pattern)
24. Quote guardrails ranges + floor - quotes
25. Canon wa.py/auditor_toolkit, deprecate ultimate/enhanced - arch

## 2. Tool Catalog (verdict: INSTALL NOW / TEST / OPTIONAL / REJECT)
- Crawl4AI (Apache-2.0, ~2GB, Easy, Docker+Py, github.com/unclecode/crawl4ai): INSTALL NOW
- Playwright keep cap-workers=2 (Apache-2.0): INSTALL NOW
- Lightpanda L1 bulk + Playwright fallback (Apache-2.0, 200MB): INSTALL NOW
- Trafilatura keep fallback (GPL-3.0): KEEP
- Lychee broken links (MIT, Docker/CLI): INSTALL NOW
- axe-core vendored inject via Playwright (MPL-2.0): INSTALL NOW
- Lighthouse CI / PSI 25k-d free cached: INSTALL NOW
- Nuclei http-misconfig only passive (MIT): TEST
- sslyze TLS (pip): INSTALL NOW
- librecrawl-technical-seo-audit-mcp (MIT): TEST
- Overpass keyless (ODbL): INSTALL NOW
- SearXNG keep + OSM/Wikidata engines (AGPL): KEEP
- Nominatim 1rps cache (ODbL): INSTALL NOW
- tldextract replace regex (BSD): INSTALL NOW
- Splink DuckDB nightly link (MIT): TEST
- python-dedupe <50k (MIT): OPTIONAL
- Local verifier dnspython+aiosmtplib+email-validator+blocklist: INSTALL NOW, require score>=0.75 + first-party
- Reacher check-if-email-exists Docker 2nd opinion (AGPL): TEST
- Verifio early OSS: TEST not prod
- Hunter 25-mo / Verifalia trial capped fallback + circuit-breaker: OPTIONAL
- Mailpit catch sends (MIT): INSTALL NOW
- Gotenberg 8 Chromium screens+PDF (MIT Docker): INSTALL NOW
- WeasyPrint: REJECT (Gotenberg covers)
- Pollinations primary: REJECT, OPTIONAL fallback
- Dramatiq + Redis 7-alpine: INSTALL NOW
- RQ fallback: OPTIONAL
- n8n keep formalize (Sustainable-Use): KEEP
- SQLite WAL+FTS5+sqlite-vec: INSTALL NOW
- MinIO + Litestream: TEST->prod
- Langfuse self-host (MIT): TEST
- Uptime Kuma + Beszel (MIT): INSTALL NOW
- Prometheus+Grafana: REJECT for now (heavy)
- Gitleaks + pip-audit + ruff: INSTALL NOW
- Promptfoo local (MIT): INSTALL NOW
- DeepEval OSS (Apache): TEST
- Ragas: OPTIONAL; Inspect AI: OPTIONAL later
- Twenty CRM self-host (AGPL): TEST, migrate follow_up_tracker.py
- Mautic (GPL): OPTIONAL if volume
- REJECT paid: Apify, Firecrawl Cloud, BrightData/ScrapingBee, ZeroBounce/Emailable paid, OpenAI/Anthropic paid, Pinecone, paid Vercel/Render.

## 3. Model Stack by Role (Ollama local, 16GB Mac)
- plan: qwen3:8b Q4_K_M (~5GB) | fallback qwen/qwen3-8b:free
- code: qwen2.5-coder:7b Q4 or hermes3:8b Q4 | fallback qwen2.5-coder-7b:free
- extract/classify/judge bulk: qwen3:4b Q4 or llama-3.2-3b Q4 (~2GB)
- proofread/draft: hermes3:8b Q4
- vision HOT-only: qwen2-vl:7b Q4 via llama.cpp | fallback qwen2-vl-7b:free
- embeddings: nomic-embed-text local for sqlite-vec dedup
- cmd: ollama pull qwen3:8b qwen3:4b qwen2.5-coder:7b hermes3:8b qwen2-vl:7b nomic-embed-text

## 4. Docker Stack
- redis:7-alpine, gotenberg:8, mailpit, uptime-kuma:1, beszel, langfuse, searxng (keep), minio, reacher, n8n (keep)
- Playwright browsers stay native on macOS (playwright install chromium); Docker Chromium CI only.
- See docker-stack.yaml companion.

## 5. MCP Stack
- playwright-mcp (npx @playwright/mcp): audit/screens/axe
- fetch-mcp -> Crawl4AI: extraction
- mcp-server-sqlite read-only + writer separated: leads/audits
- filesystem-mcp scoped outputs/,audits/,proposals/: guardrail
- librecrawl-technical-seo-audit-mcp: TEST
- mcp-zap-server passive only: OPTIONAL supervised
- Keep DSH_MM_ALLOW_BOUNDED_WRITES=0; route FS/network via MCP.

## 6-7. Workflow + Parallel Workers
- discover(Overpass+SearXNG+Nominatim) -> resolve(tldextract+Splink) -> fetch L1 Lightpanda/Crawl4AI fallback L2 Playwright -> audit fan-out x6 (perf/SEO/axe/lychee/sslyze+nuclei-light/content) -> contact x3 + verify x2 consensus>=0.75 -> score+quote guarded range -> draft Hermes-3 evidence-cited -> n8n APPROVAL GATE -> Mailpit/Gmail -> Gotenberg PDF -> Twenty CRM -> Langfuse/Promptfoo learn
- Queues: discover,fetch,audit,verify,score,draft (Dramatiq). Msg {domain,geo,niche,attempt,provenance[]}. Retry exp-backoff, DLQ after 3. Limits: Overpass 1rps, Nominatim 1rps, PSI 1qps cached 24h, SMTP 5/min/domain. Concurrency fetch=8 audit=4 (playwright cap2) verify=3 LLM=2.

## 8. Self-Improvement Loop
1. Golden set evals/golden/: 50 NZ sites labeled defects + 200 labeled emails.
2. Promptfoo nightly extractor/scorer/drafter x (4B vs 8B); keep winner if +2pct no regression.
3. DeepEval faithfulness (evidence-only) + defect precision/recall.
4. Langfuse funnel discovered->audited->verified->drafted->approved->replied->won.
5. Challenger 10pct traffic, promote on 7-day win.
6. CI gate: pytest + promptfoo --threshold 0.85 blocks merge on drop.

## 9. Reliability / Failover
- Fetch Lightpanda->Playwright->trafilatura/urllib. LLM 8B->4B->OpenRouter-free->cached summary.
- Verifier local->Reacher->Hunter/Verifalia capped, CB opens after 3x429/5xx, half-open 5min.
- Cache Redis 24h + --recheck-days 7. Backups Litestream->MinIO + restic daily.
- Kuma checks mm doctor/queue depth/disk; DLQ triage mm dead-letter show/retry.

## 10. Security + Secrets
- NOW: rotate PAGESPEED + RANKNIBBLER keys, add .gitleaks.toml + CI, pip-audit + ruff.
- Gmail OAuth to macOS Keychain (security add-generic-password), fallback age-encrypted file, mm secret rotate/status --dry-run.
- MCP filesystem scoped, SQLite MCP read-only for agents, bounded-writes 0. No intrusive scans.

## 11-12. Missing / Remove / Replace
- Missing: queue, screenshot/PDF, consensus verifier, entity resolution, eval harness, artifact store, approval sender, geocoded discovery, TLS deep-check, schema validator, rotation, runbook.
- Remove: ultimate_auditor.py + website_auditor_enhanced.py -> auditor_toolkit+wa.py; Pollinations primary -> Gotenberg; ThreadPool+watch -> Dramatiq+n8n; regex domain -> tldextract; single-verifier -> consensus; outputs/ FS-only -> MinIO; nightly_watchdog.py -> Kuma+supervisor.

## 13. Implementation Order
- P0 (~1 day): gitleaks+rotate, axe wiring, tldextract, lychee, local consensus, docker up redis/gotenberg/mailpit/kuma/beszel, supervisor P0.1-P0.4, deprecate dupes.
- P1 (2 wks): Crawl4AI+Lightpanda chain, Dramatiq DLQ CLI, Overpass NZ packs, Gotenberg diffs, sqlite-vec+FTS5, Promptfoo golden, Keychain secrets, quote guardrails.
- P2: Splink nightly, Reacher, Langfuse+MinIO+Litestream, Nuclei-light+sslyze, vision HOT-only, Twenty CRM, n8n approval hardening.
- P3: Mautic, multi-host, auto-challenger, Inspect AI, Postgres only if >1M rows.

## 14. Snippets
- canonical: use tldextract.extract(u) -> f"{d}.{s}"; score = 0.35*mx + 0.25*smtp + 0.15*not_disposable + 0.15*not_catchall + 0.10*first_party; require >=0.75 + first_party.
- routing.yaml roles: {plan: qwen3:8b, code: qwen2.5-coder:7b, extract: qwen3:4b, judge: qwen3:4b, proofread: hermes3:8b, vision: qwen2-vl:7b}; fallbacks [local-4b, openrouter-free, cached-summary].

## 15. Architecture Diagram
- Overpass+SearXNG+Nominatim -> Resolve(tldextract+Splink)->SQLite FTS/vec -> L1 Lightpanda/Crawl4AI fallback L2 Playwright -> audit fan-out (lychee/sslyze/nuclei-light/SEO/content) -> consensus>=0.75? no->archive+retry yes->Score+Quote->Draft->n8n APPROVAL->Mailpit/Gmail -> Gotenberg PDF->Twenty->Langfuse/Promptfoo; Redis/Dramatiq+Supervisor+Kuma/Beszel+MinIO/Litestream underneath.

## 16. Backlog P0/P1/P2/P3
- P0: rotate keys+gitleaks CI; axe wiring; tldextract; lychee; local consensus; Redis+Gotenberg+Mailpit+Kuma up; supervisor daemon; deprecate dupes.
- P1: Crawl4AI+Lightpanda; Dramatiq queues+DLQ; Overpass packs; Gotenberg diffs; Promptfoo golden; Keychain secrets; quote guardrails.
- P2: Splink nightly; Reacher; Langfuse+MinIO+Litestream; Nuclei-light+sslyze; vision HOT-only; Twenty CRM; n8n hardening.
- P3: Mautic; multi-host; auto-challenger; Inspect AI; Postgres if >1M.
- Install now ($0/OSS/Docker): Crawl4AI, Lightpanda, Gotenberg, Dramatiq+Redis, Lychee, sslyze, tldextract, Reacher, Mailpit, Kuma+Beszel. Keep Playwright, SearXNG, n8n, Ollama/Qwen+Hermes, trafilatura, axe.
