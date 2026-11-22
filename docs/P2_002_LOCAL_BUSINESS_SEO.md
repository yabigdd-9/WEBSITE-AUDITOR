# P2-002 — Local Business SEO + Entity/NAP Intelligence v38

## Core Rule
> Normalize first. Corroborate second. Flag contradictions only when materially different. Never let weak third-party data override stronger first-party evidence automatically.

## Architecture

```
auditor_toolkit/local_seo/
├── schema.py          — LocalBusinessEntity, BusinessLocation, ExternalLocalEvidence
├── nap.py             — Name/Address/Phone normalization & comparison
├── identity.py        — Entity resolution, branch-parent awareness, confidence
├── address.py         — Address component parsing, suffix expansion, rapidfuzz comparison
├── phone.py           — E.164 normalization via phonenumbers library
├── hours.py           — Opening hours normalization (Mon-Fri 9am-5pm → intervals)
├── local_schema.py    — JSON-LD extraction via extruct, schema-vs-visible comparison
├── location_pages.py  — Location page detection, classification, quality assessment
├── service_area.py    — SERVICE_AREA vs PHYSICAL_LOCATION vs HYBRID classification
├── categories.py      — Business category extraction and normalization
├── consistency.py     — Contradiction engine (FORMAT_DIFFERENCE vs REAL_CONTRADICTION)
├── corroboration.py   — External evidence with provenance (never overwrites canonical)
├── geo.py             — Haversine distance, geocoding cache, status classification
├── scoring.py         — Calibrated impact levels (HIGH/MEDIUM/LOW)
├── pipeline.py        — Orchestrated escalation: cheap first, expensive only if needed
├── report.py          — LocalSEOReport generation
└── adapters/
    ├── website.py     — NAP and schema extraction from HTML
    ├── nominatim.py   — Geocoding (rate-limited, cached, disabled by default)
    ├── overpass.py    — OSM data (stub/optional)
    └── authorized_gbp.py — Google Business Profile (OAuth-only, disabled by default)
```

## What v38 Audits
- Business name/address/phone consistency across site
- LocalBusiness/Organization structured data
- Location page detection and quality
- Service-area business classification
- Schema-vs-visible contradictions
- Geographic coordinate consistency
- Branch-parent relationships

## What v38 Does NOT Claim
- "GBP is wrong" (unless authorized GBP access exists)
- "Business doesn't rank locally" (from website evidence alone)
- "NAP inconsistency across Google" (without legitimate evidence)
- "OSM != website means website is wrong" (OSM can be stale too)

## Evidence Hierarchy
1. Direct visible page evidence
2. First-party structured data
3. Multiple first-party pages
4. Authorized business data
5. Independent geographic corroboration
6. Third-party public listing
7. Inference

## Nominatim Policy
- Max 1 request/second (enforced)
- Requires User-Agent header
- Disabled by default
- Requires caching
- Bulk mode not allowed
- Self-hosted recommended for high volume

## False-Positive Suppression
Automatically downgrade when:
- Phone difference is formatting only
- Address difference is normalization only
- Service-area business legitimately hides address
- Branch phone differs from parent phone
- Third-party data appears stale
- Schema identifies parent while visible page identifies branch

## Benchmark Output
- `reports/local-seo/benchmarks/v38-baseline.json`
- `reports/local-seo/benchmarks/P2_002_V38_BENCHMARK.md`

## Deferred
- Self-hosted Nominatim for NZ
- Commercial Places APIs
- Authorized GBP management
- Local SERP rank tracking
- Competitor ranking comparisons
- Automatic directory submission
