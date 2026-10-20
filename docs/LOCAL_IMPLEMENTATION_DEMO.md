# Local implemented demo workflow

`wa implementation-demo SOURCE PATCH_PLAN --output-dir NEW_OUTPUT [--entrypoint index.html]`

All supplied paths must remain in the caller's workspace. Source and output must be separate; output must be new. Input sites are bounded to 200 supported static files and 20 MB. No source file is edited. Patch schema 1 contains edits with path, expected_sha256, and literal replacements (old/new/expected_count). Hash and occurrence mismatches fail before output is created. Scripts/handlers, active frames, refresh, hidden paths and source symlinks are unsupported.

The command copies before/after trees, applies the supplied reviewed patch only to after, audits both at the same loopback URL and rendered profile, preserves report/screenshot hashes, and closes its owned HTTP server. No site script, model invocation, price, form submission or outreach is performed.

A complete paired audit at the same URL/profile/coverage with removed findings or reduced severity, and no new or worsened findings, is labelled LOCAL_IMPROVEMENT_OBSERVED. This is a lab comparison of a static local copy. Six remaining findings or a green local comparison never establish live-site correction, accessibility conformance or revenue improvement. New/incomplete comparisons remain REVIEW_REQUIRED.

Candidate regression validation and human promotion review remain required. Do not change frozen source/config during an active soak.
