#!/usr/bin/env python3
"""Final consolidator: read all judge + audit files, produce ranked JSON."""
import json, glob, os

reports = "/Users/yabigdd/MoneyMachine/reports"
audit_files = glob.glob(reports + "/AUDIT_*.json")
judge_files = glob.glob(reports + "/JUDGE_*.json")

# Load audits
audits = {}
for f in audit_files:
    if "CONSOLIDATED" in f or "CURRENT" in f:
        continue
    try:
        raw = open(f).read().strip()
        if raw.startswith("{|"):
            raw = raw[2:]
        if raw.endswith("|}"):
            raw = raw[:-2]
        d = json.loads(raw)
        audits[d["business_id"]] = d
    except Exception:
        pass

# Load judges
judges = {}
for f in judge_files:
    try:
        d = json.load(open(f))
        bid = d.get("business_id")
        if bid is not None:
            judges[bid] = d
    except Exception:
        pass

# Build ranked list
rows = []
for bid in sorted(set(list(audits.keys()) + list(judges.keys()))):
    a = audits.get(bid, {})
    j = judges.get(bid)
    name = a.get("business_name") or j.get("business_name", "?")
    ascore = a.get("overall_score", 0) or 0
    aconf = a.get("confidence")
    jdec = j.get("judge_decision") if j else "NO_JUDGE"
    jscore_new = None
    jconf = None
    reasons = None
    if j:
        adj = j.get("judge_score_adjustment")
        if adj:
            jscore_new = adj.get("overall_score_new")
        jconf = j.get("confidence")
        reasons = j.get("reasons")
    # Final score: judge-adjusted if available, else audit
    final_score = jscore_new if jscore_new is not None else ascore
    rows.append({
        "business_id": bid,
        "business_name": name,
        "website": a.get("website"),
        "region": a.get("audit", {}).get("region"),
        "audit_score": ascore,
        "audit_confidence": aconf,
        "judge_decision": jdec,
        "judge_score": jscore_new,
        "judge_confidence": jconf,
        "final_score": final_score,
        "judge_reasons": reasons,
    })

rows.sort(key=lambda r: r["final_score"], reverse=True)

# Write consolidated
out = {
    "generated": "2026-09-08T05:00Z",
    "total_audited": len(audits),
    "total_judged": len(judges),
    "ranked": rows,
    "accept_count": sum(1 for r in rows if r["judge_decision"] == "ACCEPT"),
    "revise_count": sum(1 for r in rows if r["judge_decision"] == "REVISE"),
    "reject_count": sum(1 for r in rows if r["judge_decision"] == "REJECT"),
    "no_judge_count": sum(1 for r in rows if r["judge_decision"] == "NO_JUDGE"),
}

with open(reports + "/BATCH_001_CONSOLIDATED_JUDGMENT.json", "w") as fh:
    json.dump(out, fh, indent=2)

print("=== FINAL RANKING ===")
print(f"{'#':<3} {'Business':<35} {'Audit':<6} {'J-Dec':<7} {'New':<5} {'Conf':<5} {'Final'}")
print("-" * 72)
for i, r in enumerate(rows, 1):
    jdec = r["judge_decision"]
    new = str(r["judge_score"]) if r["judge_score"] is not None else "—"
    jconf = str(r["judge_confidence"]) if r["judge_confidence"] else "—"
    print(f"{i:<3} {r['business_name'][:34]:<35} {r['audit_score']:<6} {jdec:<7} {new:<5} {jconf:<5} {r['final_score']}")

print(f"\nTotal audited: {len(audits)} | Judged: {len(judges)} | Accept: {out['accept_count']} | Revise: {out['revise_count']} | Reject: {out['reject_count']} | No-judge: {out['no_judge_count']}")
