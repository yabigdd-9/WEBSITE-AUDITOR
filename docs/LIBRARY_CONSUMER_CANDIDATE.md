# Markdown and explicit legacy scoring

Source candidate only. These consumers have not been imported, executed,
regression tested or promoted. Broader regression approval is pending.

## Readable canonical Markdown

The compatibility `--format md` route now delegates to
`auditor_toolkit.markdown.render_markdown_report`. It presents the same canonical
audit; it does not run a second engine or recalculate health.

The output separates reported health from defect severity and includes findings,
evidence references, confidence, proposed remediation/review requirements,
checker coverage, score deductions, historical summary and recorded artifact
references. There are no invented hot/warm sales tiers or copied revenue claims.
Incomplete health is unavailable. Empty findings do not establish a clean site
when coverage is incomplete.

The renderer requires a consistent canonical report/finding inventory. Untrusted
text is flattened, HTML escaped and Markdown punctuation escaped rather than
placed inside raw HTML or fixed-length code fences. Artifact paths are displayed
as references; this is not a fresh integrity check. Full Markdown rendering and
hostile-input regressions remain unverified.

The filename-import API of the archived enhanced engine is not restored. The
existing compatibility command format is improved through the shared engine.

## Two named legacy formulas

`legacy-message-weights-v2` retains the original root formula.
`legacy-enhanced-message-weights-v4` retains the enhanced keyword/branch table,
including its differing CTA, viewport, trust and markup weights. The pure
compatibility API accepts an explicit method; unknown methods are rejected.
Its existing default names the root v2 formula for API compatibility. These
message-weight formulas remain historical arithmetic, not canonical health or
calibrated prospect quality.

Enrichment requires the legacy report to declare `legacy_score_method` as one
of those two names before changing its findings/count/score. It does not infer
a formula from defect text, current score or old filename. Missing/unknown
methods hold scoring and preserve the original base fields; header-grading
observations remain in the enrichment block for review.

Known-method recomputation is prepared on a copied finding list, with repeated
header observations deduplicated. Base fields are updated together only after
successful calculation. Canonical reports remain advisory-only. This addresses
the earlier mutation of findings while retaining a stale score on failure.

## Proposed regression scope

No tests were added or run for these changes. Developer instructions require
explicit additional approval; the existing broader request covers remaining
auditor consumers and full isolated regressions.

- Canonical complete/partial Markdown, empty/invalid/duplicate inventories,
  checker/evidence references, effort/review actions, financial caveats and
  unchanged recorded score values.
- HTML/Markdown headings, lists, fences, tables, links and hostile nested evidence;
  no active markup or invented source references.
- Repeat compatibility CLI output paths and return codes with a mocked audit;
  no website/provider request, live history or overwrite of audit artifacts.
- Each archived scoring branch, precedence, fallthrough, numeric markup weights
  and cap for both named formulas; differential valid-input comparison with
  preserved formulas, plus invalid input/method rejection.
- Unknown-method enrichment preserves base fields and shares no mutated list;
  known methods update copied findings/count/score together, deduplicate repeated
  observations and preserve canonical scores.

Static compilation/full file Ruff are source checks only. The historical 116
presentation cases do not exercise these consumers. HEAD API and custom-404
usability parity remain separate gaps; no additional network probe was enabled.
