# Shared static UX candidate

Prepared source in the isolated worktree only. No candidate checker, audit or
regression test was executed. The frozen V44/V45 source and live soak are intact.

## Changes

The legacy plugin flagged any checked checkbox and searched all page text for
four decline phrases, without source-linked findings. The old canonical page
check had a narrower marketing rule but treated selected negative radio options
and ambiguous field names as marketing defaults.

One shared ux_static checker now serves the canonical page compatibility API,
the canonical audit pipeline and the legacy plugin. Existing two-argument page
calls still include UX results. The pipeline excludes that compatibility path
and performs one dedicated required ux check with its own version-2 registry
entry and evidence, rather than calculating/deducting the same findings twice.
The pipeline's existing conversion/contact/booking observations remain in this
same record with their original top-level data keys; static choice evidence is
added under static_choice_observations. A single required composite call keeps
later conversion processing from overwriting choice evidence or failure status.
Fetch failure explicitly skips that required check; source/coverage errors leave
the report incomplete. No other page rule is removed.

Static records cover checkbox/radio attributes, common label associations,
label/ARIA hints, nearest fieldset legend, declared negative/affirmative option
hints, static source XPath and the exact supplied HTML hash. Label text is
bounded with its full hash. Arbitrary option values are not copied into evidence.

The statuses distinguish:

- Unchecked markup and ordinary checked preferences without marketing cues.
- Checked marketing markup requiring human review.
- Negative/opt-out hints and selected radio options with unresolved polarity.
- Duplicate/unresolved label IDs and ambiguous nested label controls.
- Disabled/hidden/inactive declarations and unresolved disabled-fieldset context.

Marketing cue detection uses word/camel-case normalization, newsletter/marketing/
promotional wording, or subscribe with email/news/updates/offers context. A promo
code, terms choice, selected opt-out or subscribe label alone is not silently
declared marketing consent. Browser/server meaning remains unverified even when
static hints are strong. The existing consent_prechecked key is retained with
explicit heuristic confidence and HUMAN_REVIEW remediation.

The four old decline phrases are retained as review heuristics on buttons,
links, button inputs and role-button controls. Page prose, comments, script/style
and inactive text no longer trigger the plugin's global claim. The new
confirmshaming_review finding contains a source locator, matched phrase,
captured copy/hash and editorial review action; it is low severity and heuristic.
Rendered visibility, interaction intent and legal compliance are unmeasured.

The plugin keeps its callable name and issue-list/type/description format,
adding full evidence-based finding records and explicit limitations. Severity,
finding count and scope intentionally differ from the old blanket High labels;
consumer/regression acceptance is pending. The advanced entrypoint passes the
final fetched URL but its DNS/fetch path is still legacy.

Original checks.py, pipeline.py and the UX plugin are preserved as byte-exact
baseline text archives. Input limits are 8,388,608 HTML characters for standalone
analysis and 5,000 unique input/button/link/role-button controls. Exceeding a
limit causes explicit failure rather than successful dropped coverage.

## Standards and remaining interpretation

The [HTML label rules](https://html.spec.whatwg.org/multipage/forms.html#the-label-element)
associate explicit labels through IDs or nested controls. Duplicate IDs and
ambiguous label structures are held for review rather than treated as proof.

The [checked attribute](https://html.spec.whatwg.org/multipage/input.html#attr-input-checked)
describes default checkedness. Actual checkedness can differ after interaction
or script execution. This implementation reports markup and does not pretend to
inspect a live consent transaction.

ARIA handling is a limited hint, not a complete accessible-name implementation.
Hidden descendants are excluded from ordinary control copy; explicitly
referenced ARIA label text may contribute a naming hint. CSS visibility, custom
form controls, first-legend fieldset exceptions and server semantics need actual
browser review. This static work does not establish legal compliance.

## Required acceptance before promotion

- Existing page/evidence/privacy/pipeline/report/remediation suites.
- Ordinary terms/preferences, positive checkbox cues, negative labels/values,
  selected positive/negative/ambiguous radio options and duplicate IDs.
- Explicit/nested labels, ARIA hints, fieldset legends, mixed-case/camel-case
  attribute cues and malformed/unresolved label structures.
- All four decline phrases on controls, ordinary prose/comments, hidden/script/
  template/noscript descendants and role-button source-ordinal mapping.
- Stable hashes and bounded text; no arbitrary form value copied to evidence.
- A dedicated canonical ux evidence_ref with one finding/deduction per source;
  preserved conversion keys, no record overwrite/duplicate page execution,
  and required check failures/skips.
- Preserved direct page API defaults, circular-import boundaries and legacy
  plugin list semantics/intentional severity changes.
- Coverage limits, no network/provider/subprocess call, unknown browser state
  and no legal or consent-behaviour claims.

Earlier 92 approved identity/contact/metadata/demo passes are historical and do
not cover these source changes. Expanded regression authorization, synthetic
runtime checks, independent interpretation review and source promotion remain
pending. P2/P5 acceptance is incomplete.
