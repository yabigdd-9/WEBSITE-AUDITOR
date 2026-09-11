#!/usr/bin/env python3
"""Read all judge results and print a clean summary table."""
import json, glob, os

reports = "/Users/yabigdd/MoneyMachine/reports"
judge_files = sorted(glob.glob(reports + "/JUDGE_*.json"))
audit_files = sorted(glob.glob(reports + "/AUDIT_*.json"))

audit_by_id = {}
for f in audit_files:
    if "CONSOLIDATED" in f or "CURRENT" in f:
        continue
    try:
        with open(f) as fh:
            d = json.loads(fh.read().strip().lstrip("{|").rstrip("|}"))
            audit_by_id[d["business_id"]] = d
    except Exception:
        pass

judge_by_id = {}
for f in judge_files:
    try:
        with open(f) as fh:
            d = json.load(fh)
            bid = d.get("business_id") or d.get("original_score")
            if bid is not None:
                judge_by_id[bid] = d
    except Exception:
        pass

print("=== ALL JUDGE RESULTS (final) ===\n")
print(f"{'#':<3} {'Business':<35} {'Audit':<6} {'J-Dec':<7} {'J-Score':<8} {'Conf':<5} {'Verdict'}")
print("-" * 80)
results = []
for bid in sorted(set(list(audit_by_id.keys()) + list(judge_by_id.keys()))):
    a = audit_by_id.get(bid, {})
    j = judge_by_id.get(bid)
    name = a.get("business_name", "?") or j.get("business_name", "?")
    ascore = a.get("overall_score", "?")
    jdec = j.get("judge_decision", "NO JUDGE") if j else "NO JUDGE"
    jscore = j["judge_score_adjustment"]["overall_score_new"] if j and j.get("judge_score_adjustment") else "—"
    jconf = j.get("confidence", "?") if j else "—"
    results.append((bid, name, ascore, jdec, jscore, jconf, j))
    print(f"{bid:<3} {name[:34]:<35} {ascore:<6} {jdec:<7} {str(jscore):<8} {str(jconf):<5} {jdec}")

# Now build JSON consolidated
consolidated = {
    "generated": "2026-09-08T05:00Z",
    "total_audited": len(audit_by_id),
    "total_judged": len(judge_by_id),
    "by_business": []
}
for bid, name, ascore, jdec, jscore, jconf, j in sorted(results, key=lambda r: (r[4] if isinstance(r[4], int) else r[2] or 0), reverse=True):
    entry = {
        "business_id": bid,
        "business_name": name,
        "audit_score": ascore,
        "audit_confidence": audit_by_id.get(bid, {}).get("confidence"),
        "website": audit_by_id.get(bid, {}).get("website"),
        "judge_decision": jdec,
        "judge_score": jscore,
        "judge_confidence": jconf,
    }
    if j and j.get("reasons"):
        entry["judge_reasons"] = j["reasons"]
    consolidated["by_business"].append(entry)

with open(reports + "/BATCH_001_CONSOLIDATED_JUDGMENT.json", "w") as fh:
    json.dump(consolidated, fh, indent=2)

print(f"\nSaved {len(results)} entries to BATCH_001_CONSOLIDATED_JUDGMENT.json")
print(f"\nSummary: {len(judge_by_id)} judged, {sum(1 for r in results if r[3]=='ACCEPT')} ACCEPT, {sum(1 for r in results if r[3]=='REVISE')} REVISE, {sum(1 for r in results if r[3]=='REJECT')} REJECT")
