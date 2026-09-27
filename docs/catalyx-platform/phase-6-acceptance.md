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
| Link crawl | `lychee --no-progress --verbose http://127.0.0.1:4174/` | 17 total links checked, 11 unique, zero errors |
| Lighthouse mobile lab runs | Lighthouse 13.5.0 with Chrome for Testing 153.0.8010.12; serial runs against the loopback preview | Eight routes scored 100 for accessibility, best practices, and SEO; performance scored 99–100. LCP was 0.92–1.06 s, CLS 0, TBT 0–104 ms. |

Pages measured: `/`, `/how-it-works`, `/what-we-check`, `/security-and-privacy`,
`/pricing`, `/sample-report`, `/privacy`, and `/terms`. The `/privacy` draft
scored 99 for performance because of render-blocking and unused shared CSS;
the other seven routes scored 100. Per-page lab metrics and fetch timestamps are
in the compact [Lighthouse page summary](/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-phase6-lighthouse-pages.json)
(SHA-256 `09b7e241af761a01b36e22462f2abafef71a29dbf50a9ec998f2059a623f706c`).

The browser journey uses a temporary database and local mailbox. It exercises
synthetic registration, local email verification, site authorization, MFA
admin sign-in, and review queue approval. Its accessibility checks cover
document structure, accessible names, keyboard focus order, rendered text
contrast, small viewport reflow, and enlarged text on the pages in the test.

## Limits and remaining gates

These results establish the listed local automated behavior at the stated
revision only. They are not a human screen-reader session, complete WCAG 2.2 AA
conformance assessment, production-provider test, PostgreSQL concurrency test,
or staging/release approval. Lighthouse used mobile emulation with simulated
throttling; TBT is a lab metric, not field INP. Lychee and Lighthouse were
limited to the loopback preview. The full Lighthouse JSON report is saved at
`/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-phase6-lighthouse.json`
(SHA-256 `b10f51cee2b977f195f24271da3ed9de6659f5240dfa28fa48dc2e027288e868`).
That full report contains the homepage run; the compact summary covers all six
eight routes. The full privacy-draft report, including its CSS audit details, is
saved at
`/Users/dd/Documents/Codex/2026-09-27/i-ll-generate-the-master-execution/outputs/catalyx-phase6-lighthouse-privacy.json`
(SHA-256 `62b363c87a744b168380cc7d0208a3ef35f0b7eace41c8a9daa107a0e504e04b`).
The proposed Phase 6 scope remains pending owner ratification; phases 7–9
remain gated by provider, privacy/legal, hosting, and release decisions. No
soak test was run in this check.
