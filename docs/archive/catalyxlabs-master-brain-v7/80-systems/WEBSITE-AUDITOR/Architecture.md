# WEBSITE-AUDITOR Architecture

Canonical runtime:

```text
launchd
→ ./mm supervisor
→ SQLite leased queue + canonical runtime state
→ WEBSITE-AUDITOR workers
→ artifacts/reports/evidence
→ Obsidian operator workspace
```

Obsidian is the human-facing control and knowledge layer. It is not the canonical queue or runtime state.

See [[README]], [[Runtime]], [[Queue]], [[Approvals]], [[Observability]], [[Backups]], and [[Recovery]].
