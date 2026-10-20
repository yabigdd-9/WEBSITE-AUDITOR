# Rollback plan

This is an uncommitted local candidate based on 1695615263d3e10eaa4e94a98588dcca5d6eaae9. No live runtime or database was changed, so operational rollback is unnecessary.

Keep the source patch and reports for review. If rejected, archive only this attached managed worktree using the app worktree archive operation after confirming no needed ignored artifacts are lost. Do not reset or clean the primary or any other worktree. Do not undo Hermes staged changes.

If later integration is approved, apply narrowly to the agreed revision, preserve a backup, re-run tests against combined changes and keep approval/send disabled. Roll back that reviewed patch in its isolated branch if lease-expiry handling or health schema consumers regress. No new DB columns/migration were introduced by these repairs. Never automatically replay external side effects or release held businesses to compensate for rollback.
