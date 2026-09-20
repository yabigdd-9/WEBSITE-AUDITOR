# WEBSITE AUDITOR

Evidence-first website auditing for NZ businesses — detect defects, generate fix suggestions, track remediation progress, and optionally plan policy-controlled automatic actions. The core remains **free** and local-first.

## What It Does

| Tool | Purpose |
|------|---------|
| `website_auditor.py` | Single-site audit — 25+ checks (SSL, mobile, SEO, security, performance) |
| `full-pipeline.py` | 9-step pipeline — scout, audit, discover emails, generate mockups, rank, export |
| `remediation-engine.py` | Auto-generate fix suggestions with code snippets and effort/cost estimates |
| `audit-dashboard.py` | Safe self-contained HTML dashboard with opportunity + health scoring and stable finding IDs |
| `python -m website_auditor.cli actions …` | Policy-controlled action registry, approvals, dry-run, audit log, verification and rollback |

## Quick Start

```bash
# Fast static audit (default)
python3 website_auditor.py https://example.co.nz --profile auto --mode static

# Deep rendered audit: Playwright + axe + Lighthouse evidence
cd audit && npm install && npx playwright install chromium && cd ..
python3 website_auditor.py https://example.co.nz --profile deep --mode rendered

# Run the full pipeline (all free, no API keys)
python3 full-pipeline.py --all

# Generate remediation plans from existing audits
python3 remediation-engine.py --all --output-dir outputs/remediations

# View interactive dashboard
python3 audit-dashboard.py --output report.html
open report.html

# One-command safe execution: audit -> remediation -> dashboard -> action dry-run
python3 run_all.py https://example.co.nz
# or
bash execute_all_safe.sh https://example.co.nz

# Action-engine status (installed editable: pip install -e ".[dev]")
wa actions status
```

## Features

### Evidence-first P0 core
- Versioned check registry with stable IDs in `auditor_core/checks.yaml`
- Typed Pydantic models for findings, evidence, checks and remediation state
- Raw page evidence with HTTP status/headers, SHA-256, size and bounded HTML snippet
- Sensitive response headers such as `Set-Cookie` are redacted from stored evidence
- Transparent category health scores with per-category confidence and deductions
- Deterministic site-type detection plus quick/standard/deep/ecommerce/leadgen/NZ profiles
- Static audit mode and optional rendered mode using the existing Playwright/Lighthouse/axe engine
- Remediation lifecycle: detected → acknowledged → scheduled → in progress → patched → verified/regressed
- Legacy `score` is retained for compatibility and explicitly labeled as an opportunity/defect score; category scores use 100 = healthier

### Policy-controlled automatic actions
- Stable action registry with risk classes and idempotency keys
- Default policy: `mode=dry_run`, `execution_enabled=false`
- Approval queue and domain/scope authorization records
- Append-only NDJSON audit log
- Emergency kill switch: `wa actions pause` / `wa actions resume`
- Per-hour execution rate limit
- Environment-only secret resolver; secrets are not stored in repo policy JSON
- Connector interface with a safe local connector and blocked/unavailable external connectors
- Local verification and rollback for generated artifacts
- External email, DNS/TLS, external connectors, and production changes remain blocked by default
- Policy lives at `action-policy.json` because this repo already uses the top-level `config` path for another object

Useful commands:

```bash
wa actions init
wa actions propose --from-remediations outputs/remediations
wa actions dry-run
wa actions list
wa actions approve --id act_xxx --approver Dion
wa actions authorize --domain example.co.nz --scope remediation --actor Dion
wa actions execute --id act_xxx
wa actions rollback --id act_xxx
wa actions pause
```

`execute` still obeys the policy file. With the shipped defaults it becomes a dry-run and cannot create an external effect.

### Auditor Checks (25+)
- SSL certificate validity & expiry
- Mobile viewport / responsive detection
- Page title & meta description
- H1 tag presence
- Image alt text
- Contact form detection
- Broken link scanning
- Page load speed
- HTML validation errors
- Security headers (HSTS, CSP, X-Frame-Options)
- robots.txt & sitemap.xml detection
- Structured data (Schema.org)
- Open Graph / Twitter card tags
- Canonical URL
- Copyright year freshness
- Privacy policy link
- Cookie consent banner
- Social media links
- GDPR signal detection

### Remediation Engine
- Maps each defect to a fix library with:
  - Step-by-step fix instructions
  - Ready-to-use HTML/code snippets
  - Effort estimates (minutes/hours)
  - Cost (most are free; paid options noted)
  - Priority ranking (P0 = revenue-critical → P12 = cosmetic)
- Backward-compatible: infers fix from defect text even without `defect_key`
- Outputs per-domain JSON + HTML patch files

### Dashboard
- Self-contained HTML (no server needed)
- Score distribution with HOT/WARM/NURTURE/COLD tier coloring
- Sortable, filterable defect table
- Export to CSV/JSON
- Trend comparison (when multiple audits per domain exist)

### Pipeline v3 Fixes
- Removed duplicate `elif` branches
- Added `--recheck-days N` flag — skip sites audited within N days
- Async batch processing for 10x speed on large prospect lists
- Cached HTTP responses (24h TTL) to avoid re-fetching

## Output Structure

```
audits/                  # Per-domain audit JSONs
outputs/
  remediations/          # Fix suggestions + HTML patches
  dashboard.html         # Interactive report
email-discovery.json     # Email contacts found during pipeline
outreach-ranking.csv     # Ranked prospect list
cold-emails/             # Generated outreach drafts
```

## Execution Boundary

Automatic-action architecture is available, but **live execution is disabled by default**. The shipped policy can plan, dry-run, log, approve, authorize, verify, and roll back safe local artifacts. It does **not** send external email, change DNS/TLS, modify live websites, deploy production code, or invoke paid AI services unless a future connector is explicitly configured and its policy gates are deliberately changed.

High-risk actions remain approval- and authorization-gated. The emergency kill switch overrides action execution.

## DeepSeek Harness integration

An experimental secondary agent lane is available under `integrations/deepseek-harness/`.

It adds an installable DeepSeek Harness tool bundle around a restricted allowlist of deterministic Website Auditor and MoneyMachine operations. Hermes remains the intended scheduler/master control plane. Harness does not replace the Email Finder V2 evidence rules, the consent gate, or human approval.

The integration is pinned to `@deepseek-ai/dsh@0.1.6-alpha.2` and defaults to zero-paid-token local Ollama routing. Mutation-capable tools are disabled unless the operator explicitly enables the supervised bounded-write flag. No send, approval, payment, deployment, secret-reading, or arbitrary-shell capability is exposed through the bridge.

Start with:

```bash
bash integrations/deepseek-harness/scripts/install_profile.sh
bash integrations/deepseek-harness/scripts/run_headless.sh \
  "Use website_auditor_status with view=doctor. Report blockers only."
```

See [the Harness integration guide](integrations/deepseek-harness/README.md) for Ollama configuration, guardrails, Docker isolation and the shadow-mode acceptance gate.

## Requirements

- Python 3.11+
- No API keys needed (free stack only)
- Optional: `aiohttp` for async batch mode (`pip install aiohttp`)

## License

MIT — use freely for client work, internal audits, or agency pipelines.
