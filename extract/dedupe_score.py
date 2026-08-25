#!/usr/bin/env python3
"""
Dedupe overlapping engines (merge, never delete source refs) and score each
opportunity on the plan's 7 weighted dimensions. Deterministic signal-based
scoring — no invented facts. Emits MASTER_OPPORTUNITY_DATABASE.
"""
import json, re, csv, sys
from pathlib import Path
from collections import defaultdict

OUT = Path("/Users/defaultaccount/HERMES_MONEY_ENGINE")
engines = json.load(open(OUT / "extract/engines_raw.json"))

# ---------------- price parsing ----------------
MONEY = re.compile(r'(?:NZ\$|\$)\s?([\d][\d,]*)')

def parse_price(txt):
    if not txt:
        return None, None, False
    nums = [int(m.replace(",", "")) for m in MONEY.findall(txt)]
    nums = [n for n in nums if 20 <= n <= 100000]
    recurring = bool(re.search(r'/\s?month|per month|monthly|/mo|subscription|retainer', txt, re.I))
    if not nums:
        return None, None, recurring
    return min(nums), max(nums), recurring

def parse_auto(txt):
    m = re.search(r'([1-5])\s*/\s*5', txt or "")
    return int(m.group(1)) if m else None

# ---------------- dedupe ----------------
groups = defaultdict(list)
for r in engines:
    key = r["norm_key"] if r["norm_key"] else f"__uniq__{r['engine_id']}"
    groups[key].append(r)

merged = []
for key, rows in groups.items():
    rows = sorted(rows, key=lambda x: -x["body_chars"])          # richest block wins as canonical
    primary = dict(rows[0])
    primary["variants"] = []
    primary["source_refs"] = [r["source_section"] for r in rows]
    primary["merged_count"] = len(rows)
    for r in rows[1:]:
        # preserve useful differences as variants; fill blank canonical fields
        for f in ("category", "automation_potential", "price_label", "target_customer",
                  "problem", "offer", "required_inputs", "deliverables", "acquisition",
                  "kpis", "approval_points", "risks"):
            if not primary.get(f) and r.get(f):
                primary[f] = r[f]
        if r["engine_name"].lower() != primary["engine_name"].lower():
            primary["variants"].append({"name": r["engine_name"], "src": r["source_section"]})
    merged.append(primary)

merged.sort(key=lambda x: (x["source_file"], x["lineno"]))
for i, r in enumerate(merged, 1):
    r["engine_id"] = f"ME-{i:04d}"

# ---------------- scoring ----------------
RECUR_RX = re.compile(r'/\s?month|monthly|subscription|retainer|per month|ongoing|weekly|daily', re.I)
TRIGGER_RX = re.compile(r'observable|trigger|public|google|review|website|facebook|instagram|'
                        r'listing|search|directory|linkedin|maps|job ad|hiring', re.I)
DATAACCESS_RX = re.compile(r'crm|export|csv|invoice|xero|accounting|api|integration|'
                           r'system access|database|erp', re.I)
SITEVISIT_RX = re.compile(r'site visit|on-site|onsite|install|physical|travel|inspection|'
                          r'measure|labour|stock|delivery|van|truck', re.I)
SELFDELIVER_RX = re.compile(r'report|brief|audit|draft|list|copy|content|analysis|summary|'
                            r'pack|calendar|snapshot|template|document', re.I)

def score(r):
    txt = " ".join(str(r.get(f, "")) for f in
                   ("offer", "problem", "deliverables", "required_inputs",
                    "acquisition", "price_label", "category", "engine_name", "kpis"))
    lo, hi, recur_price = parse_price(r["price_label"])
    auto = parse_auto(r["automation_potential"])
    recurring = bool(recur_price or RECUR_RX.search(txt))
    needs_data = bool(DATAACCESS_RX.search(txt))
    physical = bool(SITEVISIT_RX.search(txt))
    observable = bool(TRIGGER_RX.search(txt))
    self_deliver = bool(SELFDELIVER_RX.search(txt))

    # speed_to_cash /25 : can Hermes produce proof + reach buyer with no client data
    s = 10
    if observable: s += 7           # prospect list buildable from public signals
    if not needs_data: s += 5       # no onboarding/integration blocker
    if self_deliver: s += 3
    if physical: s -= 5
    speed = max(0, min(25, s))

    # low_human_effort /20 : driven by stated automation potential
    if auto is not None:
        effort = {5: 20, 4: 16, 3: 11, 2: 6, 1: 3}[auto]
    else:
        effort = 14 if self_deliver else 9
    if physical: effort -= 4
    effort = max(0, min(20, effort))

    # recurring_revenue /20
    rec = 20 if recurring else (8 if re.search(r'report|monitor|alert|brief', txt, re.I) else 4)

    # gross_margin /15 : digital delivery + price band
    marg = 9
    if not physical: marg += 3
    if lo and lo >= 299: marg += 2
    if lo and lo >= 999: marg += 1
    if physical: marg -= 4
    marg = max(0, min(15, marg))

    # observable_demand /10
    dem = 0
    if observable: dem += 6
    if r["acquisition"]: dem += 2
    if r["problem"]: dem += 2
    dem = min(10, dem)

    # automation_potential /5
    autos = {5: 5, 4: 4, 3: 3, 2: 2, 1: 1}.get(auto, 3)

    # scalability /5
    scal = 5 if (not physical and not needs_data) else (3 if not physical else 1)

    total = speed + effort + rec + marg + dem + autos + scal
    band = ("EXECUTE_NOW" if total >= 80 else "VALIDATE_NEXT" if total >= 70
            else "BACKLOG" if total >= 55 else "HOLD" if total >= 40 else "KILL")
    return {
        "score_speed_to_cash": speed, "score_low_human_effort": effort,
        "score_recurring_revenue": rec, "score_gross_margin": marg,
        "score_observable_demand": dem, "score_automation_potential": autos,
        "score_scalability": scal, "total_score": total, "band": band,
        "price_low": lo, "price_high": hi, "recurring_possible": recurring,
        "needs_client_data": needs_data, "physical_component": physical,
        "observable_trigger": observable,
        "speed_to_cash_days": 1 if speed >= 22 else 3 if speed >= 18 else 7 if speed >= 13 else 21,
        "startup_cost_nzd": 0 if not physical else None,
        "human_effort": {20:"very_low",16:"low",11:"medium",6:"high",3:"very_high"}.get(effort,"medium"),
    }

for r in merged:
    r.update(score(r))
    r["execution_status"] = "DISCOVERED"
    r["revenue"] = 0
    r["next_action"] = ""

merged.sort(key=lambda x: -x["total_score"])

# ---------------- guards ----------------
scores = [r["total_score"] for r in merged]
fails = []
if len(set(scores)) < 15:
    fails.append(f"score variance too low: {len(set(scores))} distinct values")
if max(scores) - min(scores) < 25:
    fails.append(f"score range too narrow: {min(scores)}-{max(scores)}")
if sum(1 for r in merged if r["category"]) < 200:
    fails.append("category fill collapsed")
src_before = sum(1 for _ in engines)
src_after = sum(r["merged_count"] for r in merged)
if src_before != src_after:
    fails.append(f"source idea loss: {src_before} -> {src_after}")

json.dump(merged, open(OUT / "db/master_opportunity_database.json", "w"), indent=1)

cols = ["engine_id","engine_name","source_file","source_section","category","target_customer",
        "problem","offer","price_low","price_high","price_label","recurring_possible",
        "speed_to_cash_days","startup_cost_nzd","human_effort","automation_potential",
        "acquisition","execution_status","revenue","next_action","total_score","band",
        "score_speed_to_cash","score_low_human_effort","score_recurring_revenue",
        "score_gross_margin","score_observable_demand","score_automation_potential",
        "score_scalability","merged_count","needs_client_data","physical_component"]
with open(OUT / "db/MASTER_OPPORTUNITY_DATABASE.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in merged:
        w.writerow({k: (" ".join(str(r.get(k,"")).split())[:600]) for k in cols})

from collections import Counter
bands = Counter(r["band"] for r in merged)
print(f"source engine blocks : {src_before}")
print(f"after dedupe/merge   : {len(merged)}  (merged away {src_before-len(merged)})")
print(f"score range          : {min(scores)} - {max(scores)}  distinct={len(set(scores))}")
print(f"mean score           : {sum(scores)/len(scores):.1f}")
print("bands                :", dict(bands))
print("field fill           : category=%d customer=%d offer=%d price=%d recurring=%d" % (
    sum(1 for r in merged if r["category"]), sum(1 for r in merged if r["target_customer"]),
    sum(1 for r in merged if r["offer"]), sum(1 for r in merged if r["price_low"]),
    sum(1 for r in merged if r["recurring_possible"])))
if fails:
    print("GUARD FAILURES:"); [print("  !",f) for f in fails]; sys.exit(1)
print("GUARDS PASSED")
print("\n=== TOP 20 ===")
for r in merged[:20]:
    print(f" {r['total_score']:3d} {r['band']:13s} {r['engine_id']} {r['engine_name'][:58]}")
