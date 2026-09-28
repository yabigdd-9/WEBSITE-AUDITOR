# Retired MoneyMachine scripts

Archived on 2026-09-28 from their former package paths. These files are retained for audit history; they are not supported entrypoints and must not be moved back into the active tree. Each Python stub exits with a `BLOCKED` message.

| Former path | Reason retained here |
|---|---|
| `money-machine/seed_data.py` | Retired one-off migration; use the reviewed `mm_operator.py` workflow. |
| `money-machine/fix_contacts.py` | Retired one-off migration; do not fabricate approval or send history. |
| `money-machine/mark_sent.py` | Retired because it could fabricate send history. |
| `money-machine/PROMPTS/dispatch_judges.py` | Retired legacy `delegate_task` bypass; model execution remains paused. |

The archived copies remain fail-closed. This directory is historical evidence, not an executable compatibility layer.
