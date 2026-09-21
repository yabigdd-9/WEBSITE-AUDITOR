# Contributing to the local toolkit

Use `.venv/bin/python -m pytest toolkit_tests -q` and `.venv/bin/ruff check auditor_toolkit toolkit_tests`. Real browser tests are opt-in: `WA_BROWSER_E2E=1 .venv/bin/python -m pytest toolkit_tests/test_browser_e2e.py -q`. They use local fixture servers only. Legacy integration tests are separate because the repository includes a symlinked money-machine suite and unrelated databases.

Register new checks with stable IDs, categories, versions and limitations. A check returning findings is successful execution; a thrown exception is an error. Never assign health to an incomplete required profile. Use bounded Fetcher calls, atomic artifacts, stable finding identities and escaped report text. Do not store cookie values, credentials or authorization headers.

Tests must cover behavior and failure propagation with deterministic fixtures. Browser/PDF tests must inspect real output; AI templates are not evidence that llama.cpp generated text. Document every incomplete acceptance item.

Do not replace source files with code copied from conversation attachments. Those files are historical evidence. Preserve source references, imported report schemas and existing integration policies. Do not add connector dispatch, recurring jobs, Git mutation or external delivery to default commands.
