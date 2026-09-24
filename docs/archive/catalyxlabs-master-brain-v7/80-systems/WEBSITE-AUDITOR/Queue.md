# WEBSITE-AUDITOR Queue

The canonical queue is SQLite with leases, heartbeats, bounded retries, stale-worker recovery, crash recovery, and dead-letter visibility.

Obsidian may display queue state but must not become queue authority.
