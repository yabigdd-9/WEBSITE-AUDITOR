# HERMES Money Engine — Internal Audit Dashboard

A minimal, dependency-light internal dashboard that aggregates and displays the
audit/health information the **HERMES Money Engine** already produces. It reads
the existing artifacts **live, on every request** — no snapshots, no external
network calls.

## What it shows

1. **Pipeline Summary** — counts derived from `db/master_opportunity_database.json`
   (total opportunities, band distribution, top categories, automation potential,
   execution status, average total score). Cross-checked against the CSV row count.
2. **Approval Queue** — items requiring Dion's approval from
   `approval/APPROVAL_QUEUE.yaml`, broken down by status
   (`AWAITING_DION`, `NOT_READY`, `RESOLVED_BY_DION`), with the blocking summary.
3. **Execution State** — phase, portfolio stats, band distribution, active engine,
   and active/completed tasks from `state/HERMES_EXECUTION_STATE.yaml`.
4. **Output Reports** — a linked list of every `outputs/*.md` report (opens the
   file via `file://` in a new tab).

## How to run

From the repo root (`HERMES_MONEY_ENGINE/`):

```bash
python3 audit-dashboard/server.py            # serves http://127.0.0.1:8755/
# or pick a port:
python3 audit-dashboard/server.py 9000       # http://127.0.0.1:9000/
```

Then open the printed URL in a browser. Refresh to re-read the artifacts.

### Dependencies
- Python 3.8+ (standard library only for the server).
- **PyYAML** for parsing the `.yaml` artifacts: `python3 -m pip install pyyaml`
  (already present in the dev environment where this was built).

## How to view (no server)

The dashboard is server-rendered, so a browser reading `file://.../index.html`
directly cannot read the sibling JSON/YAML (browsers block `file://` fetches).
Use the tiny server above — it IS the "static HTML dashboard," rendered on demand
with live data. (A pure single-file `index.html` would need to be regenerated
whenever artifacts change; this design avoids that staleness.)

## Files
- `audit-dashboard/server.py` — the entire dashboard (stdlib HTTP server + PyYAML).
- `audit-dashboard/README.md` — this file.

## Assumptions
- The dashboard lives in `HERMES_MONEY_ENGINE/audit-dashboard/`; the artifacts are
  read from the **parent directory** (`..`), so the repo layout must stay as-is.
- `master_opportunity_database.json` is a JSON **list** of opportunity records, each
  carrying `band`, `category`, `automation_potential`, `execution_status`, and
  `total_score` fields (verified against the current data).
- Approval items carry a `status` field; anything not equal to `RESOLVED_BY_DION`
  is treated as "awaiting / not ready" for the headline count.
- Output reports are the `*.md` files directly inside `outputs/` (not the outreach/
  research sub-reports).
- This is an **internal tool** — report links use `file://` and the server binds to
  `127.0.0.1` only. Do not expose it on a public interface.
- Built on branch `agent/task-002-audit-dashboard`; committed locally, not pushed.
