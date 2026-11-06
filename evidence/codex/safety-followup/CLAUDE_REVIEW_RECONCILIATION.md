# Reconciliation of supplied Claude report

Claude's reported toolkit_tests-only run is a different test selection and
revision from the retained canonical receipts. Canonical replay is
`pytest toolkit_tests tests -q`; MoneyMachine replay is
`pytest money-machine -m "not slow" -q`. MoneyMachine test_acceptance.py alone
is not the 693-test suite. Older reports/v44-integration/2026-10-15/VERIFICATION.md
counts are historical, not contradictory results for the same pinned run.

Use the existing reviewed interpreter; do not install packages, run against
the live database, or infer acceptance from whichever dirty checkout has a DB.
The replay wrapper uses the reviewed synthetic schema/migration/guard fixture
and separates scratch directories by source revision. Exact application source
is pinned and parent-process loaded code is checked; child code/live runtime
are not certified by the parent-process probe.

The original candidate aac59f98 contained tested application source b032c8c1.
The subsequently authorized local upgrade batch is now tested separately at
c50fc9757d156fdce20a975f3ff0f04e98065af8; do not apply the old review as approval
for these new changes. Claude source fixes and search-DLQ work remain attributed
to Claude; canonical A10 startup identity is a distinct package.

Branch names are Git references, not directories. Exact owned paths are listed
in ../OWNERSHIP.md and commits.json. Codex writes only its assigned checkout;
Opus and the shared integration checkout are not destinations. Shared dirty
work remains preserved and requires owner disposition before integration.
