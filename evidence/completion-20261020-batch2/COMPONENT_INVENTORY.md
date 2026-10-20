# Observed component and ownership map

Candidate branch: `codex/completion-20261020`; base `ec86481ccd6c674c6dfee8d7856d71d97581d08f`.

Codex is the writer only in this isolated candidate. Existing canonical/Opus work remains untouched.

| Work package | Observed reusable source/evidence |
| --- | --- |
| R00 | `evidence/codex/r00-runtime-snapshot.json`; `evidence/codex/EXECUTION_STATE.json` |
| R01 | `evidence/codex/OWNERSHIP.md`; `evidence/codex/R01_RECEIVED_REVIEW.md` |
| S10 | `.gitleaks.toml`; `.github/workflows/security.yml` |
| S20 | Human-controlled action; no replacement module proposed |
| S30 | `money-machine/mm_redaction.py`; `money-machine/test_redaction.py`; `.github/workflows/security.yml` |
| C10 | `money-machine/config/routing.yaml` |
| C20 | `money-machine/mm_model_router.py`; `money-machine/scripts/fcc-bridge.py`; `money-machine/scripts/free_role_router.py` |
| C30 | `money-machine/test_router_cost_stop.py`; `money-machine/scripts/test_free_role_router.py` |
| A10 | `money-machine/runtime_bootstrap.py`; `money-machine/mm_soak.py`; `money-machine/test_runtime_bootstrap.py` |
| Q10 | `evidence/codex/q10_baseline_probe.py`; `evidence/codex/q10_fixture_source.py`; `.github/workflows/ci.yml` |
| D10 | `money-machine/mm_core.py`; `evidence/codex/RESTORE_DRILL.md`; `evidence/codex/d10-restore-receipt.json` |
| E10 | `ops/hermes_zero_token/worker_ownership.py`; `ops/hermes_zero_token/staging_db.py`; `ops/hermes_zero_token/test_standalone_ownership.py`; `ops/hermes_zero_token/test_staging_progress.py`; `ops/hermes_zero_token/test_worker_contract.py`; `money-machine/mm_transport.py`; `money-machine/mm_pipeline.py`; `ops/hermes_zero_token/runner.py` |
| E20 | `money-machine/mm_email_lifecycle.py`; `money-machine/test_email_lifecycle.py`; `money-machine/test_email_lifecycle_cli.py` |
| B10 | `money-machine/mm_workers.py`; `auditor_toolkit/packet.py`; `auditor_toolkit/quote.py`; `auditor_toolkit/proofing.py` |
| B20 | `money-machine/mm_discovery.py`; `auditor_toolkit/identity.py`; `money-machine/mm_email_network.py`; `auditor_toolkit/storage.py` |
| B30 | `money-machine/mm_intelligence.py`; `auditor_toolkit/quote.py` |
| G10 | `auditor_toolkit/runtime/readiness.py`; `money-machine/mm_intelligence_readiness.py`; `money-machine/approval_gates.yaml` |
| G20 | `auditor_toolkit/runtime/recovery.py`; `money-machine/test_pipeline_recovery.py`; `money-machine/RUNTIME_SOAK.md` |
| G30 | `money-machine/mm_soak.py`; `money-machine/test_runtime_readiness.py`; `money-machine/test_soak_discovery_recovery.py` |
| G40 | `money-machine/runtime_bootstrap.py`; `money-machine/supervisor/cli.py` |
| G50 | `money-machine/mm_transport.py`; `money-machine/mm_outreach.py`; `money-machine/config/transport.json` |
| O10 | `auditor_toolkit/runtime/resource_limits.py`; `money-machine/mm_runtime_guards.py` |
| O20 | `money-machine/mm_intelligence_calibration.py`; `money-machine/mm_intelligence_strategy.py` |

Exact hashes and top-level definition line numbers are in `component-inventory.json`.

This is a source inventory, not independent approval or proof that every required gate exists.
In particular: startup attestation is partial A10; the router cost latch is partial C20;
preview-only transport is partial E10/E20; ordinary dependency preflight is not G10 release acceptance.
