# Deliverables 1–2: revenue scenarios and monthly client reporting

Implemented in the existing toolkit, with compatibility entrypoints for the earlier scripts. The default delivery mode is **draft-only**. No SMTP connection, email sending, remote publishing or scheduler activation occurs, even if credentials exist.

## 1. Revenue Calculator

**Business value:** explain the assumptions behind a proposed investment, prioritize work and avoid undermining credibility with unsupported revenue claims.

**Client sentence:** “We can show what these issues could cost under your agreed business assumptions, what the fixes could cost, and what we need to measure to validate the benefit.”

The calculator accepts exact `defect_key` values from a versioned audit report. Each quantified effect requires a low/high range, source, rationale and reviewer. There are no built-in “industry average” losses, default 2.5% conversion rates, arbitrary 60% caps or assumed $120 hourly charges. Missing input is **not quantified**, not zero loss. An expiring TLS certificate is not treated as an already expired certificate or a current browser warning.

Formula:

```
Baseline monthly value = visitors × baseline conversion rate × value per conversion
Modeled monthly risk = baseline value × disjoint audience share × relative conversion loss
Potential recovery = modeled risk × recovery fraction
Contribution benefit = potential recovery × contribution margin
Profit ROI (%) = (contribution benefit × horizon months − fix cost) ÷ fix cost × 100
Payback months = fix cost ÷ monthly contribution benefit
```

Baseline conversion means the assumed rate **without** the modeled defect. For lead generation, value per conversion is expected value per lead, not average sale value unless a conversion means a sale. The fixture example is hypothetical: 2,000 × 5% × NZD 150 × 18% = NZD 2,700/month at risk. It is not evidence that a missing title causes an 18% loss.

Repeated instances of a defect share one modeled fix bundle. Effects within the same traffic segment overlap and are combined by taking the maximum, not summing. Disjoint segment shares must add to at most 100%. Estimated work is per defect type across all occurrences; split scopes explicitly when that assumption does not fit. Total fix costs cover quantified items only. Unknown effects remain listed separately. Zero rates/traffic are honored, and division by zero yields unavailable ROI/payback.

**Inputs/outputs:** `calculate_revenue(report, scenario)` returns `revenue_scenario` schema 1 with decimal-string currency amounts, evidence IDs, baseline, low/high ranges, assumptions, unknown items, and coverage. The CSV contains per-type comparisons, not additive loss totals. CSV formula prefixes are escaped.

**Action Engine:** financial output never grants approval or changes remediation state. Evidence IDs remain available for local fix previews. Cost assumptions are operator inputs rather than inferred implementation facts.

## 2. Monthly client reporting

**Business value:** show verified work and next priorities each month, supporting retainer conversations with an auditable record.

**Client sentence:** “Every month you get a branded report showing what we verified, how your site changed, and the next work we recommend.”

A single YAML config holds branding, a local PNG/JPEG logo, contact details, client URLs, profiles and scenario inputs. Logo bytes are embedded locally. The PDF contains an executive summary, health trend, scenario amounts, ROI assumptions, verified work, next-month recommendations and compliance-review observations. It makes no legal or WCAG conformance determination.

Reports select the exact client URL/profile and calendar month in `Pacific/Auckland` by default. The prior month uses the same profile. A later partial audit is shown as partial; an older complete result is not silently substituted. No audit means unknown status. Verified work requires a recorded remediation verification event for the same client and a complete verification run; a disappearing finding alone is not billed as completed agency work.

Artifacts are immutable per generation: HTML, optional PDF, revenue JSON, ROI CSV, `email.eml`, action preview, report JSON and a hash manifest. SQLite registers monthly bundles separately from raw audit runs. Repeating identical successful input reuses an intact bundle. A failed PDF attempt retains HTML/email with a visible partial status, and a later retry can produce a new bundle. Email drafts attach the PDF when available or HTML otherwise. Open them in an email client for human review; the toolkit never sends them.

**Portal:** log in and open **Monthly report drafts**. Only registered artifact IDs can be downloaded; hash checks reject altered files, paths cannot escape their generation directory, and HTML is served as an attachment.

**Action Engine:** every build evaluates existing policy and respects a local `outputs/toolkit/monthly/CANCELLED` kill switch. It records a draft action and a history event. Approval never enables email transmission in this release.

**Nightly Watchdog:** `Watchdog.monthly_draft_jobs(config_path, output_root, now)` returns unsent draft jobs for the previous month on the 1st in the configured timezone. It does not execute them or modify the existing nightly workflow. `wa monthly --due-preview` exposes the same check. Scheduling and automatic delivery remain disabled, per the selected defaults.

## Install and run

Python 3.9+ compatibility is targeted for these modules and the canonical toolkit; Python 3.14 remains the local macOS runtime. Python 3.9 itself is end-of-life upstream; compatibility does not extend its security-support lifetime. Use a maintained Python release for deployment.

```sh
cd /Users/dd/WEBSITE-AUDITOR
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,browser,portal]'
.venv/bin/python -m playwright install chromium
cp toolkit_config/agency.example.yaml toolkit_config/agency.local.yaml
```

Edit `agency.local.yaml` with the actual client URL, profile, recipient and reviewed assumptions. The example deliberately leaves `impacts: {}` until reviewed. Do not put SMTP passwords in it. JSON configuration works without PyYAML. Missing Playwright produces HTML and an unsent email draft with an explicit PDF error; local AI and DuckDB are not required.

```sh
.venv/bin/wa audit https://example.com/ --profile static
# Replace the path with the JSON artifact from the selected client's audit.
.venv/bin/wa revenue outputs/toolkit/RUN_ID/report.json \
  --config toolkit_config/agency.local.yaml --client example

# Generate last month's report, with PDF when available.
.venv/bin/wa monthly --config toolkit_config/agency.local.yaml --client example
# Or choose a month and generate drafts for all configured clients.
.venv/bin/wa monthly --config toolkit_config/agency.local.yaml --all --month 2026-08
# Explicit fallback and due-job inspection:
.venv/bin/wa monthly --config toolkit_config/agency.local.yaml --client example --html-only
.venv/bin/wa monthly --config toolkit_config/agency.local.yaml --due-preview

.venv/bin/wa dashboard --set-password
.venv/bin/wa dashboard
```

`revenue_report.py` and `monthly_report.py` accept the same arguments as their corresponding `wa` subcommands. Earlier guessed-domain/default-input and `--email` behaviors are deliberately retired. Old builders (`make_revenue_calc.py`, `make_monthly_reporting.py`, etc.) are historical sources and should not be replayed: they can overwrite the repaired modules.

Exit code 0 means a scenario/report was produced in the requested mode; 2 means missing inputs, no current audit, a partial PDF/report, blocked policy or invalid input. A scenario is always labeled hypothetical even on exit 0. Generated artifacts under `outputs/` are excluded from source control.

The `deliverables/` folder contains readable Python file generators for both deliverables. Default invocation checks the existing files. `--write` creates missing files; `--replace` is required to overwrite a differing source file. They never install packages, activate schedules, or send email. Run them only against the current toolkit baseline.

## Verification

```sh
.venv/bin/python -m pytest toolkit_tests/test_agency_revenue_monthly.py -q
WA_BROWSER_E2E=1 .venv/bin/python -m pytest toolkit_tests/test_monthly_browser_e2e.py -q
```

The browser test uses local synthetic data, generates a real PDF, signs into the portal, downloads the PDF and email draft, logs out and verifies access rejection. The Python CI matrix covers 3.9, 3.11 and 3.14; live local-model generation remains a separate acceptance item.

Deliverables 3–12 remain the next requested tranche: prospect scoring/outreach drafts, onboarding, competitor comparison, churn indicators, deployment/tenancy, performance benchmarks, jurisdictional review register, AI sales drafts, portfolio views, and the monetization playbook. Public deployment, sending, payments and unsupported financial/legal claims are not enabled by these first two deliverables.
