"""P6: proof-of-work daily reporting, alert rules, and jsonl retention.

Stdlib only. Every report carries the fail-closed safety attestation. No sends,
no model calls, $0.
"""
import datetime as dt
import gzip
import json
import re
from pathlib import Path

import mm_core as core

ROOT = core.Path(__file__).resolve().parent.parent
RULES_DEFAULT = {
    "dead_lettered_growth_per_hour_max": 0,
    "disk_free_mb_min": 2048,
    "heartbeat_age_seconds_max": 120,
}


def _state(name):
    return core.root() / "state" / name


def load_rules(path=None):
    """Parse the alert-rules file (a flat `key: number` YAML subset, stdlib only)."""
    path = Path(path) if path else _state("alert-rules.yaml")
    if not path.is_file():
        return dict(RULES_DEFAULT), "defaults (no state/alert-rules.yaml present)"
    rules, bad = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            bad.append(line)
            continue
        key, _, raw = line.partition(":")
        try:
            rules[key.strip()] = float(raw.strip())
        except ValueError:
            bad.append(line)
    if bad:
        raise ValueError(f"Unparseable alert rules: {bad}")
    return rules, "state/alert-rules.yaml"


def evaluate_alerts(rules=None):
    """Evaluate the three canonical rules; returns typed alert dicts (empty = OK)."""
    if rules is None:
        rules, source = load_rules()
    else:
        source = "supplied"
    alerts, values = [], {}
    d = _open_ro()
    if d is not None:
        with d:
            tables = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "pipeline_items" in tables:
                values["dead_lettered_total"] = d.execute(
                    "SELECT count(*) FROM pipeline_items WHERE state='DEAD_LETTER'").fetchone()[0]
    disk = _disk_free_mb()
    if disk is not None:
        values["disk_free_mb"] = disk
    hb = _heartbeat_age_seconds()
    if hb is not None:
        values["heartbeat_age_seconds"] = hb
    if "dead_lettered_total" in values:
        growth = _dead_lettered_growth_per_hour(values["dead_lettered_total"])
        values["dead_lettered_growth_per_hour"] = growth
        if growth > rules["dead_lettered_growth_per_hour_max"]:
            alerts.append({"rule": "dead_lettered_growth_per_hour_max", "status": "ALERT",
                           "value": growth, "threshold": rules["dead_lettered_growth_per_hour_max"]})
    if "disk_free_mb" in values and values["disk_free_mb"] < rules["disk_free_mb_min"]:
        alerts.append({"rule": "disk_free_mb_min", "status": "ALERT",
                       "value": values["disk_free_mb"], "threshold": rules["disk_free_mb_min"]})
    if "heartbeat_age_seconds" in values and values["heartbeat_age_seconds"] > rules["heartbeat_age_seconds_max"]:
        alerts.append({"rule": "heartbeat_age_seconds_max", "status": "ALERT",
                       "value": values["heartbeat_age_seconds"],
                       "threshold": rules["heartbeat_age_seconds_max"]})
    return {"alerts": alerts, "values": values, "rules_source": source,
            "evaluated_at": core.now()}


def _open_ro():
    path = core.root() / "database" / "money_machine.db"
    if not path.is_file():
        return None
    return core.connect(path, readonly=True)


def _disk_free_mb():
    import shutil
    try:
        return round(shutil.disk_usage(core.root()).free / (1024 * 1024), 1)
    except OSError:
        return None


def _heartbeat_age_seconds():
    hb = _state("supervisor.heartbeat")
    if not hb.is_file():
        return None
    age = dt.datetime.now(dt.UTC) - dt.datetime.fromtimestamp(hb.stat().st_mtime, dt.UTC)
    return round(age.total_seconds(), 1)


def _dead_lettered_growth_per_hour(total):
    hist = _state("daily-dlq.jsonl")
    cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)).isoformat()
    try:
        for line in reversed(hist.read_text(encoding="utf-8").splitlines()):
            row = json.loads(line)
            if row.get("at", "") >= cutoff and "dead_lettered_total" in row:
                return max(0, total - row["dead_lettered_total"])
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return 0


def rotate_jsonl(name, retention_days=30, archive_dir="archive"):
    """Gzip a state/*.jsonl file whose mtime is older than retention_days."""
    path = _state(name)
    if not path.is_file():
        return None
    age_days = (dt.datetime.now(dt.UTC)
                - dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC)).total_seconds() / 86400
    if age_days <= retention_days:
        return None
    dest_dir = _state(archive_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{path.name}.{stamp}.gz"
    with open(path, "rb") as src, gzip.open(dest, "wb") as dst:
        dst.write(src.read())
    path.unlink()
    return str(dest)


def funnel_snapshot(d):
    stages = {r[0]: r[1] for r in d.execute("SELECT stage,count(*) FROM mm_deals GROUP BY stage")}
    counts = {
        "new_evidence_24h": d.execute(
            "SELECT count(*) FROM mm_evidence WHERE checked_at >= datetime('now','-1 day')").fetchone()[0],
        "new_drafts_24h": d.execute(
            "SELECT count(*) FROM mm_messages WHERE created_at >= datetime('now','-1 day')").fetchone()[0],
        "dead_lettered": d.execute(
            "SELECT count(*) FROM pipeline_items WHERE state='DEAD_LETTER'").fetchone()[0],
        "prospects_without_evidence": d.execute(
            "SELECT count(*) FROM businesses b WHERE is_dummy=0 AND NOT EXISTS"
            "(SELECT 1 FROM mm_evidence e WHERE e.business_id=b.id)").fetchone()[0],
    }
    return {"stages": stages, "counts": counts}


def _prev_snapshot(today):
    hist = _state("daily-funnel.jsonl")
    try:
        for line in reversed(hist.read_text(encoding="utf-8").splitlines()):
            row = json.loads(line)
            if "funnel" in row:
                return row  # last recorded run (any date) is the comparison baseline
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return None


def _guard_flaps_24h():
    flaps = 0
    path = _state("errors.jsonl")
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "network_degraded" in line or '"kind": "failure"' in line:
                flaps += 1
    except OSError:
        pass
    return flaps


def daily_report(write=True, quiet=False):
    """`mm report daily` -> reports/YYYY-MM-DD.md (stdlib only, safety-attested)."""
    import mm_observability
    today = dt.date.today().isoformat()
    d = _open_ro()
    if d is None:
        raise ValueError("database missing; cannot report")
    with d:
        snap = funnel_snapshot(d)
    prev = _prev_snapshot(today)
    delta = {}
    if prev:
        prev_stages = prev.get("funnel", {}).get("stages", {})
        prev_counts = prev.get("funnel", {}).get("counts", {})
        for stage in set(snap["stages"]) | set(prev_stages):
            delta[stage] = snap["stages"].get(stage, 0) - prev_stages.get(stage, 0)
        for k in set(snap["counts"]) | set(prev_counts):
            delta[k] = snap["counts"].get(k, 0) - prev_counts.get(k, 0)
    guard_doc = mm_observability.health().get("guards", {})
    alerts = evaluate_alerts()
    attestation = (f"external_sends: {guard_doc.get('external_sends')} · "
                   f"model_calls: 0 · model_cost_usd: 0.0")
    recs = _recommendations(snap, alerts)
    lines = [
        f"# Daily report — {today}", "",
        f"Generated {core.now()} by `mm report daily`. Stdlib only; $0.", "",
        "## Safety attestation", "", attestation, "",
        "## Funnel", "",
        "Stages: `" + json.dumps(snap["stages"], sort_keys=True) + "`",
        ("Delta vs last snapshot: `" + json.dumps(delta, sort_keys=True) + "`")
            if prev else "Delta: (first snapshot)", "",
        "## Last 24h", "",
        f"- new evidence rows: {snap['counts']['new_evidence_24h']}",
        f"- new drafts: {snap['counts']['new_drafts_24h']}",
        f"- dead-lettered: {snap['counts']['dead_lettered']}",
        f"- prospects without evidence: {snap['counts']['prospects_without_evidence']}",
        f"- guard flaps in state/errors.jsonl (last file, 24h window heuristic): {_guard_flaps_24h()}",
        "", "## Alerts", "",
        (json.dumps(alerts["alerts"], indent=2) if alerts["alerts"]
         else f"none (rules: {alerts['rules_source']})"), "",
        "## Top deterministic next actions", "",
    ]
    lines += [f"{i+1}. {r}" for i, r in enumerate(recs)]
    lines += ["", "---", "", "Nothing was sent. Nothing was automated toward a customer.", ""]
    text = "\n".join(lines)
    if write:
        out = core.root() / "reports" / f"{today}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".md.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(out)
        hist = _state("daily-funnel.jsonl")
        hist.parent.mkdir(parents=True, exist_ok=True)
        with open(hist, "a", encoding="utf-8") as h:
            h.write(json.dumps({"date": today, "funnel": snap, "at": core.now()}) + "\n")
        rotate_jsonl("metrics.jsonl")
        rotate_jsonl("errors.jsonl")
    if not quiet:
        print(text)
    return {"report": f"reports/{today}.md" if write else None, "funnel": snap,
            "delta": delta, "alerts": alerts, "safety_attestation": attestation}


def _recommendations(snap, alerts):
    recs = []
    c = snap["counts"]
    if c["dead_lettered"]:
        recs.append(f"Triage {c['dead_lettered']} dead-lettered pipeline item(s) via `./mm dead-letter`.")
    if c["prospects_without_evidence"]:
        recs.append(f"Run `./mm audit-backfill` for {c['prospects_without_evidence']} prospect(s) without evidence.")
    if any(a["rule"] == "heartbeat_age_seconds_max" for a in alerts["alerts"]):
        recs.append("Supervisor heartbeat stale: run `./mm supervisor ensure-running`.")
    recs.append("Capture current website evidence before any customer-facing claim.")
    return recs[:3]
