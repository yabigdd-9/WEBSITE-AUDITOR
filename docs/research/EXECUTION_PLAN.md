# EXECUTION PLAN — P0+P1 (concrete, verifiable)
Interpreter: /Users/dd/.local/bin/python3.11 (repo needs >=3.11; system python3 is 3.9)
Docker: NOT on this host — all Docker items deferred to Docker machine.

## P0 (do first, in order)
- [x] requirements.txt: dnspython, email-validator, tldextract, aiosmtplib, pyyaml
- [x] .gitleaks.toml created; ci.yml: ruff + gitleaks + toolkit pytest
- [x] auditor_toolkit/identity.py (canonical_domain tldextract + fallback)
- [x] auditor_toolkit/verify.py (local consensus, >=0.75 + first-party gate)
- [x] auditor_toolkit/fetch_chain.py (L1 Lightpanda/Crawl4AI -> L2 Playwright -> L3 urllib)
- [x] toolkit_tests/test_p0_upgrades.py (2 tests)
- [ ] P0-1 deps: pip install httpx bs4 lxml trafilatura textstat pyyaml requests aiohttp yarl into 3.11, then pytest test_p0_upgrades (expect 2 passed)
- [ ] P0-2 validate ci.yml YAML parses
- [ ] P0-3 rotate PAGESPEED + RANKNIBBLER keys (manual, dashboards)
- [ ] P0-4 deprecation headers on ultimate_auditor.py + website_auditor_enhanced.py -> wa.py/auditor_toolkit
- [ ] P0-5 docker-stack.yaml up on Docker host (redis, gotenberg, mailpit, kuma, beszel)

## P1 (after P0 green)
- [ ] P1-1 wire fetch_chain L3 into full-pipeline.py fetch() fallback; L1 behind env
- [ ] P1-2 lychee broken-link stage
- [ ] P1-3 Overpass NZ packs integrations/discovery/overpass_nz.py (1rps, 24h cache)
- [ ] P1-4 sqlite-vec + FTS5 + WAL migration
- [ ] P1-5 evals/golden/ (50 sites + 200 emails) + promptfoo config + nightly job
- [ ] P1-6 keychain secrets + quote guardrails (min/max + needs-visit)
- [ ] P1-7 mm dead-letter show/retry + Dramatiq queues (needs Redis)

## Verify each step
- py_compile changed files; pytest target file; git diff --stat review.
- Never send outreach without approval gate; SMTP probe opt-in SMTP_PROBE=1 only.
