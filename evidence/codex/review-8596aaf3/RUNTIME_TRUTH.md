# Runtime truth correction — A10 incomplete

Read-only observation: 2026-10-17T06:19:03.718881+00:00 (UTC). Shared checkout ec86481c; local reader candidate 8596aaf3. No service-control action issued.

A shared supervisor was observed as PID 22805, cwd /Users/dd/WEBSITE-AUDITOR/money-machine, executable /Users/dd/WEBSITE-AUDITOR/.venv-email/bin/python. It matches the shared PID file and heartbeat and has a shared database handle. Its observed process start is 2026-10-17T13:55:09+13:00 (Pacific/Auckland). The command uses supervisor.cli _run-foreground without isolated bootstrap, and no startup receipt exists for this PID. Actual loaded revision/configuration remain UNKNOWN.

The launchd job gui/501/ai.website-auditor.supervisor is absent. These facts can coexist: an absent job is not proof of no process. Parent PID 1 is not proof that this particular launchd job owns the process; a detached process can be reparented. The initiator and authorization are unknown.

The observed start predates the recorded integration preservation snapshot 2026-10-17T01:55:37Z. Earlier completion reports proved the launchd job was absent but did not perform an exhaustive shared-process absence check. Their statements that the shared supervisor remained stopped were too strong and must not be used as activation or maintenance-window evidence. The integration's dirty-file preservation checks remain distinct and do not attest running code.

Affected shared integration/runtime activation is held for owner coordination. User has been asked whether this runtime was intentionally started by the user or Claude. No process termination/restart is inferred from the local reader assignment. Opus process remains untouched. No production DB was opened by this inventory; lsof inspected existing process handles only.

Local isolated tests can validate reader source independently. Passing tests, on-disk HEAD, heartbeat, PID existence and source receipts do not certify this process. Full A10 remains incomplete, and no live-runtime/financial/release/soak acceptance is granted.
