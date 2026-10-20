---
generated_by: ./mm obsidian-sync
authoritative: false
runtime_authority: SQLite + ./mm + launchd
send_authority: false
title: Recovery
---

# Recovery

1. Check ./mm supervisor status.
2. Check ./mm supervisor health.
3. Review worker logs and dead-letter state.
4. Confirm SQLite/database integrity before changing state.
5. Restart with ./mm supervisor restart only after identifying the failure boundary.
6. Never use Obsidian edits as recovery commands.
