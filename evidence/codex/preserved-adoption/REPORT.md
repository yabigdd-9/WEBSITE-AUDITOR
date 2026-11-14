# Preserved application fixes adopted on Codex branch

Application source: 0fe5047b18df40e603b8f0bea20cb16fe2c95fac.
Base: approved/integrated e68873c509431f7132c754e2aeaee99fc9eb858e.
Status: LOCAL_IMPLEMENTED_AND_VERIFIED; independent review required.

The integration owner explicitly assigned the two source files and their two
new test files. Exact assignment is appended to ../OWNERSHIP.md.

## Registry correction — e86b9f54

Adopts only the preserved removal of duplicate hygiene/links definitions.
Later duplicate entries had overwritten the useful limitation text with empty
defaults. All 27 registry IDs remain, with no change to evidence-required flags,
categories, modes or versions. Two behavioral regressions assert serialized
static-check definitions retain their evidence qualifications.

## Adapter import correction — 0fe5047b

Adopts only the preserved trusted sibling-path setup. This supports file-spec
and runpy entry points from an unrelated working directory when only the
repository root is explicitly available. Repeated execution does not duplicate
the path entry. Two narrow E402 annotations document intentional imports after
path bootstrap; no global lint settings changed. No adapter behavior, request
limits, DNS safeguards, SMTP restrictions or transport activation changed.

Tests use fresh isolated Python children, a foreign disposable cwd, scrubbed
credential variables and hard socket/DNS blockers. They import but do not
invoke live GET/DNS/SMTP behavior. Both entry-point cases assert the public
Crawler/DNSChecks definitions exist and the trusted path appears exactly once.

## Evidence

The four new assertions all fail against unchanged e68873c5 in a separate
disposable clone (baseline.xml/baseline-result.json). This is intentional
regression evidence, not an accepted failing gate. After adoption, focused
coverage is 131 passed plus 49 passing subtests. It includes registry, hygiene,
V44 analyzers, bounded contact-network adapters and synthetic email DB handling.
Final exact-source full-suite receipts follow below after completion.

The earlier two-overlay review is not misrepresented as a clean committed
full-suite result. Its hashes/import/registry observations are retained for
provenance; new final receipts govern this committed package.

## Preservation and remaining boundaries

No shared files were edited, staged, restored or discarded. All original
approval state, generated reports, untracked files and private recovery archive
remain separate. The shared branch remains e68873c5; Opus remains untouched.
The shared launchd supervisor remains unloaded and must not restart without
separate authorization. No paid route, provider call, external send, migration,
service activation, push or shared integration is part of this adoption.

These new commits require independent review. Future shared integration has
actual path overlap with the preserved dirty application files, unlike the
previous fast-forward. Preserve/archive/review both sides; do not auto-resolve,
stash/clean or overwrite them. Registry source matches its reviewed preserved
bytes; adapter source adds only narrow lint annotations beyond those bytes.
Approval YAML and generated outputs require their own owner disposition.

## Final frozen verification

- canonical: 1141 passed, 3 skipped, 2 warnings in 63.66s (0:01:03); receipt duration 64.328 seconds.
- money: 744 passed, 2 skipped, 83 subtests passed in 72.76s (0:01:12); receipt duration 73.908 seconds.

Both final receipts exit 0 with changed_during_run=[] and
loaded_mismatches=[]. Existing five skips remain limitations. No new skips
were added. Later evidence-only commit does not change the tested app source.
