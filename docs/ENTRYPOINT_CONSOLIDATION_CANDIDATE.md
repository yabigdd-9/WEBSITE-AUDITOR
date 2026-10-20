# Audit entrypoint consolidation candidate

Prepared source only. No candidate entrypoint or enrichment/scoring code was
executed, no regression tests were added/run, and no live source was changed.

## Current source findings

Both root website_auditor scripts already have an early main guard that calls
auditor_toolkit.compat.legacy_main before the old implementation. Their current
command-line runs therefore use the canonical pipeline.

Importing those files explicitly by filename instead loads the duplicate old
engine, imports optional dependencies and creates outputs/.cache immediately.
Ordinary import website_auditor resolves the separate extension package. The
tier1 enrichment adapter nevertheless calls wa.score_defects on that package,
whose initializer is empty, and silently catches the missing attribute.

Source inventory found:

- 16 imports of extension-package submodules used for reporting, connectors,
  monitoring and policy; that package remains in place.
- One bare package import expecting the absent legacy scorer, now corrected
  in this candidate.
- Filename subprocess callers in watchdog, competitor comparison and the
  DeepSeek bridge; the same script names and CLI translator remain available.
- The old wa.py workflow references seventeen scripts; eleven are absent at
  the frozen baseline. It previously returned success despite these skips,
  module failures, unsupported commands and failed/missing file viewers.
- All seventeen workflow steps and four advanced plugins now have a static,
  source-bound feature map. This candidate does not claim feature parity or
  that all P2 routes are consolidated.

## Proposed changes

1. Replace the two root script bodies with lazy thin wrappers around the existing
   canonical compatibility CLI. Argument interpretation and audit execution are
   delegated to the same legacy_main as before.
2. Preserve byte-exact baseline copies as non-executable .txt archives, with
   source hashes and baseline revision in a preservation receipt.
3. Move the valid old defect-message scoring arithmetic into an explicitly named
   toolkit compatibility module. No page fetch, optional dependency import or
   cache creation is needed to use that arithmetic.
4. Replace enrichment's missing package attribute call with the explicit legacy
   scorer; include UPDATED/HELD status and the legacy method identifier.
5. Avoid appending duplicate identical header grading on repeated legacy
   enrichment. Preserve the old score with a visible HELD status when unsupported
   legacy input prevents rescoring.
6. Treat canonical evidence-based reports as advisory enrichment only: preserve
   their finding list, counts and all score fields. A future pipeline adapter
   must provide evidence linkage before incorporating enrichment findings.
7. Record source exceptions as skipped rather than implying a score update.
8. Add an explicit wa.py toolkit <args> route to the canonical CLI, forwarding
   its arguments and return status. Keep the legacy run workflow distinct.
9. Return status 1 when any legacy workflow module fails, times out or skips,
   and status 2 for unknown commands, unsupported extra arguments or an
   ambiguous run without an explicit domain/--all. The 17-module workflow
   therefore cannot pass while referenced modules are absent.
10. Resolve legacy scripts and outputs relative to the checkout containing
    wa.py, and run children in that checkout. Preserve the child's SSL defaults
    without changing the importing process's environment.
11. Label the old status command as saved-output inventory. File/folder
    existence provides no runtime health, freshness or acceptance evidence.
    Return nonzero for a missing command-center file or failed viewer.

The old formula's W3C/markup branch may produce fractional values; compatibility
does not silently round them. This score is not a current health score,
opportunity index, commercial confidence, compliance finding or quote approval.

## Compatibility and feature limits

The root scripts no longer expose their former library-only functions when
explicitly imported by filename. Current library callers must use
auditor_toolkit.pipeline.run_audit and its report contract. Unknown external or
dynamic filename imports remain a compatibility acceptance risk.

The old script help mentioned batch/crawl/scout/competitor options that the
existing early CLI guard already rejects. This candidate does not silently
claim to restore them. Useful old features must be mapped and accepted before
the entire consolidation phase can close.

The wa.py workflow remains a legacy fanout path, now with truthful status and an
explicit canonical command route. It has not been replaced by a single audit.
Its historical reports and fourteen non-audit workflow steps cannot silently
be declared equivalent to canonical commands. Eleven referenced scripts are
absent; this preparation neither restores nor runs them.

The advanced entrypoint is now a lazy canonical wrapper with an exact baseline archive.
The new canonical orchestration uses the existing bounded fetcher, calls each
shared feature implementation once, preserves per-check evidence/status and
returns nonzero for incomplete coverage. A toolkit namespace on the operator
launcher selects the canonical CLI and this advanced command. See
ADVANCED_COMMAND_CANDIDATE.md; command/consumer parity is not yet tested.
The technology candidate now consolidates four implementations behind a shared
passive interpreter/catalog and compatible output adapters. Exact regression
and consumer acceptance remain pending; see TECHNOLOGY_SIGNATURE_CANDIDATE.md.
The static UX candidate now shares a dedicated canonical check with the page
compatibility API and legacy plugin. Checked ordinary/negative choices and
unresolved labels are distinguished from marketing review flags; decline copy
is a control-scoped heuristic. See STATIC_UX_CANDIDATE.md for unaccepted scope.
The bounded optional SPF/DMARC adapter is prepared but uninstalled/untested;
see EMAIL_AUTH_CANDIDATE.md. Rendered image optimization remains unaccepted.
The frozen images.py is a TODO; the candidate now implements static markup
evidence with a shared plugin adapter, as documented in IMAGE_MARKUP_CANDIDATE.md.
Rendered image optimization/performance remains unmeasured. DNS errors cannot become failed security checks, all
checked boxes cannot be assumed marketing consent, and blanket lazy-loading
advice must exclude critical hero images. The feature map records these gaps.
Historical generators and old companion reports still need parity decisions.
Source archives preserve review material; they are not a new runnable engine.

## Required regression evidence

Before promotion, use mocked audits and enrichment sources:

- Wrapper import creates no cache, network request or subprocess; filename
  entrypoint delegates arguments/return codes to the same compatibility API.
- Existing supported URL/format/output/browser/private/TLS arguments, errors
  and incomplete-report exit status remain equivalent.
- Every legacy score branch, fractional markup arithmetic, cap, malformed
  record handling and comparison with the archived source's valid formula.
- Legacy enrichment rescoring, repeat-call deduplication and explicit held
  status on malformed input or source failure.
- Canonical report findings, counts, breakdown, severity, health and categories
  remain unchanged after advisory enrichment.
- Existing tier1 offline and toolkit/compatibility regression suites.
- Extension package users and filename subprocess callers retain their intended
  contracts; further independent entrypoint acceptance is still required.
- wa.py canonical forwarding, legacy module result aggregation (success,
  skip, failure and timeout), missing modules, argument errors and return codes.
- wa.py import leaves environment unchanged; children use the script checkout
  as cwd, inherit explicit SSL settings and otherwise preserve legacy defaults.
- Old output inventory does not claim health; missing/failed/unsupported viewer
  returns failure and no shell interpolation is used.

The master plan requires regression evidence before source promotion. None
of these additional consolidation tests has been authorised or run yet.
