# WEBSITE AUDITOR

Evidence-first website auditing and supervised prospect workflow tooling for New Zealand businesses.

The canonical stack is local-first and zero-paid-token:

- **Audit engine:** `auditor_toolkit`
- **Audit CLI:** `wa`
- **Operator/control-plane CLI:** `./mm`
- **Durable state/queue:** SQLite + `state/`
- **Supervisor:** `./mm supervisor` + launchd on the operator Mac
- **Human workspace:** Obsidian, read-mostly and non-authoritative
- **Paid model/API policy:** disabled; maximum paid model cost is **$0**
- **Outreach:** draft/review only by default; canonical live transport remains fail-closed

## Quick start

Python 3.11 is the supported runtime.

```bash
python3.11 -m venv .venv-email
source .venv-email/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,browser,portal]' -r money-machine/requirements-email.txt
npm install
```

Run a deterministic audit:

```bash
wa audit https://example.co.nz --profile nz
```

Add rendered browser checks when Chromium/Playwright is installed:

```bash
python -m pip install -e '.[browser,portal,dev]'
python -m playwright install chromium
wa audit https://example.co.nz --profile nz --browser
```

Require locally installed Lighthouse and Lychee for a deeper operator-run audit:

```bash
wa audit https://example.co.nz --profile nz --external-tools
```

Those tools are never downloaded automatically by the audit process.

## Canonical workflow

The target flow is:

```text
discover
→ dedupe
→ identity
→ audit
→ verify
→ score
→ select
→ remediate
→ demo
→ quote
→ draft
→ human review
→ approved external action
→ measure
→ learn
```

The canonical transport remains disabled, so the flow stops at review unless a live adapter is separately approved.

### Discovery

Import a curated/NZBN/directory/OSM-style export:

```bash
./mm discover-import --file prospects.json --source nzbn
```

Use an optional self-hosted loopback SearXNG instance:

```bash
./mm discover-search   --query "plumber christchurch"   --region Canterbury   --endpoint http://127.0.0.1:8888
```

Discovery only creates `DISCOVERED` items. It does not create outreach approval or send state.

### Audit → remediation → demo → quote → packet

An audit report can be turned into reviewable local artifacts:

```bash
wa remediate outputs/toolkit/<run>/report.json   --output-dir outputs/remediation/<run>

wa demo   outputs/toolkit/<run>/report.json   outputs/remediation/<run>/remediation.json   --output-dir outputs/demo/<run>   --render

wa quote outputs/toolkit/<run>/report.json   --hourly-rate-nzd 150   --output outputs/quote/<run>.json

wa packet   outputs/toolkit/<run>/report.json   outputs/remediation/<run>/remediation.json   outputs/demo/<run>/demo.json   outputs/quote/<run>.json   --output-dir outputs/packet/<run>
```

Remediation artifacts are previews, demo renders are explicitly **local concepts**, quote bands are deterministic, and prospect packets remain `HUMAN_APPROVAL_REQUIRED`.

## Simple decision intelligence

The v43 upgrade adds a deterministic, side-effect-free decision layer:

```python
from auditor_toolkit.decision import priority_decision
```

It returns a versioned `priority_score`, `confidence`, `reason_codes`,
`blockers`, and a recommended `next_action`. Weak identity or evidence routes
to verification instead of being promoted by a model. Missing contactability
does not erase a legitimate technical opportunity.

Rendered audits can also run the safe transaction-flow probe. It may click
same-origin CTAs and inspect forms, but it blocks cross-origin requests, write
requests, form submission, payment, and checkout.

## Operator commands

Useful read-only/control-plane views:

```bash
./mm doctor
./mm health
./mm metrics
./mm errors
./mm queue
./mm dead-letter
./mm transport-status
./mm model-routes
./mm obsidian-status
```

Supervisor controls:

```bash
./mm supervisor start
./mm supervisor status
./mm supervisor health
./mm supervisor logs
./mm supervisor restart
./mm supervisor stop
```

Observability snapshots are intentionally lightweight:

- `state/health.json`
- `state/metrics.jsonl`
- `state/errors.jsonl`
- `state/dead-letter/`
- `state/worker-heartbeats/`

## Safety model

The canonical stack is fail-closed:

- no silent paid model fallback;
- external free model routes require explicit opt-in and are restricted to public/non-confidential prompts;
- provider data collection defaults to `deny`;
- guessed email patterns, MX records and catch-all results do not equal a verified recipient;
- no agent can directly write or merge to `master`;
- production remediation/deployment is separate from preview generation;
- no SMTP/Gmail/network-send implementation is approved in the canonical transport;
- high-risk actions require human review.

## Model routing

Deterministic Python is preferred first, then local models. Free external routes are optional and are disabled unless explicitly enabled:

```bash
export MM_ALLOW_EXTERNAL_FREE_MODELS=1
```

If local/free routes are unavailable, work is deferred rather than sent to a paid provider.

## Obsidian

Obsidian is the human-facing operator workspace, not the runtime database or queue.

```bash
./mm obsidian-sync
./mm obsidian-status
```

Runtime → Obsidian synchronization is read-mostly. Closing Obsidian does not stop the pipeline.

## Legacy compatibility

`website_auditor.py`, `website_auditor_enhanced.py`, `ultimate_auditor.py`, and `full-pipeline.py` are legacy/compatibility paths. New work should use `wa` and `./mm`. They are retained temporarily because older helper scripts still reference them; they should be archived only after those callers are migrated and regression-tested.

The experimental DeepSeek Harness lane remains under `integrations/deepseek-harness/` and does not replace Hermes, the canonical audit engine, Email Finder V2, approval gates, or transport policy.

## Validation

CI covers the packaged toolkit plus the portable synthetic MoneyMachine state-machine, discovery, email verification, bridge-policy, lead-qualification and packet-polish suites. Host-specific acceptance still includes current-Mac `./mm doctor`, launchd restart/crash recovery, Chromium E2E, optional Lighthouse/Lychee, local SearXNG when used, actual Obsidian sync, and the required 24+ hour unattended soak.

See `CURRENT_STATE.md`, `MASTER_PLAN.md`, and `MASTER_PLAN.yaml` for the current canonical execution state.

## License

MIT.
