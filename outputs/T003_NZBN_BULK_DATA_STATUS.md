# T-003: NZBN Bulk Data Pull — Status

**Task ID:** T-003  
**Engine:** Website Rescue Lead Engine  
**Status:** BLOCKED — Pending NZBN bulk data access approval

---

## Blocker

NZBN bulk data requires **prior approved access** from Companies Office:
- Apply at: https://www.companiesoffice.govt.nz/data-services/ways-to-get-our-data/bulk-data/
- Files delivered via Box.com shared folder (link after approval)
- No programmatic API available without subscription key approval

NZBN API (portal.api.business.govt.nz/api/nzbn/v5/) also requires subscription key + OAuth2 approval for entity searches.

---

## Script Ready

`scripts/consume_nzbn_bulk.py` is written and ready to run once access is approved.

**What it does:**
1. Reads 19 CSV files from Companies Office bulk data zip
2. Filters to Canterbury postcodes (7xxx, 8xxx)
3. Joins core data + websites + addresses + trading names + industry codes
4. Outputs ranked prospect list: `outputs/T003_NZBN_CANTERBURY_PROSPECTS.csv`

**Usage:**
```bash
python3 money-machine/consume_nzbn_bulk.py \
  --zip /path/to/companies-office-bulk-data.zip \
  --output outputs/T003_NZBN_CANTERBURY_PROSPECTS.csv
```

---

## Recommended Alternative Path (while awaiting approval)

Since NZBN bulk access requires approval, the immediate next step is to **run the T-001 detection methodology on existing known prospects** rather than waiting for bulk data:

### Existing prospect sources in repo:
1. `outreach/prospect_candidates.csv` — 9 NZ businesses with detected defects
2. `outreach/prospects_batch_001.json` — 172 structured prospect records with consent evidence fields
3. `outreach/new-catalyx/prospect-list.json` + `prospect-list-batch2.json` — CATALYX flooring prospects
4. `prospects/` directory — existing research packets (trident-electric, heat-force, blizzard-hvac)

### Alternative data sources (no approval needed):
- **Business Canterbury member directory** (businesscanterbury.co.nz/member-directory) — browsable, Christchurch-focused
- **Google Maps UI** — manual verification of known businesses
- **Direct NZBN entity lookup** — single-entity API (no bulk, but usable per-entity)

---

## Action Required

**Dion:** Apply for NZBN bulk data access at the Companies Office website. Once approved, run:
```bash
python3 money-machine/consume_nzbn_bulk.py --zip ~/Downloads/companies-office-bulk-data.zip
```

**Meanwhile:** Run detection stack on existing prospect_candidates.csv (9 records) to score and tier them.
