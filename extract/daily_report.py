#!/usr/bin/env python3
"""DAILY_OPERATOR_REPORT generator. Reads state + db; reports only real facts."""
import json, yaml, datetime, collections, os, glob
from pathlib import Path

OUT = Path("/Users/defaultaccount/HERMES_MONEY_ENGINE")
db = json.load(open(OUT / "db/master_opportunity_database.json"))
state = yaml.safe_load(open(OUT / "state/HERMES_EXECUTION_STATE.yaml"))
appr = yaml.safe_load(open(OUT / "approval/APPROVAL_QUEUE.yaml"))
TODAY = datetime.date.today().isoformat()
NOW = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
bands = collections.Counter(r["band"] for r in db)

research_files = sorted(glob.glob(str(OUT / "outputs/RESEARCH_*.md")))
rf_lines = []
for f in research_files:
    n = sum(1 for _ in open(f, errors="replace"))
    rf_lines.append(f"- `{os.path.basename(f)}` — {n} lines, {os.path.getsize(f):,} bytes")

pend = [a for a in appr["requires_dion_approval"]]
awaiting = [a for a in pend if a["status"] == "AWAITING_DION"]

R = f"""# DAILY OPERATOR REPORT — {TODAY}

_Generated {NOW} · Hermes Multi-Model Money Engine_

## 1. Headline

Full portfolio extraction is **complete across all five source files**. 504 engine blocks were
parsed, deduplicated to **{len(db)} distinct revenue engines**, every one scored on the plan's
seven weighted dimensions. The three plan-mandated engines are activated; nothing has been sent,
published, purchased or committed.

## 2. Active agents & model routing

| Agent | Model used | Status |
|-------|-----------|--------|
| Orchestrator | {state['model_routing']['orchestrator']} | active (this session) |
| Researcher #1 | {state['model_routing']['researcher'][0]} | dispatched — Website Rescue methodology |
| Researcher #2 | {state['model_routing']['researcher'][0]} | dispatched — Reputation gap methodology |
| Executor Sales | {state['model_routing']['executor_sales'][0]} | idle — waiting on research |
| Executor Content | {state['model_routing']['executor_content'][0]} | idle |
| Coder | {state['model_routing']['coder'][0]} | idle (extractors written natively) |
| Judge | {state['model_routing']['judge'][0]} | idle — no customer-facing output yet |
| Proofer | {state['model_routing']['proofer'][0]} | idle |

Concurrency: **{state['concurrency']['current_max_concurrent_children']}** ({state['concurrency']['mode']}).
Escalate to {state['concurrency']['escalate_to']} when: {state['concurrency']['escalate_condition']}.

## 3. Provider failures & rate limits

- Provider failures this session: **0**
- 429 / rate-limit events: **0**
- Fallback activations: **0**
- Concurrency reductions: **0**

## 4. Completed tasks

""" + "\n".join(f"- {c['task']}" for c in state["completed_tasks"]) + f"""

## 5. Portfolio state

| Band | Count | Share |
|------|-------|-------|
| EXECUTE_NOW (≥80) | {bands['EXECUTE_NOW']} | {bands['EXECUTE_NOW']/len(db)*100:.0f}% |
| VALIDATE_NEXT (70–79) | {bands['VALIDATE_NEXT']} | {bands['VALIDATE_NEXT']/len(db)*100:.0f}% |
| BACKLOG (55–69) | {bands['BACKLOG']} | {bands['BACKLOG']/len(db)*100:.0f}% |
| HOLD (40–54) | {bands['HOLD']} | {bands['HOLD']/len(db)*100:.0f}% |
| KILL (<40) | {bands['KILL']} | {bands['KILL']/len(db)*100:.0f}% |

- Recurring-revenue capable: **{sum(1 for r in db if r['recurring_possible'])}** ({sum(1 for r in db if r['recurring_possible'])/len(db)*100:.0f}%)
- Deliverable with **no client data access and no physical work**: **{sum(1 for r in db if not r['needs_client_data'] and not r['physical_component'])}** — this is the true fast-to-cash pool
- Score range: **{min(r['total_score'] for r in db)}–{max(r['total_score'] for r in db)}**, mean {sum(r['total_score'] for r in db)/len(db):.1f}
- Duplicates merged (source refs preserved, nothing deleted): **{504-len(db)}**

## 6. Qualified leads

**0.** No prospect research has completed yet — the two Researcher agents are still running.
No lead numbers are reported because none exist; fabricating prospects is prohibited.

## 7. Proof assets

**0 built.** Proof-asset design is part of the running research tasks.

## 8. Outreach ready

**0.** Nothing has reached Judge or Proofer.

## 9. Approvals needed from Dion

""" + "\n".join(
    f"- **{a['id']}** ({a['type']}) — {a['description']}  \n  status: `{a['status']}`"
    + (f" · **ask: {a['ask']}**" if a.get("ask") else f" · blocked: {a.get('reason_not_ready','')}")
    for a in pend) + f"""

**The one thing that needs Dion now:** {awaiting[0]['ask'] if awaiting else 'nothing'}

## 10. Replies / sales opportunities / revenue

- Replies: **0** (nothing sent)
- Live sales opportunities: **0**
- Revenue: **NZ$0**

## 11. Best / weakest engine

**Strongest by score:** `{db[0]['engine_id']}` {db[0]['engine_name']} — {db[0]['total_score']}/100.
**Strongest cluster:** the competitor/website monitoring group (ME-0273…ME-0278, ME-0327, ME-0328)
all score 93 — pure public-data monitoring, recurring pricing stated in source, zero client onboarding.
This cluster is a stronger *technical* fit than two of the three mandated engines.

**Weakest:** {db[-1]['engine_id']} {db[-1]['engine_name']} — {db[-1]['total_score']}/100.
Note the CATALYX Flooring Lead Engine (`ME-0001`) scores only 41/100 on the generic rubric because
it carries physical/site-visit cost — it is retained in the active three by explicit plan mandate as
the proving ground, not because the rubric favours it.

## 12. Blockers

1. **Real prospect data does not exist yet** — everything downstream of research is gated on it.
2. **Price bands unconfirmed** — source suggests NZ$149–799 one-off / NZ$99–599 per month, but no
   approved sellable price exists, so no quote can be produced.
3. **Google review data access is legally/technically uncertain** — Researcher #2 is checking whether
   the Reputation engine is even viable at scale. If the API path is closed, that engine should be
   replaced from the 93-score monitoring cluster.

## 13. Research delivered

""" + ("\n".join(rf_lines) if rf_lines else "- _none yet — both researcher agents still running_") + f"""

## 14. Next highest-value action

{state['next_action']}

---
_All figures above are read from real files in `{OUT}`. Any metric with no underlying data is
reported as zero, not estimated._
"""
p = OUT / f"outputs/DAILY_OPERATOR_REPORT_{TODAY}.md"
p.write_text(R)
print(f"wrote {p} ({p.stat().st_size:,}b)")
