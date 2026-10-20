# Saved audit comparisons and history

Prepared candidate; not promoted. After explicit approval, 116 focused comparison/
history checks passed, including three repeated CLI path checks. Tests used
synthetic reports and mocked audit/browser/PDF services, with connection/process
guards and SQLite restricted to the isolated test directory. No live audit,
production change, history migration, provider request or soak restart occurred.

## One canonical implementation

`auditor_toolkit.comparison` consumes canonical reports. A new `compare` command
selects existing JSON files; the existing `audit --competitor` command also
produces a shared JSON/HTML table after its usual explicit target audits.

Proposed routes, not executed commands:

```text
./mm toolkit compare target/report.json --against other/report.json --output-dir comparison-output
./mm toolkit audit https://target.example --competitor https://comparison.example
```

The saved-file command makes no HTTP/DNS/provider requests and opens no history
database. Files and output remain within the current workspace. It requires
2–100 distinct reports, caps each file at 10 MB and the set at 20 MB, and requires
a new output directory outside the input report directories. Existing report
files and manifests remain immutable. No published output or outreach occurs.

Input URL/profile/status/coverage/run IDs and timestamps are visible. JSON binds
the canonical observation fields by SHA256. This is not a raw file hash or an
independent verification of a supplied report's truth.

The table retains finding counts and per-site differences, plus the comparison
mean and its difference from the target. The aggregate is held unless every
selected comparison is eligible; held observations are never silently excluded.

## Score differences

Numeric health differences require complete audits, finite 0–100 health,
timezone-aware timestamps, complete required checks, no errored checks,
consistent coverage, a scoring method/weight record, matching check scope and
versions, matching schema/profile, and a matching measurement contract.

New pipeline reports record measurement options and the digest of toolkit Python
source plus the bundled axe asset. This deliberately excludes brand, price,
output location and AI draft preferences. These do not affect deterministic
audit scope. Optional checker dependencies, local tools, browser installations,
hardware and network conditions are not proven identical by this source digest.
Every table retains this limit: a matching recorded basis permits a labelled
heuristic score difference, not a business ranking, revenue claim or controlled
performance experiment.

Missing provenance, partial runs and mismatches hold numeric differences. Older
reports stay visible with their recorded scores and explicit hold reasons; their
missing contract is not invented or backfilled. CLI exit 2 indicates a held
comparison even when individual reports say complete. Invalid inputs use the
existing argument-error path. Duplicated run IDs are rejected.

## Recorded history

History selection uses SQL equality for the exact requested URL and profile,
excludes the current run ID and newer rows, and returns at most 99 prior rows.
The current report supplies the hundredth observation. It does not combine
substrings, unrelated hosts, www/mobile variants, protocols, pages or profiles.
No canonical-domain equivalence or old JSON-history migration is asserted.

The SVG uses elapsed UTC time on its horizontal axis and reported health 0–100
on its vertical axis. Its JSON points retain run IDs, timestamps, profile,
coverage, observed health, comparison basis and hold reasons. Held rows appear
as crosses and break line segments. Missing/invalid timestamps cannot be placed
on the axis but remain in the point data. One eligible point does not establish
change over time. On a partial current run, the latest eligible historical basis
may show earlier comparable observations; the current run remains held.

The chart appears in HTML/PDF after final check coverage is known. If the last
PDF export fails, the report/chart are regenerated as partial and current health
is unavailable. Final trend, HTML and PDF files use the existing artifact
manifest mechanism. Earlier files/rows are not rewritten.

Starting/current health and change are retained in the trend summary. Aggregate
change requires at least two observations and an entirely comparable series;
unknown or mismatched intervals do not receive an invented improvement number.

## Finding labels and recorded verification

The same measurement basis now gates new/persistent/regressed/resolved findings.
Only complete, strictly earlier reports with the exact URL/profile and matching
source, scope, scoring and check rules participate. A missing baseline, partial
current run or malformed/duplicated finding inventory holds all historical
labels. Current observations remain visible without claiming novelty or repair.
Older incomparable runs cannot create a regression label.

SQLite selection compares normalized UTC instants at microsecond precision;
it does not order offset-bearing timestamps as raw strings. Chart selection
retains unplaced/invalid timestamps as held observations within its 99-row bound.
Finding comparisons are bounded to 1,000 eligible-query candidates. No existing
timestamp, report, finding state or event was migrated or rewritten.

An explicit `verified` transition requires a complete matching earlier detection
and a complete verification run without that finding. Saved metadata binds the
detection run and measurement-basis digest. Authoritative identity/state values
override metadata hints, so the event cannot contradict the actual transition.
These transitions were exercised only in synthetic test databases. They do not
authorize a real transition or establish who performed a customer fix.

The pipeline refreshes finding and fault labels after final coverage. A final
PDF failure holds both again, preventing earlier provisional resolution labels
from surviving in a partial saved report.

The previous 89-case receipt/source snapshot remains preserved separately.
The additional 27 cases include positive classifications, incompatible/future/
self/profile history, malformed inventories, recorded verification, timezone
precision and final-PDF failure handling. Monthly report comparisons and older
recorded verification events need separate review; this does not claim all
downstream historical assertions have been accepted.

## Focused scope and remaining validation

The user approved: "Yes, test comparison/history and repeat CLI checks".
The new presentation module plus the selected existing CLI checks pass 116 cases.
The test and source hashes, guards, final JUnit and earlier attempts are saved
in the presentation regression receipt. This covers the cases below; it is not
a full repository regression or whole-CLI/library compatibility acceptance.

- Complete matching reports: score difference, canonical observations, table escaping.
- Partial/error/skipped-required checks; malformed/boolean/NaN/infinite health;
  inconsistent coverage, missing contract and mismatch across each basis field.
- Distinct URLs with the same domain substring; exact profile/URL selection;
  exclusion of newer rows/current run; bounded query and deterministic order.
- Out-of-order/duplicate/conflicting IDs; UTC offsets, invalid/naive timestamps;
  held middle observations, partial current, one/no eligible plotted observations.
- SVG/HTML hostile strings, no external resources or injected links.
- Saved CLI limits, malformed JSON, path escape, overwrite refusal, no network/DB;
  original commands remain usable; competitor validation before network work.
- Final PDF failure, report manifest integrity and immutable prior history.
- Three relevant prior CLI path checks passed again. The CLI source changed
  after the historical 92-test run; that entire suite was not repeated and its
  old receipt is not current whole-CLI acceptance.

The tests reproduced and fixed malformed boolean/negative scoring and scope
metadata and invalid/credential-bearing URLs. Large integers and future history
were also hardened and covered. Real browser/PDF appearance, other consolidation
groups, full regressions and source promotion still need acceptance.

Source preparation does not complete P2, full library parity, the full regression
gate, release promotion or the required 24-hour soak acceptance.
