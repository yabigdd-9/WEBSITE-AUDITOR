# Tier 1 Enrichment — free external signals for the Website Auditor

Keyless-first layer that adds **PageSpeed/Lighthouse, deep-TLS grades,
W3C validation, urlscan history, RankNibbler SEO, and a local A+–F security
header grade** to audits — without touching the deterministic auditors.

## Sources (all live-verified 2026-09-19)

| Source | Key? | What you get | Etiquette |
|---|---|---|---|
| Local header grader | none | A+–F grade + defects from headers you already fetch | no network at all |
| W3C Nu validator | none | real HTML error count (first 10 with line numbers) | keyless, generous |
| SSL Labs v3 | none | worst-endpoint TLS grade | **cached reads only** (`startNew=off`), 7-day TTL |
| urlscan.io search | none for reads | prior scans of the host | shared 1k searches/day — cache 24h |
| PageSpeed Insights v5 | optional free `PAGESPEED_API_KEY` | Lighthouse performance/a11y/BP/SEO scores | keyless 429s often; keyed ≈25k/day |
| RankNibbler | free `RANKNIBBLER_API_KEY` (100/day) | full on-page SEO JSON | skipped cleanly without a key |

Deliberately **not** implemented: Mozilla Observatory (dead, 502),
securityheaders.com API (retired), urlscan *submission* (publishes URLs;
needs a key + human say-so), active scanners (ZAP/wapiti vs prospects).

## Use

```bash
# standalone probe — keyless, exit 0 even if everything skips
python3 -m integrations.tier1_enrichment.cli https://example.com

# with keys (paste into .env, never commit)
export PAGESPEED_API_KEY=... RANKNIBBLER_API_KEY=...
python3 -m integrations.tier1_enrichment.cli https://example.com \
  --include headers w3c ssllabs urlscan pagespeed ranknibbler

# from Python — enrich an audit dict in place (additive only)
from integrations.tier1_enrichment import enrich_audit
enrich_audit(audit, response_headers)

# or via the auditor itself
python3 website_auditor.py https://example.com --enrich
```

## Layout

- `cache.py` — disk cache under `outputs/.cache/enrichment/`, per-source TTLs,
  stale-on-failure fallback
- `graders.py` — local security-header grader (pure function, fully tested)
- `sources.py` — one async client per third-party source, all fail-closed
- `enrich.py` — `enrich_async()` + `enrich_audit()` merge (additive-only)
- `cli.py` — standalone probe
- `policies/permissions.yml` — allow/deny list incl. `ssllabs_new_assessment`
  and `urlscan_submit` bans
- `tests/` — stdlib unittest, `httpx.MockTransport`, **zero live network**

## Tests

```bash
python3 -m unittest discover -s integrations/tier1-enrichment/tests -v
```
