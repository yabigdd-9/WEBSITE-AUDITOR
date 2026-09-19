# DeepSeek Harness integration

This directory adds DeepSeek Harness as a **secondary agent execution lane** for WEBSITE-AUDITOR. Hermes remains the scheduler/master control plane; the existing deterministic Python and `money-machine/mm` interfaces remain authoritative.

## Pinned compatibility target

- DeepSeek Harness CLI: `@deepseek-ai/dsh@0.1.6-alpha.2`
- Integration plugin: `dsh-website-auditor-tools@0.1.0`
- Profile: `website-auditor`, cloned from the shipped `headless` profile

Harness is still developer-preview software. Run it with least privilege and keep this integration isolated from production credentials.

## What is implemented

The local bundle under `plugin/` registers six model-facing tools:

- `website_auditor_status` — read runtime, queue, polish and doctor state.
- `website_auditor_audit_site` — run one deterministic public-site audit.
- `website_auditor_email_status` — read Email Finder V2 provenance/status.
- `website_auditor_outreach_plan` — create the existing local review plan only.
- `website_auditor_email_find` — bounded discovery, disabled by default.
- `website_auditor_demo_qa` — deterministic demo QA, disabled by default.

The plugin does **not** expose arbitrary shell through its bridge and has no tool for sending mail, approving outreach, recording sends, payments, refunds, secrets or deployment.

## Install

From the repository root:

```bash
npm install -g @deepseek-ai/dsh@0.1.6-alpha.2

# dsh plugin uses pnpm for profile dependency management.
corepack enable
corepack prepare pnpm@latest --activate

bash integrations/deepseek-harness/scripts/install_profile.sh
```

The installer creates/uses a dedicated `website-auditor` profile based on the shipped headless profile and installs the local plugin bundle.

## Local Ollama — zero paid tokens

Copy/merge `settings.ollama.example.yaml` into your DSH settings. Then:

```bash
export OLLAMA_API_KEY=ollama
ollama list
curl -s http://127.0.0.1:11434/v1/models
```

If the model ID differs, replace it in the example settings with the exact value from `ollama list`.

No paid fallback is configured by this integration. Provider failure should fail/queue the job rather than silently purchasing inference.

## Headless run

```bash
bash integrations/deepseek-harness/scripts/run_headless.sh \
  "Use website_auditor_status with view=doctor. Report blockers only."
```

The headless runner uses Harness JSON events so Hermes or another supervisor can parse progress and preserve a session id.

## Direct bridge smoke tests

These do not require a model:

```bash
python3 integrations/deepseek-harness/scripts/dsh_mm_bridge.py runtime
python3 integrations/deepseek-harness/scripts/dsh_mm_bridge.py doctor
python3 integrations/deepseek-harness/scripts/dsh_mm_bridge.py email-status --business-id 5
python3 integrations/deepseek-harness/scripts/dsh_mm_bridge.py audit-site \
  --url https://example.co.nz \
  --output outputs/deepseek-harness/example-audit.json
```

Mutation-capable tools fail closed. Enable them only for a supervised test:

```bash
export DSH_MM_ALLOW_BOUNDED_WRITES=1
python3 integrations/deepseek-harness/scripts/dsh_mm_bridge.py email-find --business-id 5
```

That flag still does not create any send/approval/deploy capability.

## Hermes dispatch pattern

Hermes should remain the scheduler and launch one-shot Harness jobs:

```text
Hermes
  -> queue task
  -> run_headless.sh
  -> DSH JSON event stream
  -> Website Auditor tool bundle
  -> restricted bridge
  -> deterministic WEBSITE-AUDITOR / mm
  -> evidence result
  -> Hermes validation/judge
  -> human gate for external action
```

Recommended initial tasks are audits, research, independent critique and code review. Do not allow production outreach during the shadow phase.

## Safety boundaries

1. Do not provide Gmail credentials, master `.env`, SSH keys or deployment keys to the Harness process.
2. Keep `DSH_TELEMETRY_MODE=DISABLED` for commercial prospect data unless deliberately changed after review.
3. Treat third-party plugins as trusted host code and review them before installation.
4. Keep the existing Email Finder V2 and UEMA consent gate authoritative.
5. Do not set `DSH_MM_ALLOW_BOUNDED_WRITES=1` for unattended operation until the shadow benchmark passes.
6. Keep a Git/database backup before supervised mutation tests.

## Acceptance gate

Promote beyond shadow mode only after:

- existing WEBSITE-AUDITOR tests remain green;
- bridge guardrail tests pass;
- Email Finder V2 precision/regression checks do not degrade;
- no secret appears in Harness logs/events;
- private/local audit targets are blocked by the bridge;
- sending/approval/deploy remain unavailable;
- one free-provider outage fails closed without paid fallback;
- five shadow prospects complete successfully;
- twenty-prospect Hermes-only vs Harness-only vs combined comparison is reviewed.

See `policies/permissions.yml` for the machine-readable boundary.
