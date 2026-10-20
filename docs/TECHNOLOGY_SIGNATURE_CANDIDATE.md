# Shared passive technology detector candidate

Prepared source only in the isolated candidate. No detector was imported/run,
no regression tests were added/run, and no live checkout/service was changed.

## Consolidation

Four previously independent implementations now delegate to one passive
signature interpreter in technology/observations.py:

- The canonical auditor_toolkit.tech list/evidence API.
- The typed technology.fingerprints API used by enrichment.
- plugins.tech_stack_detector's legacy name list.
- website_auditor.advanced.tech_fingerprint's builder/cache/CDN groups.

The signature catalog has 118 rules, statically extracted from the baseline
typed and extension tables plus explicit canonical/plugin DOM/header rules.
The four original implementations are preserved byte-exactly as text archives.
Their hashes and frozen revision are included in the preservation receipt.

The shared interpreter collects all matched technology/category clues from
supplied HTML, selected DOM attributes and case-insensitive response headers.
Each clue has its input location/hash, rule origin/pattern, matched text and
source URL when supplied. The advanced launcher passes its final fetched URL.
No whole cookie/header is copied merely because a technology token matched.
Matches against the combined header context withhold their raw values; scoped
header rules retain only a matched token or a nonempty-header presence marker.

The canonical report retains all matches. Compatibility adapters retain old
callable names, typed records and output containers. Vue.js, nginx and AWS
CloudFront spellings are translated for their respective legacy views. Typed
singleton slots use the old category ordering; framework slots use the highest
signature weight with deterministic legacy tie ordering. Other matches remain
in canonical evidence, rather than being silently discarded by singleton slots.

## Interpretation and limits

These are passive clues, including broad historical substring rules that can
match prose, comments or inactive code. A match is not confirmed installation,
an exploitable component, a measured security risk or an installed version.
Technology observations produce no audit defect deductions. The technology
registry advances to version 2 and declares this scope.

Numeric signature weights are explicitly uncalibrated and are not probabilities.
WordPress's numeric generator token remains available through the established
version field, with its legacy 0.9 extraction weight. It is labelled unverified;
conflicting declared tokens produce no selected version. This code neither
looks up current versions nor runs the separate vulnerability/advisory path.

Limits are 8,388,608 HTML characters, 10,000 generator/script-src/link-href
contexts and 20,000 linked signal records. Exceeding a limit is an error, not
successful partial coverage. This makes a required canonical technology check
incomplete. Evidence hashing is cached per input within one call.

The canonical list can include more technology clues than its old nine-detector
implementation, while the old plugin's unordered set becomes a deterministic
name list. Numeric confidence and evidence text can change. Internal private
helpers/constants removed from old implementations have no discovered in-repo
callers; unknown external/dynamic imports still require migration acceptance.
The typed enrichment's existing version/advisory logic remains separate and
requires its own evidence-quality acceptance. Full P2 closure is not proven.

## Regression evidence required before promotion

- Existing technology fingerprint/pipeline/report/schema/version/advisory suites.
- All fourteen unique technology names in the old plugin's rule branches,
  original canonical categories/features and old extension builder/cache/CDN rules.
- Upper/lowercase headers and DOM attributes, missing values, duplicate header
  case variants, multiple CMS/framework/server matches and adapter ordering.
- Stable name aliases, singleton selection and all-match canonical evidence.
- WordPress version extraction, absent/empty generators, conflicting version
  tokens and explicit unverified/calibration metadata.
- False-positive review for visible prose/comments/inactive scripts, with no
  material findings, installed-version or vulnerability claims.
- Complete input hashes, bounded matched clues and no copying unrelated cookie
  values; declared coverage limits fail explicitly.
- No network/subprocess/provider calls or hidden optional model dependencies.
- Current and unknown downstream consumer/import compatibility.

The earlier 92 approved identity/contact/metadata/demo passes do not cover this
new shared detector. Expanded regression authorization/evidence and full
candidate regression are pending; nothing has been promoted.
