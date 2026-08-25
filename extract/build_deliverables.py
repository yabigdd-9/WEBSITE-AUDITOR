#!/usr/bin/env python3
"""Generate all six required deliverables from the master database."""
import json, yaml, datetime, re
from pathlib import Path
from collections import Counter

OUT = Path("/Users/defaultaccount/HERMES_MONEY_ENGINE")
db = json.load(open(OUT / "db/master_opportunity_database.json"))
NOW = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
TODAY = datetime.date.today().isoformat()

byid = {r["engine_id"]: r for r in db}

# ---- ACTIVE_3 : mandated by plan (initial_three_engines), not score-selected ----
ACTIVE_3 = [
    {"slot": 1, "name": "Website Rescue Lead Engine",
     "primary": "ME-0462", "supporting": ["ME-0008", "ME-0331", "ME-0380", "ME-0387"],
     "objective": "Find businesses with obvious website problems and prepare proof-backed offers."},
    {"slot": 2, "name": "Reputation / Unanswered Review Engine",
     "primary": "ME-0007", "supporting": ["ME-0006", "ME-0042", "ME-0392", "ME-0393"],
     "objective": "Find businesses with visible reputation-management gaps."},
    {"slot": 3, "name": "CATALYX Flooring Lead Engine",
     "primary": "ME-0001", "supporting": ["ME-0449", "ME-0452", "ME-0453", "ME-0454"],
     "objective": "Generate qualified Christchurch/Canterbury flooring prospects."},
]

def fmt(v, n=260):
    return " ".join(str(v or "").split())[:n]

# ---------------- TOP_20_MONEY_ENGINES.md ----------------
top20 = db[:20]
L = ["# TOP 20 MONEY ENGINES", "", f"_Generated {NOW} · ranked by weighted opportunity score (max 100)_",
     "", "| # | ID | Engine | Score | Band | Price (NZD) | Recurring | Auto | Source |",
     "|---|----|--------|-------|------|-------------|-----------|------|--------|"]
for i, r in enumerate(top20, 1):
    price = (f"${r['price_low']:,}–${r['price_high']:,}" if r["price_low"] else "—")
    L.append(f"| {i} | {r['engine_id']} | {fmt(r['engine_name'],60)} | **{r['total_score']}** | "
             f"{r['band']} | {price} | {'yes' if r['recurring_possible'] else 'no'} | "
             f"{r['automation_potential'] or '—'} | {r['source_file'].replace('HERMES_MEGA_MONEY_ENGINE_','').replace('.md','')} |")
L += ["", "## Detail", ""]
for i, r in enumerate(top20, 1):
    L += [f"### {i}. {r['engine_name']}  `{r['engine_id']}` — {r['total_score']}/100 ({r['band']})",
          f"- **Target customer:** {fmt(r['target_customer'],180) or '_not stated in source_'}",
          f"- **Offer:** {fmt(r['offer'],320) or '_not stated_'}",
          f"- **Problem:** {fmt(r['problem'],240) or '_not stated_'}",
          f"- **Lead source:** {fmt(r['acquisition'],200) or '_not stated_'}",
          f"- **Score split:** speed {r['score_speed_to_cash']}/25 · effort {r['score_low_human_effort']}/20 · "
          f"recurring {r['score_recurring_revenue']}/20 · margin {r['score_gross_margin']}/15 · "
          f"demand {r['score_observable_demand']}/10 · automation {r['score_automation_potential']}/5 · "
          f"scale {r['score_scalability']}/5",
          f"- **Source:** `{r['source_section']}`" + (f" (+{r['merged_count']-1} merged duplicate(s))" if r["merged_count"] > 1 else ""),
          ""]
(OUT / "outputs/TOP_20_MONEY_ENGINES.md").write_text("\n".join(L))

# ---------------- ACTIVE_3_EXECUTION_QUEUE.md ----------------
A = ["# ACTIVE 3 EXECUTION QUEUE", "",
     f"_Generated {NOW}_", "",
     "Execution limit: **3 unproven engines running simultaneously** (plan rule). "
     "These three are mandated by the plan's `initial_three_engines`, which overrides raw score rank.", ""]
for e in ACTIVE_3:
    p = byid[e["primary"]]
    A += [f"## Slot {e['slot']} — {e['name']}",
          f"**Objective:** {e['objective']}", "",
          f"- **Primary source engine:** `{p['engine_id']}` {p['engine_name']} — score {p['total_score']}/100 ({p['band']})",
          f"- **Supporting engines:** " + ", ".join(f"`{s}` {fmt(byid[s]['engine_name'],40)}" for s in e["supporting"] if s in byid),
          f"- **Offer (from source):** {fmt(p['offer'],300) or '_not stated_'}",
          f"- **Target customer:** {fmt(p['target_customer'],160) or '_not stated_'}",
          f"- **Indicative price:** {fmt(p['price_label'],120) or '_not stated_'}",
          f"- **Status:** ACTIVE · **Stage:** research not yet run",
          "", "**Daily pipeline (10 steps):**",
          "1. Research 60–100 candidates · 2. Reject weak fit · 3. Score qualified · "
          "4. Select strongest 20–30 · 5. Create personalised proof · 6. Prepare outreach · "
          "7. Judge every customer-facing item · 8. Proofer verifies · 9. Queue for Dion approval · "
          "10. Record results + next actions", "",
          "**Blocked-on-human:** cold outreach send (approval gate), any final pricing commitment.", ""]
A += ["## Not started (deliberately)", "",
      f"{len(db)-3} other engines remain in the database at DISCOVERED. "
      "Nothing else is activated until one of the three above produces a paid pilot or is killed.", ""]
(OUT / "outputs/ACTIVE_3_EXECUTION_QUEUE.md").write_text("\n".join(A))

# ---------------- APPROVAL_QUEUE.yaml ----------------
approval = {
    "generated_at": NOW,
    "policy": "Nothing in this queue has been sent, published, purchased or committed.",
    "requires_dion_approval": [
        {"id": "APR-001", "type": "cold_outreach_send",
         "engine": "Website Rescue Lead Engine",
         "description": "Send personalised website-rescue outreach emails to researched prospects.",
         "blocked_until": "Prospect research + proof assets + Judge >=80 + Proofer pass",
         "status": "NOT_READY", "reason_not_ready": "prospect research not yet executed"},
        {"id": "APR-002", "type": "cold_outreach_send",
         "engine": "Reputation / Unanswered Review Engine",
         "description": "Send review-gap outreach to businesses with visible reputation gaps.",
         "blocked_until": "Prospect research + proof assets + Judge >=80 + Proofer pass",
         "status": "NOT_READY", "reason_not_ready": "prospect research not yet executed"},
        {"id": "APR-003", "type": "cold_outreach_send",
         "engine": "CATALYX Flooring Lead Engine",
         "description": "Send flooring prospect outreach in Christchurch/Canterbury.",
         "blocked_until": "Prospect research + proof assets + Judge >=80 + Proofer pass",
         "status": "NOT_READY", "reason_not_ready": "prospect research not yet executed"},
        {"id": "APR-004", "type": "pricing_commitment",
         "engine": "all",
         "description": "Any quote containing final pricing to a real prospect.",
         "blocked_until": "Dion sets approved price bands per engine",
         "status": "AWAITING_DION",
         "ask": "Confirm sellable price bands for the three active engines (source suggests "
                "NZ$149–799 one-off, NZ$99–599/month recurring)."},
    ],
    "autonomous_no_approval_needed": [
        "prospect research from public sources", "opportunity scoring", "draft creation",
        "internal reports", "file organisation", "database maintenance", "checkpointing"],
}
yaml.safe_dump(approval, open(OUT / "approval/APPROVAL_QUEUE.yaml", "w"), sort_keys=False, width=100)

# ---------------- HERMES_EXECUTION_STATE.yaml ----------------
bands = Counter(r["band"] for r in db)
state = {
    "version": "1.0", "owner": "Dion", "updated_at": NOW,
    "current_phase": "PHASE_5_COMPLETE_ALL_FILES_EXTRACTED",
    "phases": {
        "phase_1_part1": {"status": "COMPLETE", "engines_extracted": 118},
        "phase_2_part2": {"status": "COMPLETE", "engines_extracted": 87},
        "phase_3_part3": {"status": "COMPLETE", "engines_extracted": 113},
        "phase_4_part4": {"status": "COMPLETE", "engines_extracted": 94},
        "phase_5_part5": {"status": "COMPLETE", "engines_extracted": 92},
    },
    "portfolio": {
        "source_engine_blocks": 504, "after_dedupe": len(db),
        "merged_duplicates": 504 - len(db),
        "meta_blocks_excluded": 79,
        "bands": dict(bands),
    },
    "active_engine": "Website Rescue Lead Engine",
    "active_tasks": [
        {"id": "T-001", "engine": "Website Rescue Lead Engine",
         "task": "Prospect research: detection methodology + candidate criteria", "status": "QUEUED", "agent": "Researcher"},
        {"id": "T-002", "engine": "CATALYX Flooring Lead Engine",
         "task": "Christchurch/Canterbury flooring prospect research", "status": "QUEUED", "agent": "Researcher"},
    ],
    "completed_tasks": [
        {"id": "C-001", "task": "Create workspace + state file", "at": NOW},
        {"id": "C-002", "task": "Extract 504 engine blocks from all 5 source files (guards passed)", "at": NOW},
        {"id": "C-003", "task": f"Dedupe to {len(db)} engines, zero source ideas deleted", "at": NOW},
        {"id": "C-004", "task": "Score all engines on 7 weighted dimensions (range 28-95)", "at": NOW},
        {"id": "C-005", "task": "Generate MASTER_OPPORTUNITY_DATABASE (json+csv)", "at": NOW},
        {"id": "C-006", "task": "Generate TOP_20 / ACTIVE_3 / APPROVAL_QUEUE", "at": NOW},
    ],
    "failed_tasks": [], "retry_queue": [],
    "approval_queue_ref": "approval/APPROVAL_QUEUE.yaml",
    "revenue": {"total_nzd": 0, "paid_customers": 0, "pilots": 0},
    "concurrency": {"current_max_concurrent_children": 2, "mode": "initial_conservative",
                    "escalate_to": 3, "escalate_condition": "zero 429s across 2 consecutive batches"},
    "model_routing": {
        "orchestrator": "meituan/longcat-2.0:free",
        "researcher": ["upstage/solar-pro4:free", "stepfun/step-3.7-flash:free"],
        "executor_sales": ["tencent/hy3:free", "stepfun/step-3.7-flash:free"],
        "executor_content": ["stepfun/step-3.7-flash:free", "meituan/longcat-2.0:free"],
        "coder": ["poolside/laguna-s-2.1:free", "poolside/laguna-xs-2.1:free"],
        "lightweight_worker": "poolside/laguna-xs-2.1:free",
        "judge": ["tencent/hy3:free", "meituan/longcat-2.0:free"],
        "proofer": ["upstage/solar-pro4:free", "stepfun/step-3.7-flash:free"],
        "note": "delegation.model / delegation.provider intentionally UNSET in config.yaml so "
                "subagents inherit working parent credentials; pinning a non-nous model misroutes to 401.",
    },
    "next_action": "Run Researcher on T-001 (Website Rescue detection methodology + candidate criteria), "
                   "then T-002 (CATALYX flooring prospects). Concurrency 2.",
    "artifacts": {
        "master_db_json": "db/master_opportunity_database.json",
        "master_db_csv": "db/MASTER_OPPORTUNITY_DATABASE.csv",
        "top20": "outputs/TOP_20_MONEY_ENGINES.md",
        "active3": "outputs/ACTIVE_3_EXECUTION_QUEUE.md",
        "approval": "approval/APPROVAL_QUEUE.yaml",
        "daily_report": f"outputs/DAILY_OPERATOR_REPORT_{TODAY}.md",
        "extractor": "extract/extract_engines.py",
        "scorer": "extract/dedupe_score.py",
    },
    "resume_protocol": [
        "Read this file.", "Read latest DAILY_OPERATOR_REPORT.",
        "Do not re-extract source files (phases 1-5 COMPLETE).",
        "Resume from active_tasks with status QUEUED or IN_PROGRESS.",
        "Continue highest-value unfinished action.",
    ],
}
yaml.safe_dump(state, open(OUT / "state/HERMES_EXECUTION_STATE.yaml", "w"), sort_keys=False, width=100)

print("wrote:")
for p in ["outputs/TOP_20_MONEY_ENGINES.md", "outputs/ACTIVE_3_EXECUTION_QUEUE.md",
          "approval/APPROVAL_QUEUE.yaml", "state/HERMES_EXECUTION_STATE.yaml"]:
    f = OUT / p
    print(f"  {p}  {f.stat().st_size:,}b")
print(f"\ndb: {len(db)} engines · bands {dict(bands)}")
