# Controlled integration proposal — not executed

Candidate source 923c14e5a35f69889875cc41c93539678baf44d7; shared base e68873c509431f7132c754e2aeaee99fc9eb858e is its ancestor. No cherry-picks are needed. Five existing commits are already sequential descendants; replaying them separately would duplicate history unnecessarily.

1. Integrator reviews immutable candidate and full exact-source replay receipts. No activation approval follows from a green suite.
2. Recheck shared branch/HEAD, job unloaded, dirty path list and private recovery manifest. Make and verify a new private preservation snapshot of all seven modified plus 241 untracked files, retaining existing archives. Do not publish approval/customer content.
3. Resolve only the two reviewed application overlaps with explicit integrator authorization. Registry shared bytes equal candidate. Adapter differs solely by two narrow E402 comments. After reviewing both sides and verifying recovery, adopt candidate equivalents for these two paths; leave all other dirty paths untouched. Do not stash/clean/reset the shared checkout or commit approval/generated state.
4. Fast-forward shared branch to the accepted candidate only after safely handling those exact overlaps. Git may refuse the dirty overlap; do not force it. No merge commit or duplicate cherry-picks.
5. Verify all five other modified paths and all untracked contents against preservation hashes, review source diff, and replay impacted tests with isolated fixtures. Keep supervisor unloaded. Record exact integrated SHA and preservation proof.

This document is a proposal only: no shared-file manipulation, integration, service control or live DB operation has been performed. Current adoption assignment explicitly excludes further shared integration. Integration-owner authorization is required before step 3.

Next module decision: complete A10 contract/design review for live scheduler identity and continuous drift observation; current opt-in bootstrap is startup-only. Existing two-file ownership does not grant modifications to scheduler, launchd or global provider settings. Global financial admission remains dependent on C10 entitlement evidence and assigned global call sites. No speculative upgrade or runtime acceptance is inferred from passing startup tests.
