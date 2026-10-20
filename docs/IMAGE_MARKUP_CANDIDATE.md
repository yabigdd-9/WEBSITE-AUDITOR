# Canonical image markup candidate

Prepared in the isolated worktree only. No audit, browser, asset request, provider
call or regression test was run. The live frozen source and soak remain intact.

## Implementation

The canonical pipeline already calls images.analyse_html as a required check,
but the frozen implementation returns no findings/evidence from a TODO body.
This candidate implements that path and advances its registry version to 2.
The old plugin becomes a compatibility adapter to this same canonical code.

For each active static img element, evidence records:

- Source ordinal and XPath in the static parse, with browser identity unverified.
- Declared src/srcset/sizes, loading/fetchpriority/decoding and width/height.
- Only preceding direct picture source siblings and their declared candidate,
  type, media, sizes and dimension attributes.
- Enum defaults, explicit positive img dimensions, nonempty responsive markup,
  and URL extension hints, with actual selected source/layout/MIME unmeasured.
- Supplied HTML hash; long attribute values are truncated with their full hash.

Findings are limited to empty picture source srcset (fallback may still work),
and lazy loading combined with high fetch priority (heuristic review). Both
carry source, selector, observed evidence, effort and HUMAN_REVIEW remediation.
The canonical scorer remains responsible for finding-linked deductions.

PNG/JPEG extensions, missing responsive markup or dimensions, and default eager
loading alone do not cause findings or generate optimization scores. No-img
input reports its limited scope rather than inventing a perfect performance
score. Template/noscript descendants are excluded with a visible count.

Limits are 8,388,608 HTML characters, 2,000 img elements and 2,000 picture source
elements. Exceeding a limit raises an error: the existing pipeline reports an
incomplete required check, rather than silently treating dropped coverage as OK.

## Compatibility

The plugin keeps its callable name and total_images for the legacy dashboard.
It returns method/version, evidence and finding records. The old score and
missing-lazy/responsive/legacy-format counters are explicitly retired in format
version 2; consumers need migration acceptance. No unknown consumer parity is
claimed. Exact baseline plugin text is archived before replacement.

advanced_audit.py remains a legacy entrypoint with other unmapped adapters. This
single shared check does not complete P2 or P4. The older dashboard also assumes
missing score means 100 and renders unescaped input; those independent gaps
must be resolved before accepting that presentation path.

## Standards and interpretation

The [HTML image specification](https://html.spec.whatwg.org/multipage/embedded-content.html#the-img-element)
defines picture alternatives and image attributes. Their presence alone does
not prove browser selection, valid candidates or measured performance.

The [HTML enum defaults](https://html.spec.whatwg.org/multipage/urls-and-fetching.html#lazy-loading-attributes)
are eager for unspecified/invalid loading and auto for unspecified/invalid
fetchpriority. Keyword matching is case insensitive and does not strip spaces.

Google's [image loading guidance](https://web.dev/articles/browser-level-image-lazy-loading)
recommends eager loading for images initially in view and lazy loading for
offscreen images. Static source cannot establish which role an image occupies.

## Required regression evidence before promotion

- Existing canonical pipeline and registry contracts with mocked network.
- Zero/ordinary images, nested layouts, picture siblings before/after img,
  source fallback, template/noscript exclusion and repeated source deduplication.
- Valid/missing/invalid/case/whitespace enum values and positive dimension hints.
- No penalty for PNG/JPEG, absent srcset/dimensions or eager/default loading.
- Explicit review evidence and score linkage for the two proposed finding rules.
- URLs with queries/fragments, data URLs, malformed URL hints and unknown MIME.
- Long attributes/full hashes; declared source limits fail required coverage.
- Stable JSON evidence, no fetch/subprocess, no browser performance/field claims.
- Plugin format migration and current/unknown downstream consumers.

Earlier 92 focused identity/contact/metadata/demo passes do not cover this new
checker, changed registry or plugin format. Additional test authorization is
pending; full candidate regression and promotion are unproven.
