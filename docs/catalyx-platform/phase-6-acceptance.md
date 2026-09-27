# Catalyx Phase 6 acceptance evidence

**Revision:** `b1bf406e113deee6239ef07e5ad44988ca3ffde3`  
**Run date:** 2026-09-28  
**Environment:** local Python 3.11.16, synthetic accounts and disposable SQLite
databases; no production data, outbound SMTP, model provider, or public site.

## Automated results

| Check | Command | Result |
| --- | --- | --- |
| Catalyx web and security integration suite | `.venv/bin/python -m pytest -q toolkit_tests/test_catalyx_web.py` | 68 passed; one upstream Starlette/httpx deprecation warning |
| Customer-to-admin browser journey and accessibility sweep | `WA_CATALYX_WEB_BROWSER_E2E=1 .venv/bin/python -m pytest -q toolkit_tests/test_catalyx_web_browser_e2e.py` | 1 passed in 15.79 seconds |

The browser journey uses a temporary database and local mailbox. It exercises
synthetic registration, local email verification, site authorization, MFA
admin sign-in, and review queue approval. Its accessibility checks cover
document structure, accessible names, keyboard focus order, rendered text
contrast, small viewport reflow, and enlarged text on the pages in the test.

## Limits and remaining gates

These results establish the listed local automated behavior at the stated
revision only. They are not a human screen-reader session, complete WCAG 2.2 AA
conformance assessment, production-provider test, PostgreSQL concurrency test,
or staging/release approval. The proposed Phase 6 scope remains pending owner
ratification; phases 7–9 remain gated by provider, privacy/legal, hosting, and
release decisions. No soak test was run in this check.
