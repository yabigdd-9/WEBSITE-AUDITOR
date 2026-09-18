# Exa Integration Reference

Full command surface, config schema, and patterns for the Money Machine's Exa integration.

## Architecture

Two classes in `money-machine/mm_exa.py`:

| Class | Use Case | Returns |
|-------|----------|--------|
| `ExaSearch` | Single-shot retrieval | List of results or content |
| `ExaAgent` | Multi-step async research | Run ID (poll until terminal) |

Both read `EXA_API_KEY` from environment or `.env`. Both raise `RuntimeError` if key is missing.

## Config-Driven Queries

`money-machine/config/exa.yaml` defines:

```yaml
defaults:
  effort: auto
  max_cost_dollars: 5.0
  num_results: 10
  type: auto
  cron_schedule: "0 8 * * *"
  source: exa-search

regions:
  Auckland:
    queries:
      - "plumbing services Auckland New Zealand"
    num_results: 5
    max_cost_dollars: 3.0
```

Region-specific settings override defaults. The `exa-cron` command generates cronjob entries for every query in every region.

## Pipeline Flow

```
exa-pipe
  → ExaSearch.search() → results
  → Deduplicate (by name/domain)
  → INSERT businesses (source='exa-pipe')
  → INSERT mm_deals (stage='DISCOVERED')
  → ExaSearch.get_contents() → highlights
  → Write evidence file to evidence/exa/<biz_id>.txt
  → INSERT mm_evidence (method='exa-retrieval', confidence=0.5)
  → INSERT mm_evidence_meta
  → Attempt stage transition (BLOCKED by trigger — confidence < 0.7)
```

## Evidence Capture

- Exa evidence is stored at confidence 0.5 (corroboration only)
- `mm_stage_guard` blocks transitions below 0.7
- Don't "fix" the confidence threshold — external sources can't verify businesses

## Daily Operator Wiring

`mm daily` includes `exa_suggestions` when queue < 5 items:
- Checks if Exa is available (`mm_exa.check_exa_available()`)
- Suggests `mm exa-pipe` per region from existing pipeline regions

## Pipeline Metrics

The `metrics()` function tracks:
- `exa_discovered` — all businesses with source LIKE '%exa%'
- `exa_agent_discovered` — businesses from `source='exa-agent'`
- `exa_pipe_discovered` — businesses from `source='exa-pipe'`
- `manually_discovered` — businesses with non-exa source

## Auto-Intake from Agent Results

`mm exa-agent-poll --run-id <id> --auto-intake`:
- Polls until terminal status
- On `completed`, extracts `output.structured`
- Inserts each company as DISCOVERED (dedup by name)
- Sets source='exa-agent', region='agent-auto'

## Pitfalls

1. **`get_contents` with `text=true` can timeout.** Use `highlights=true` (default) for fast retrieval. Only use `text={"max_characters": N}` when full page context is required, and always wrap in try/except.

2. **`exa-pipe` is idempotent per query.** Results are deduped by name, so re-running the same query won't create duplicates. But changing the query slightly (e.g., "plumbers" vs "plumbing") may produce overlapping results.

3. **Agent API is async.** `create_run` returns immediately. You MUST poll with `poll_run` until terminal status. Don't stop at create.

4. **Exa `outputSchema` on `search()` performs LLM synthesis.** Results in `output.content` require independent verification. Use `system_prompt` to guide source preferences and dedupe behavior.

5. **`exa-cron` prints commands, doesn't create jobs.** Run the printed `hermes cronjob create` commands to actually schedule the jobs.

6. **YAML config requires PyYAML.** The `load_exa_config()` function uses `yaml.safe_load`. Install with `pip install pyyaml` — don't hand-roll a YAML parser (it's a rabbit hole).

7. **`exa-agent-poll --auto-intake` requires `output.structured`.** If the agent run returns results as `output.text` instead of `output.structured`, no intake happens. Check the schema you provide in `exa-agent-create` returns structured JSON, not a text summary.

8. **Docker builds for the money-machine need config files at `/app/config/` (root), not `/app/money-machine/config/`.** The `mm_operator` looks for `disposable_email_blocklist.conf` at `/app/config/`. When building the Dockerfile, COPY config files to `/app/config/` — not `/app/money-machine/config/`. Verify with `docker run --rm website-auditor-mm status` before pushing.

## API Decision Workflow

```
Need raw web content for your own LLM?
  → ExaSearch.search() with contents.highlights=true

Need specific fields extracted from pages?
  → ExaSearch.search_with_output_schema()

Need multi-step research (find → enrich → cross-reference)?
  → ExaAgent.create_run() + poll_run()

Already have URLs?
  → ExaSearch.get_contents()

Need to populate the pipeline from external sources?
  → mm exa-pipe or mm exa-agent-poll --auto-intake
```

## Environment Variables

| Variable | Purpose |
|----------|--------|
| `EXA_API_KEY` | Required for all Exa operations |

## File Locations

| File | Purpose |
|------|--------|
| `money-machine/mm_exa.py` | Core module (ExaSearch, ExaAgent, config loading) |
| `money-machine/config/exa.yaml` | Per-region query configuration |
| `money-machine/evidence/exa/` | Captured Exa page highlights |
