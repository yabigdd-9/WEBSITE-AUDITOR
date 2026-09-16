#!/usr/bin/env python3
"""Smart pipeline tools — resume capability, progress tracking, audit aggregation.

Usage:
    python3 smart_tools.py resume --batch prospects.csv --days 7
    python3 smart_tools.py compare <domain>
    python3 smart_tools.py aggregate
    python3 smart_tools.py audit-summary
"""
import argparse, json, re, sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDITS = ROOT / "audits"

def get_audited_domains(days=0):
    """Return dict of domain -> {score, timestamp} for audits in audits/.
    If days > 0, only include audits newer than that threshold."""
    results = {}
    cutoff = datetime.now() - timedelta(days=days) if days > 0 else None
    for aj in AUDITS.glob("*.json"):
        try:
            data = json.loads(aj.read_text())
            ts = datetime.fromisoformat(data.get("timestamp", ""))
            if cutoff and ts < cutoff:
                continue
            domain = data.get("domain", aj.stem).replace("www.", "")
            if domain not in results or ts > datetime.fromisoformat(results[domain].get("timestamp", "")):
                results[domain] = {"score": data.get("score", 0), "timestamp": data.get("timestamp"), "defect_count": data.get("defect_count", 0)}
        except Exception:
            continue
    return results

def resume(batch_file, days=7):
    """Return URLs from batch_file that haven't been audited in last N days."""
    if not Path(batch_file).exists():
        print(f"❌ Batch file not found: {batch_file}")
        return []

    audited = get_audited_domains(days=days)
    urls = Path(batch_file).read_text().splitlines()
    pending = []
    skipped = []

    for line in urls:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'(?:https?://)?(?:www\.)?([^/]+)', line)
        domain = m.group(1).replace("www.", "") if m else line
        if domain in audited:
            skipped.append((domain, audited[domain]["score"], audited[domain]["timestamp"]))
        else:
            pending.append(line)

    print(f"📊 Resume Summary ({days}-day window):")
    print(f"  Batch: {len(urls)} URLs")
    print(f"  Audited recently: {len(skipped)}")
    print(f"  Pending: {len(pending)}")
    if skipped:
        print(f"\n  Skipped (already audited):")
        for d, s, t in sorted(skipped, key=lambda x: x[1]):
            print(f"    {d} — {s}/100 @ {t[:10]}")
    if pending:
        print(f"\n  Queued:")
        for u in pending:
            print(f"    {u}")
    return pending

def compare(domain):
    """Compare audits for a domain over time."""
    domain_clean = domain.replace("www.", "")
    files = sorted(AUDITS.glob(f"*{domain_clean}*.json"), key=lambda p: p.stat().st_mtime)
    if len(files) < 2:
        print(f"  Only {len(files)} audit(s) found — need 2+ for comparison.")
        return

    print(f"📈 Trend for {domain}:")
    print(f"  {'Date':<12} {'Score':<8} {'Defects':<10} Top Defect")
    print(f"  {'─'*50}")
    for f in files:
        data = json.loads(f.read_text())
        defects = data.get("defects", [])
        top = defects[0]["defect"][:35] if defects else "—"
        date = data.get("timestamp", "")[:10]
        print(f"  {date:<12} {data.get('score', 0):<8} {data.get('defect_count', 0):<10} {top}")

def aggregate():
    """Aggregate all audits into summary stats."""
    sites = []
    for aj in sorted(AUDITS.glob("*.json")):
        try:
            data = json.loads(aj.read_text())
            sites.append({
                "domain": data.get("domain", ""),
                "score": data.get("score", 0),
                "defects": data.get("defect_count", 0),
                "timestamp": data.get("timestamp", ""),
                "url": data.get("url", ""),
            })
        except Exception:
            continue

    if not sites:
        print("No audits found in audits/ directory.")
        return

    sites.sort(key=lambda s: s["score"])
    scores = [s["score"] for s in sites]
    avg = sum(scores) / len(scores)

    # Defect frequency
    defect_counts = {}
    for aj in AUDITS.glob("*.json"):
        try:
            data = json.loads(aj.read_text())
            for d in data.get("defects", []):
                defect = d.get("defect", "")
                defect_counts[defect] = defect_counts.get(defect, 0) + 1
        except Exception:
            continue
    top_defects = sorted(defect_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    print(f"📊 Aggregate Audit Summary")
    print(f"  Total sites: {len(sites)}")
    print(f"  Average score: {avg:.0f}/100")
    print(f"  Best: {sites[-1]['domain']} ({sites[-1]['score']}/100)")
    print(f"  Worst: {sites[0]['domain']} ({sites[0]['score']}/100)")
    print(f"\n  Top defects:")
    for defect, count in top_defects:
        print(f"    {count:3d}x {defect}")

    out = ROOT / "outputs" / "aggregate-summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "total_sites": len(sites),
        "average_score": round(avg, 1),
        "sites": sites,
        "top_defects": [{"defect": d, "count": c} for d, c in top_defects],
        "generated": datetime.now().isoformat()
    }, out.open("w"), indent=2)
    print(f"\n  Saved: {out}")

def main():
    p = argparse.ArgumentParser(description="Smart pipeline tools")
    sub = p.add_subparsers(dest="cmd")

    p_resume = sub.add_parser("resume", help="Get pending URLs from batch file")
    p_resume.add_argument("--batch", required=True, help="Batch file (CSV or URL list)")
    p_resume.add_argument("--days", type=int, default=7, help="Skip audited within N days")

    p_compare = sub.add_parser("compare", help="Compare audit history for domain")
    p_compare.add_argument("domain")

    sub.add_parser("aggregate", help="Aggregate stats across all audits")
    sub.add_parser("audit-summary", help="Alias for aggregate")

    args = p.parse_args()
    if args.cmd == "resume":
        resume(args.batch, args.days)
    elif args.cmd == "compare":
        compare(args.domain)
    elif args.cmd in ("aggregate", "audit-summary"):
        aggregate()
    else:
        p.print_help()

if __name__ == "__main__":
    main()
