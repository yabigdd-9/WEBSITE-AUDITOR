# P0 verified baseline — 16 October 2026, Pacific/Auckland

PASS for repository preservation, consistent private backups and documented starting state. Full production readiness is not asserted.

Authoritative checkout `/Users/dd/WEBSITE-AUDITOR`: branch `integration/v44-local-machine-convergence`, HEAD `09ab41ab61656ae4b63110d4ee7d418f3fbf07b8`, matching its existing upstream at inspection. Initial inventory: 10 registered worktrees, 20 stashes, no tracked modifications, 160 existing untracked generated blueprint/draft files. The missing/prunable v32 registration was retained. `/Users/dd/WEBSITE-AUDITOR-v45` exists at `b349cd9fb23b6cf9c5a2e8a8c74691158e9cda8f`. No reset, clean, force push, stash application or worktree removal occurred. See `baseline.json` for refs and preserved-file hashes.

Source candidate is isolated in `/Users/dd/Documents/Codex/2026-10-16/hi-2/work/release-candidate`, branch `codex/hermes-production-readiness-20261016`, based on 09ab41ab. Initial implementation edits were transferred there; the authoritative tracked source was restored byte-for-byte to its recorded starting version. This is an additional worktree, not a replacement for any existing checkout.

Live scoped repairs: the `.venv` editable package incorrectly pointed to deleted `.claude/worktrees/pipeline-evidence-integration`. Its installed metadata was privately snapshotted, then repaired with an offline, no-dependency editable install. No provider/environment credential file was changed. See `environment-repair.json` and private snapshot location recorded there.

Eight databases received consistent read-only-source SQLite online backups and separate restores. All pass hash, schema/count, integrity, foreign-key and isolated transaction-rollback checks. Recovery files are private, outside Git; the independent verifier checked every pair. Nineteen narrowly scoped DB/directory/sidecar permission fixes preserve original modes in a private rollback manifest. See `runtime/database_recovery_receipt.json`, `runtime/database_permissions_receipt.json` and `verification/P11_INDEPENDENT_VERIFICATION.md`.

Runtime inventory at capture: 8 GiB RAM, approximately 12 GiB available disk; active supervisor PID 66896, one loopback FCC listener PID 99117, existing Hermes scheduler. A live process is not proof of loaded revision. The observed startup receipt belongs to another PID and historical SHA. Existing email transport is disabled, with cap zero; primary workflow ledger has zero model invocations and zero verified sends. Provider invoices are not inferred from these database counts.

Nine proven unsupported or unsafe recurring jobs were paused through the supported existing Hermes API after private scheduler snapshots. Eight existing jobs remain enabled. No replacement scheduler was installed. Full inventory, exact IDs, before/after comparisons and per-job rollback instructions are in `runtime/P9_HEALTH_AND_RECOVERY.md` and its receipts.

State reconciliation preserves the current approval queue. Root `HERMES_EXECUTION_STATE.yaml` was absent; differing worktree variants were compared and retained rather than copied over current data. `outputs/TOP_20_MONEY_ENGINES.md` agrees across inspected variants. New programme state is maintained separately as `HERMES_MASTER_EXECUTION_STATE.yaml`.
