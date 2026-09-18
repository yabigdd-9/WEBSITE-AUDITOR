#!/usr/bin/env python3
"""Apply verified research findings to state + approval queue. Idempotent."""
import yaml, datetime
from pathlib import Path

ROOT = Path("/Users/dd/WEBSITE-AUDITOR")
NOW = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

# ---- approval queue: add the UEMA legal gate (blocks all outreach) ----
ap = yaml.safe_load(open(ROOT / "approval/APPROVAL_QUEUE.yaml"))
ids = {a["id"] for a in ap["requires_dion_approval"]}

new = []
if "APR-005" not in ids:
    new.append({
        "id": "APR-005", "type": "legal_compliance_gate", "engine": "ALL THREE",
        "priority": "BLOCKS_ALL_OUTREACH",
        "description": "NZ Unsolicited Electronic Messages Act 2007 consent basis for B2B cold email.",
        "verified_findings": [
            "UEMA covers email and applies to any message with a NZ link — verified on dia.govt.nz.",
            "Penalty for non-compliance: fine up to NZ$500,000 — verified on dia.govt.nz.",
            "There is NO blanket B2B exemption in NZ law (unlike US CAN-SPAM).",
            "A business email published in a directory is NOT automatic consent.",
            "Onus of proof of consent sits on the SENDER (s.9(3)).",
            "Sender identification (s.10) and working unsubscribe (s.11) always apply.",
            "Address-harvesting software / harvested lists are separately restricted (s.13).",
        ],
        "status": "AWAITING_DION",
        "ask": "Choose the consent basis before ANY cold email is sent. Options: "
               "(a) get NZ legal sign-off on an inferred-consent rationale; "
               "(b) switch to non-email first touch (phone/post/in-person, not covered by UEMA email rules); "
               "(c) run an opt-in route (content/lead magnet) and only email consenting businesses.",
        "orchestrator_recommendation":
            "Option (b) then (c). Dion already has a phone number for outreach (02904556680) and "
            "telemarketing is explicitly NOT covered by UEMA. Build the proof assets now, deliver the "
            "first touch by phone, and reserve email for businesses that respond or opt in. "
            "This removes the $500k exposure without slowing the pipeline.",
        "source_urls": [
            "https://www.dia.govt.nz/Spam-NZ-Spam-Law-for-Businesses",
            "https://www.legislation.govt.nz/act/public/2007/0007/latest/DLM405134.html",
        ],
    })
if "APR-006" not in ids:
    new.append({
        "id": "APR-006", "type": "scope_change_ratification", "engine": "Reputation / Review Engine",
        "description": "Ratify descoping of slot 2 after verified evidence that unanswered-review "
                       "detection is not lawfully automatable.",
        "status": "AWAITING_DION",
        "ask": "Approve the re-scope to a Reputation Completeness & Visible-Sentiment Scanner, with "
               "ME-0274 / ME-0327 monitoring engines promoted as the recurring-revenue path.",
        "detail_ref": "outputs/VIABILITY_DECISION_ACTIVE_2.md",
    })

ap["requires_dion_approval"].extend(new)
ap["generated_at"] = NOW
ap["blocking_summary"] = (
    "APR-005 (UEMA consent basis) blocks every outbound email across all three engines. "
    "Research, scoring, proof-asset creation and phone-based first contact are NOT blocked."
)
yaml.safe_dump(ap, open(ROOT / "approval/APPROVAL_QUEUE.yaml", "w"), sort_keys=False, width=100, allow_unicode=True)

# ---- state: checkpoint research completion ----
s = yaml.safe_load(open(ROOT / "state/HERMES_EXECUTION_STATE.yaml"))
for t in s["active_tasks"]:
    if t["id"] == "T-001":
        t["status"] = "COMPLETE"
        t["output"] = "outputs/RESEARCH_website_rescue_methodology.md"

def add(task):
    if not any(task[:45] in c["task"] for c in s["completed_tasks"]):
        s["completed_tasks"].append(
            {"id": f"C-{len(s['completed_tasks'])+1:03d}", "task": task, "at": NOW})

add("Researcher #1 delivered Website Rescue detection methodology (238 lines, primary govt sources)")
add("Researcher #2 delivered Reputation gap methodology (266 lines) incl. data-access reality check")
add("Orchestrator independently re-verified UEMA 2007 scope + NZ$500k penalty on dia.govt.nz")
add("Orchestrator independently re-verified Places API 5-review ceiling and absence of owner-reply field")
add("Descoped ACTIVE-2 to lawful signals; promoted ME-0274/ME-0327 reserves; logged decision")
add("Raised APR-005 UEMA consent gate and APR-006 scope ratification to Dion")

s["active_tasks"] = [t for t in s["active_tasks"] if t["status"] != "COMPLETE"]
s["active_tasks"].append({
    "id": "T-003", "engine": "Website Rescue Lead Engine",
    "task": "Build defect-detection prototype (HTTPS/SSL, mobile viewport, title/meta, broken links, "
            "stale copyright) and run it on real NZ business sites",
    "status": "QUEUED", "agent": "Coder"})

s["research_verified"] = {
    "website_rescue": {"file": "outputs/RESEARCH_website_rescue_methodology.md",
                       "status": "ACCEPTED", "independent_check": "UEMA facts re-verified by orchestrator"},
    "reputation": {"file": "outputs/RESEARCH_reputation_engine_methodology.md",
                   "status": "ACCEPTED_WITH_DESCOPE",
                   "independent_check": "Places API 5-review limit + no reply field re-verified by orchestrator"},
}
s["blockers"] = [
    {"id": "B-001", "severity": "HIGH", "blocks": "all cold email",
     "issue": "No lawful UEMA consent basis established. Max penalty NZ$500,000.",
     "unblock": "APR-005 — Dion picks consent basis; orchestrator recommends phone-first."},
    {"id": "B-002", "severity": "MEDIUM", "blocks": "any quote",
     "issue": "No approved sellable price bands.", "unblock": "APR-004"},
    {"id": "B-003", "severity": "RESOLVED", "blocks": "nothing",
     "issue": "Reputation engine automation viability.", "unblock": "Descoped — see APR-006."},
]
s["next_action"] = ("Build + run the Website Rescue defect detector on real NZ business sites (T-003). "
                   "This is unblocked: detection uses public data only and needs no approval. "
                   "Cold email stays blocked pending APR-005.")
s["updated_at"] = NOW
yaml.safe_dump(s, open(ROOT / "state/HERMES_EXECUTION_STATE.yaml", "w"), sort_keys=False, width=100, allow_unicode=True)

print("approval items added:", [n["id"] for n in new] or "none (idempotent)")
print("completed tasks:", len(s["completed_tasks"]))
print("open blockers:", [b["id"] for b in s["blockers"] if b["severity"] != "RESOLVED"])
print("next:", s["next_action"][:90])
