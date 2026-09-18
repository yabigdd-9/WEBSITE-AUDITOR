--- 
name: money-engine
description: "Use when extending the Money Engine lead pipeline."
version: 1.3.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [money-engine, website-auditor, lead-pipeline, email-verification, outreach, exa-search, lead-discovery]
    related_skills: []
---

# Money Engine Extension Guide

The Money Engine (`/Users/dd/WEBSITE-AUDITOR/money-machine/`) is an evidence-first, deterministic cold-outreach pipeline. **It never fabricates data, never calls LLMs in the core flow, and never lets external sources override first-party observation.**

## Always-On Rules

1. **External sources are corroboration only.** Third-party data (Hunter.io, Exa, directories) can seed new candidates and boost scores, but can NEVER reach `VERIFIED_HIGH` without first-party page observation.

2. **Zero fabrication.** Every email must have a captured source URL, capture hash, and observed timestamp. No guessed addresses, no LLM hallucinations.

3. **Deterministic gates dominate hard gates.** A single hard rejection (wrong domain, disposable, former employee, SMTP rejection) drops the candidate to `REJECTED` with score 0.

4. **Production persistence is gated.** The `email_policy` table has modes: `shadow`, `v2`, `v1_hold`. The `email_release_policy` table can hold production writes in `POST_DEPLOYMENT_OBSERVATION` mode.

5. **Append-only evidence.** Tables have `BEFORE UPDATE` and `BEFORE DELETE` triggers that abort. Never modify evidence — append new observations.

6. **Suppression overrides everything.** Check `mm_suppression` (by address), `mm_deals` (stage='SUPPRESSED'), `contacts` (do_not_contact=1), and `mm_contact_evidence` (unsubscribe_state).

## Project Layout

```
WEBSITE-AUDITOR/
├── .venv-email/              # Python venv (source .venv-email/bin/activate)
├── money-machine/            # Core pipeline code
│   ├── mm_core.py            # DB connection, stage changes, eligibility
│   ├── mm_operator.py        # CLI: intake, audit, outreach, score, exa-*, email-*
│   ├── mm_intelligence.py    # Pricing, scoring, experiment assignment
│   ├── mm_email.py           # Scoring engine, verification(), evaluate()
│   ├── mm_email_store.py     # DB migrations, persistence, release gates
│   ├── mm_email_cli.py       # find_one(), human_text(), shadow()
│   ├── mm_exa.py             # Exa SDK wrapper (ExaSearch, ExaAgent, check_exa_available)
│   ├── hunter_enrichment.py  # External corroboration (Hunter.io)
│   ├── hunter_cli.py         # Hunter CLI (loads .env, calls hunter_enrichment)
│   ├── mm_outreach.py        # Draft generation, send flow, audit_packet(), plan()
│   ├── mm_audit_workflow.py  # Static HTML audit packet generator
│   ├── bridge_audits.py      # Bridge static audits → DB + Hunter enrichment
│   ├── email_acceptance.py   # Release gate: shadow → regression → promote
│   ├── status_cli.py         # Single-dashboard status view
│   ├── email_finder.json     # Verifier config flags
│   ├── migrations/           # SQL migrations directory
│   └── test_exa.py           # Exa unit tests
├── prospects/                # Per-prospect packets, briefs, demos, evidence
│   └── <business>/
│       ├── packet/packet.json
│       ├── packet/APPROVAL_PACKET.md
│       ├── brief.json        # Outreach brief (signals, recipient)
│       ├── demo/index.html
│       └── case/*.html       # Captured evidence pages
├── audits/                   # Static audit JSON files (bridged into DB)
├── tests/ → money-machine/   # Symlink: tests/ points to money-machine/
├── .env                      # API keys (gitignored)
└── env.example               # Template
```

## CLI Invocation

The `mm` file is a **POSIX shell script** (`#!/bin/sh`), not Python. Run it via `bash mm`:

```bash
cd /Users/dd/WEBSITE-AUDITOR
source .venv-email/bin/activate
bash mm status                 # Read state, show next action
bash mm exa-status             # Check Exa API availability
bash mm outreach-plan --brief prospects/heat-force/brief.json
bash mm outreach-audit --packet prospects/heat-force/packet/packet.json
bash mm email-status 5         # Check email state for business 5
```

**Pitfall**: Running `python3 mm` fails with `SyntaxError: invalid syntax` (it's shell, not Python). The `bash mm` wrapper invokes `.venv-email/bin/python` internally.

**Pitfall**: `.env` is NOT auto-loaded by the venv. When a command needs API keys (Hunter, Exa), load them first:
```bash
export $(grep -v '^#' .env | xargs -L 1)
```

## Workflow: Bridge Audits → DB + Hunter Enrichment

```bash
cd /Users/dd/WEBSITE-AUDITOR
source .venv-email/bin/activate
export $(grep -v '^#' .env | xargs -L 1)
.venv-email/bin/python money-machine/bridge_audits.py
```

**Pitfall**: Without `.env` loaded, Hunter enrichment is silently skipped with `SKIPPED: HUNTER_API_KEY not set`. The bridge still inserts businesses — it just doesn't enrich them.

**Pitfall**: Re-running the bridge on already-inserted domains reports `Skipped N already-present domains` and does NOT re-enrich. To force re-enrichment, call `hunter_enrichment.enrich_business()` + `store_enrichment()` directly in Python.

## Workflow: Outreach Packet → Plan → Audit

```bash
# 1. Generate outreach plan from brief
bash mm outreach-plan --brief prospects/heat-force/brief.json

# 2. Audit the packet (validates draft matches plan)
bash mm outreach-audit --packet prospects/heat-force/packet/packet.json
```

**Known bug (2026-09)**: `outreach-preflight` is parsed in `mm_operator.py` (line 155) but has no handler in the main if/elif dispatch chain. It falls through to a `KeyError` caught as `BLOCKED: 'brief'`. Use `outreach-plan` instead.

**Known bug (2026-09)**: `outreach-audit` calls `audit_packet()` which expects `packet['brief']` to exist at the top level of `packet.json`. Current packets store `brief` in a separate `brief.json` file. Workaround: use `outreach-plan --brief <brief.json>` directly.

## Workflow: Email Release Gate

To move from `POST_DEPLOYMENT_OBSERVATION` to a mode that allows production email persistence:

1. Run shadow tests: `bash mm email-shadow --persist`
2. Run acceptance regression: `.venv-email/bin/python money-machine/email_acceptance.py`
3. If acceptance passes, promote: `UPDATE email_release_policy SET mode='v2' WHERE id=1`

Until promotion, `email-find` raises `POST_DEPLOYMENT_OBSERVATION: use isolated observation; production email persistence is held`. This is **by design**.

## Key Schema Facts

- `mm_suppression(address, reason, created_at)` — **no business_id column**. Filter by address only.
- `contacts(business_id, address_or_channel, do_not_contact)` — `do_not_contact=1` suppresses.
- `email_policy(id, mode, changed_at, acceptance_hash)` — singleton table, id always 1.
- `mm_deals(business_id, stage, ...)` — stage machine. `VERIFIED` requires evidence confidence >= 0.7.
- `mm_evidence(business_id, url, observation, limitation, checked_at)` + `mm_evidence_meta(evidence_id, status, method, confidence, ...)` — hash-attested capture.
- `mm_evidence` confidence < 0.7 is a **blocking gate** for `change_stage`. External search sets 0.5 intentionally — first-party observation required to advance.

## Integration Pattern: Adding an External Source

1. **Create adapter module** (`money-machine/<source>_search.py` or `<source>_enrichment.py`)
2. **Create CLI** (`money-machine/<source>_cli.py`) with migrate/search/enrich/verify/status commands
3. **Create migration** (`money-machine/<source>.sql`) with append-only table + triggers
4. **Wire into scoring** in `mm_email.py`: add weight to `WEIGHTS`, condition in `verification()`
5. **Wire into `find_one`** in `mm_email_cli.py`: call after identity established, merge into legacy
6. **Add tests** (`money-machine/test_<source>.py`) covering safety, cache, status, idempotency

## Exa Search Integration

**Module**: `money-machine/mm_exa.py`  
**Install**: `pip install exa-py` (in `.venv-email`)  
**CLI**: Commands are wired into `mm_operator.py` (not a separate CLI file). All exa-* commands live in the `elif a.cmd in (...)` block alongside pricing and intake.

### Python API

```python
from mm_exa import ExaSearch, ExaAgent, check_exa_available

client = ExaSearch()  # reads EXA_API_KEY from env/.env

# Raw retrieval with highlights (default, fast ~2s)
results = client.search("HVAC Auckland contact", num_results=10)

# Structured synthesis (Exa LLM, includes grounding)
result = client.search_with_output_schema(
    "plumbing companies Auckland",
    output_schema={"type": "object", "properties": {...}},
    system_prompt="Prefer official sources, collapse duplicates."
)
print(result["output"]["content"])   # synthesized JSON
print(result["output"]["grounding"]) # field-level citations

# Content extraction for known URLs
# highlights=True is fast (~2s); text={"max_characters": N} is slow (10s+)
content = client.get_contents(["https://example.co.nz"], highlights=True)
full_text = client.get_contents(["https://example.co.nz"], text={"max_characters": 5000})

# Multi-step async research (Agent API)
agent = ExaAgent()
run = agent.create_run(
    query="Find plumbing companies in Auckland with recent funding",
    output_schema={"type": "object", "properties": {"companies": {"type": "array", "maxItems": 5}}},
    effort="auto",
    max_cost_dollars=5.0
)
result = agent.poll_run(run["run_id"], max_wait_seconds=120)
if result["status"] == "completed":
    print(result["output"]["structured"])
```

### CLI Commands (in `mm_operator.py`)

```bash
# Health check — key + SDK availability
bash mm exa-status

# Search → JSON results (raw retrieval, no DB writes)
bash mm exa-discover --query "emergency plumber Auckland" --num-results 10

# Fetch content for known URLs (highlights by default)
bash mm exa-fetch --urls https://example.co.nz

# Structured synthesis with schema (Exa LLM)
bash mm exa-structured --query "..." --schema-file schema.json

# Intake from a known URL
bash mm intake --name "..." --url "..." --region "Auckland" --source "manual"
```

### Evidence-First Rules for Exa

- Exa results are **corroboration only** — they seed candidates but never reach `VERIFIED_HIGH` without first-party observation.
- `exa-pipe` captures highlights as evidence at confidence **0.5** — `change_stage` blocks advancement past VERIFIED (requires 0.7+). First-party verification is still required for commercial claims.
- `output_schema` synthesis and `exa-agent` runs are LLM-powered — treat output as hypotheses requiring independent verification. Always check `output.grounding` for citations.
- **Speed rule**: Use `highlights=True` (default) for evidence capture (~2s). `text={"max_characters": N}` is slow (10s+) and frequently times out — reserve for cases where downstream reasoning truly needs broad page context.
- Agent runs are async — `create_run` returns immediately. Always `poll_run` to completion and check `status == "completed"` before reading output.
- Agent runs cost money (default cap $5). Always set `effort` explicitly and `max_cost_dollars` when budgeting matters.

### Daily Operator Integration

`mm_operator.py run_day()` includes `exa_suggestions` when the human queue drops below 5 items:
- Checks `mm_exa.check_exa_available()`
- Generates one suggestion per distinct region in the pipeline
- Renders as `EXA SUGGESTIONS` block in dashboard HTML/JSON
- Rationale: "Pipeline has fewer than 5 active queue items; external discovery can add candidates."

### Database Writes via Exa

`exa-intake` and `exa-pipe` perform DB writes:
- Check for duplicates by `name` (casefold) AND `public_website` host (via `public_url()`)
- Insert into `businesses` + `mm_deals` (stage='DISCOVERED')
- `exa-pipe` additionally: calls `get_contents`, writes highlights to `evidence/exa/<bid>.txt`, inserts `mm_evidence` + `mm_evidence_meta` at confidence 0.5, attempts `change_stage` to VERIFIED (blocked by confidence gate)
- Always record `limitation` field: "External retrieval corroborates only; first-party verification required."

## Invocation — NOT Docker

This project does **not** use Docker. Running `docker compose` produces `no configuration file provided: not found`. The project runs as a Python venv with a CLI runner:

```bash
cd /Users/dd/WEBSITE-AUDITOR
source .venv-email/bin/activate
python3 run.py status          # read state, show next action
python3 run.py checkpoint "<task>"
python3 run.py report
python3 run.py rebuild
python3 mm_operator.py exa-status
```

**Pitfall**: If you see `ModuleNotFoundError: No module named 'yaml'`, install it:
```bash
.venv-email/bin/pip install pyyaml
```

## Common Pitfalls

- **`mm` is shell, not Python**: Run `bash mm`, never `python3 mm`.
- **`.env` not auto-loaded**: Export keys before hunter/exa commands: `export $(grep -v '^#' .env | xargs -L 1)`.
- **Schema discovery**: Use `PRAGMA table_info(table)` before writing queries. The schema is in `mm_core.py` `SCHEMA` string.
- **Evidence confidence gate**: `mm_evidence_meta.confidence < 0.7` is a blocking gate for `change_stage`. External search sets 0.5 intentionally. Don't raise it artificially.
- **mm_suppression has no business_id**: Filter by address only.
- **Venv**: Always `source .venv-email/bin/activate` before running pip/python.
- **Tests symlink**: `tests/` is a symlink to `money-machine/`. Put test files in `money-machine/`.
- **Production gate**: `find_one()` calls `store.require_production_persistence(d)` which raises in POST_DEPLOYMENT_OBSERVATION mode.
- **Terminal backend**: When Docker Desktop isn't running or `iron-proxy` is unconfigured, run `hermes config set terminal.backend local`.
- **Git workflow**: `git pull --rebase` before push if remote has diverged. Use `git stash`/`git stash pop` to preserve unstaged changes across rebases.
- **API keys location**: Keys go in `.env` (gitignored). Never commit `.env`.
- **Dedup before intake**: Always check `public_url(host)` + `name.casefold()` before inserting new businesses.
- **Append-only evidence**: Evidence tables have `BEFORE UPDATE`/`BEFORE DELETE` triggers. Use `INSERT OR ... ON CONFLICT DO UPDATE` for meta, never direct UPDATE of evidence rows.
- **Exa API key**: `EXA_API_KEY` is loaded from environment or `.env` by `mm_exa.get_api_key()`. The `ExaSearch`/`ExaAgent` constructors read it lazily.
- **Agent runs are money**: Default budget cap is $5. A `find companies + enrich each` multi-step run can consume $2-5. Monitor `cost_dollars` in the run result.
- **mm_operator.py CLI dispatch**: New exa commands go in the `elif a.cmd in (...)` block alongside pricing, NOT in the DB-connected `else` block (exa commands don't need the `connect()` call until DB writes happen).