# QUALIFIED PROSPECT BATCH 001 — Website Rescue Lead Engine

_Generated 2026-08-18 · **NOTHING HERE HAS BEEN CONTACTED** · outreach blocked by APR-005_

## Method

Real HTTP/TLS inspection of live homepages using `engines/detect.py`. Public data only.
Every defect below carries the machine evidence that produced it. **14/14 sites fetched
successfully.** No site was scraped beyond its own homepage plus up to 12 sampled internal
links, and no personal data was collected.

Severity weights: critical 30 · high 18 · medium 9 · low 4. Tier: HOT ≥45, WARM ≥22, NURTURE >0.

## Result: 9 of 14 have real, provable defects — 2 are worth an approach

| Tier | Score | Business site | Provable defects |
|---|---|---|---|
| WARM | 31 | www.davidrobertson.co.nz | broken internal link (404), no contact details on homepage, no social links |
| WARM | 27 | www.bcplumbers.co.nz | broken links, heavy HTML |
| NURTURE | 17 | dyerdecorating.co.nz | stale copyright, phone-only contact, heavy HTML |
| NURTURE | 13 | www.whiteandtaylor.co.nz | stale copyright, heavy HTML |
| NURTURE | 13 | www.clyne-bennie.co.nz | phone-only contact, heavy HTML |
| NURTURE | 13 | www.greenscapes.co.nz | phone-only contact, heavy HTML |
| NURTURE | 13 | prodecorators.co.nz | stale copyright, heavy HTML |
| NURTURE | 4 | www.jcconstruction.co.nz | no social links |
| NURTURE | 4 | www.tbir.co.nz | no social links |
| CLEAN | 0 | cohesive.net.nz | — do not contact |
| CLEAN | 0 | www.stroudhomes.co.nz | — do not contact |
| CLEAN | 0 | www.clsonline.co.nz | — do not contact |
| CLEAN | 0 | egn.co.nz | — do not contact |
| CLEAN | 0 | a1decorating.co.nz | — do not contact |

Full machine output with per-defect evidence: `outputs/scan_nz_real.json`.

## Best single piece of provable proof found

`www.davidrobertson.co.nz` links to `https://www.davidrobertson.co.nz/_blank`, which returns
**HTTP 404**. This is a genuine authoring bug (a `target="_blank"` written into the `href`).
It is specific, verifiable by the owner in one click, and costs nothing to prove — exactly the
kind of evidence the Website Rescue offer is built on.

## Honesty corrections already applied

The first detector run scored this site **52 (HOT)** on a `NO_CONTACT_METHOD` critical defect.
Manual verification found the site **does** have a `contact.html` page. The claim was
technically true but commercially misleading, so the detector was changed to emit
`NO_CONTACT_ON_HOMEPAGE` (medium) and the score fell to an honest **31 (WARM)**.

> This is the standard: a defect that cannot survive the owner opening their own site in a
> browser is not a defect, it is a lie. Two further real bugs were fixed in the same pass
> (defect scores lost on unreachable sites; gzip/header handling causing 3 false "unreachable"
> results on sites that were actually fine).

## Sample size caveat

14 sites is a **methodology proof, not a campaign**. The candidate pool came from web search,
which surfaces businesses that already invest in visibility — these skew *better* than average.
The plan's daily target of 60–100 candidates needs the NZBN bulk-data route
(`nzbn.govt.nz/using-the-nzbn/nzbn-services/bulk-data/`) identified in the research file.

## Status

- Qualified prospects with provable defects: **9**
- Worth an approach (WARM+): **2**
- Contacted: **0**
- Outreach drafts written: **0** — deliberately not written, because the consent basis (APR-005)
  is unresolved and drafting a send-ready email invites an unlawful send.
