# Hermes + Cline + WEBSITE-AUDITOR

This repository includes a project-local Hermes plugin at:

`.hermes/plugins/cline-bridge/`

It exposes two Hermes tools:

- `cline_status` — verifies Cline/git/repository readiness.
- `cline_delegate` — sends a coding/review task to Cline with this repository as the working directory.

## Safety and cost defaults

The bridge permits only the local `lmstudio` provider.

Default provider/model:

- Provider: `lmstudio`
- Model: `qwen3:4b`
- Repository: `/Users/dd/WEBSITE-AUDITOR`

Cline workspace rules keep live outreach, email sending, purchases, deployment, Git pushes, destructive commands, and secret disclosure blocked.

## One-time setup on the Mac

From the repository:

```bash
cd ~/WEBSITE-AUDITOR
git fetch origin
git switch integration/hermes-cline-bridge

command -v hermes
hermes --version

command -v cline
cline --version


# Configure Cline to use the local model.
cline auth lmstudio

# Enable this trusted project-local Hermes plugin for the session.
export HERMES_ENABLE_PROJECT_PLUGINS=true

# Validate then enable the plugin.
hermes plugins doctor .hermes/plugins/cline-bridge --ci
hermes plugins enable cline-bridge

# Check Hermes can see it.
hermes plugins list
hermes tools list --platform cli
```

If Cline's auth screen asks for the model, choose a locally configured LM Studio model and its loopback endpoint.

## Launch

```bash
cd ~/WEBSITE-AUDITOR
chmod +x hermes-cline.sh
./hermes-cline.sh
```

Inside Hermes, ask:

```text
Use cline_status. If ready, delegate to Cline in plan mode:
inspect the repository, identify the highest-priority blocker to continuous operation,
and return the exact files and tests needed. Do not edit yet.
```

To make an implementation:

```text
Delegate this to Cline in act mode: fix the identified blocker, keep send/outreach disabled,
run the relevant local tests, and report the diff. Do not push.
```

## Direct smoke test

This bypasses Hermes and confirms Cline itself can work in the repository:

```bash
cd ~/WEBSITE-AUDITOR
cline --json --cwd "$PWD" --provider lmstudio --model "$LMSTUDIO_MODEL" --plan --auto-approve true \
  "Inspect git status and README.md only. Do not edit anything. Summarize repository state."
```

## Change bridge settings

Hermes plugin settings live under the `cline-bridge` plugin entry in Hermes config. Keep the provider set to `lmstudio` to remain local and zero-cost.

Do not put API keys in this repository.
