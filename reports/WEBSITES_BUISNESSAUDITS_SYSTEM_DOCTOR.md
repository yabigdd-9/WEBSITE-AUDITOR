# WEBSITES/BUISNESSaudits — system doctor

macOS 15.7.9 x86_64, account yabigdd. Git 2.39.5, gh 2.100.0 authenticated to yabigdd-9, Node 26.8.1 and npm/npx 11.19. The environment capture records resolved binaries, version/help stdout and return codes. No optional application was upgraded.

The actual failure was a flattened repository layout plus stale launchers: root scripts/tests/migrations/control-plane paths were missing although source existed in money-machine/. Relative compatibility links now expose the same source. Missing historical regression fixtures were recovered byte-for-byte from the intact external checkout; their provenance is recorded separately from fresh validation.

The old Python 3.9 environment cannot run this source reliably. A verified Python 3.14.7 environment on the external drive was used for repair tests. The first new-environment attempt selected Apple Python 3.9.6 via generic python3, so pip could not select the pinned dnspython 2.8.0. This newly created attempt was preserved in work/ and replaced using the explicit Python 3.14.7 executable. The local environment is therefore restored from the exact installed distribution files after checking versions and copied-file hashes; pip check and imports are verified separately. No pins or global packages are changed. See local-runtime evidence for dependency and import checks, and local-installation.json for the launchers actually installed.

Hermes capability checks pass; model execution is blocked. Ollama 0.33.3 daemon/API responds but list/ps are empty. Docker is missing; OpenCode 1.18.29 help works. These optional states do not block deterministic auditing. OpenHands/browser-use are not required or activated. Browser verification reused installed Playwright/Chromium; no browsers or models were downloaded.

The CRM backup passes integrity_check and foreign_key_check. Final status commands use read-only SQLite. Existing data and observation policy remain unchanged. Tests use disposable databases. Python 3.14 reports old test connection cleanup ResourceWarnings; they are not hidden or represented as production failures.

Evidence is in the sibling outputs/evidence directory. All times in evidence are UTC; this run occurred 13 September 2026 in Pacific/Auckland.
