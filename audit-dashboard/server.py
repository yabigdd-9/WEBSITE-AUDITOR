#!/usr/bin/env python3
"""
HERMES Money Engine — Internal Audit Dashboard (minimal scaffold).

A dependency-light, read-at-runtime dashboard for the audit/health artifacts
already produced by the HERMES Money Engine.

  * No external network calls.
  * Reads local artifacts on every request (live view, not a snapshot).
  * Only third-party dependency: PyYAML (for the .yaml artifacts).
    The HTTP server itself is Python standard library only.

Run:
    python3 audit-dashboard/server.py [port]

Then open the printed URL (default http://127.0.0.1:8755/).

Artifacts read (relative to the repo root = parent of this folder):
    db/master_opportunity_database.json
    db/MASTER_OPPORTUNITY_DATABASE.csv
    approval/APPROVAL_QUEUE.yaml
    state/HERMES_EXECUTION_STATE.yaml
    outputs/*.md
"""

import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "ERROR: PyYAML is required to parse the .yaml artifacts.\n"
        "Install it with:  python3 -m pip install pyyaml\n"
    )
    raise

# --- paths -----------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)  # audit-dashboard/ -> HERMES_MONEY_ENGINE/

DB_JSON = os.path.join(REPO_ROOT, "db", "master_opportunity_database.json")
DB_CSV = os.path.join(REPO_ROOT, "db", "MASTER_OPPORTUNITY_DATABASE.csv")
APPROVAL_YAML = os.path.join(REPO_ROOT, "approval", "APPROVAL_QUEUE.yaml")
STATE_YAML = os.path.join(REPO_ROOT, "state", "HERMES_EXECUTION_STATE.yaml")
OUTPUTS_DIR = os.path.join(REPO_ROOT, "outputs")


# --- readers ----------------------------------------------------------------
def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:  # pragma: no cover - defensive
        return {"_error": str(exc)}


def read_yaml(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:  # pragma: no cover - defensive
        return {"_error": str(exc)}


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def list_output_reports():
    """Return [(filename, abs_path, size_bytes)] for .md reports in outputs/."""
    out = []
    if not os.path.isdir(OUTPUTS_DIR):
        return out
    for name in sorted(os.listdir(OUTPUTS_DIR)):
        if name.lower().endswith(".md"):
            p = os.path.join(OUTPUTS_DIR, name)
            if os.path.isfile(p):
                out.append((name, os.path.abspath(p), os.path.getsize(p)))
    return out


def csv_row_count(path):
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            return sum(1 for _ in csv.reader(fh)) - 1  # minus header
    except FileNotFoundError:
        return None
    except Exception:
        return None


# --- analysis ---------------------------------------------------------------
def analyze_pipeline(db):
    """Counts derived from the master opportunity database JSON."""
    if not isinstance(db, list):
        return None
    total = len(db)
    bands = Counter(d.get("band", "<none>") for d in db)
    categories = Counter((d.get("category") or "<none>") for d in db)
    auto = Counter(d.get("automation_potential", "<none>") for d in db)
    exec_status = Counter(d.get("execution_status", "<none>") for d in db)
    scores = [d.get("total_score") for d in db if isinstance(d.get("total_score"), (int, float))]
    score_avg = round(sum(scores) / len(scores), 1) if scores else None
    return {
        "total": total,
        "bands": bands.most_common(),
        "categories": categories.most_common(10),
        "automation": auto.most_common(),
        "execution_status": exec_status.most_common(),
        "score_avg": score_avg,
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
    }


def analyze_approval(approval):
    """Counts derived from APPROVAL_QUEUE.yaml."""
    if not isinstance(approval, dict):
        return None
    items = approval.get("requires_dion_approval", []) or []
    statuses = Counter(it.get("status", "<none>") for it in items)
    # "blocked / awaiting" == anything not yet resolved by Dion.
    resolved = statuses.get("RESOLVED_BY_DION", 0)
    awaiting = sum(v for k, v in statuses.items() if k != "RESOLVED_BY_DION")
    return {
        "items": items,
        "statuses": statuses.most_common(),
        "total": len(items),
        "awaiting": awaiting,
        "resolved": resolved,
        "policy": approval.get("policy"),
        "blocking_summary": approval.get("blocking_summary"),
        "autonomous": approval.get("autonomous_no_approval_needed", []),
    }


def analyze_state(state):
    """Counts derived from HERMES_EXECUTION_STATE.yaml."""
    if not isinstance(state, dict):
        return None
    portfolio = state.get("portfolio", {}) or {}
    bands = (portfolio.get("bands", {}) or {}) if isinstance(portfolio, dict) else {}
    phases = state.get("phases", {}) or {}
    active_tasks = state.get("active_tasks", []) or []
    completed_tasks = state.get("completed_tasks", []) or []
    return {
        "current_phase": state.get("current_phase"),
        "updated_at": state.get("updated_at"),
        "owner": state.get("owner"),
        "portfolio": portfolio,
        "bands": bands,
        "phases": phases,
        "active_engine": state.get("active_engine"),
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "n_active_tasks": len(active_tasks),
        "n_completed_tasks": len(completed_tasks),
    }


# --- html helpers -----------------------------------------------------------
def esc(s):
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


STATUS_CLASS = {
    "AWAITING_DION": "badge-warn",
    "NOT_READY": "badge-bad",
    "RESOLVED_BY_DION": "badge-ok",
}


def badge(status):
    cls = STATUS_CLASS.get(status, "badge-neutral")
    return f'<span class="badge {cls}">{esc(status)}</span>'


BAND_ORDER = ["EXECUTE_NOW", "VALIDATE_NEXT", "BACKLOG", "HOLD", "KILL"]
BAND_CLASS = {
    "EXECUTE_NOW": "bar-ok",
    "VALIDATE_NEXT": "bar-warn",
    "BACKLOG": "bar-neutral",
    "HOLD": "bar-warn",
    "KILL": "bar-bad",
}


def render_html(model):
    pipe = model["pipeline"]
    appr = model["approval"]
    st = model["state"]
    reports = model["reports"]
    gen = model["generated_at"]
    repo = model["repo_root"]

    # ---- pipeline section ----
    if pipe:
        band_rows = ""
        max_band = max((v for _, v in pipe["bands"]), default=1) or 1
        for b in BAND_ORDER:
            v = dict(pipe["bands"]).get(b, 0)
            cls = BAND_CLASS.get(b, "bar-neutral")
            pct = (v / max_band * 100) if max_band else 0
            band_rows += (
                f'<div class="row"><span class="row-label">{esc(b)}</span>'
                f'<div class="track"><div class="fill {cls}" style="width:{pct:.1f}%"></div></div>'
                f'<span class="row-val">{v}</span></div>'
            )
        cat_rows = "".join(
            f'<li>{esc(k)}: <b>{v}</b></li>' for k, v in pipe["categories"]
        )
        auto_rows = "".join(
            f'<li>{esc(k)}: <b>{v}</b></li>' for k, v in pipe["automation"]
        )
        exec_rows = "".join(
            f'<li>{esc(k)}: <b>{v}</b></li>' for k, v in pipe["execution_status"]
        )
        score_line = (
            f'avg {pipe["score_avg"]} '
            f'(min {pipe["score_min"]} / max {pipe["score_max"]})'
            if pipe.get("score_avg") is not None
            else "n/a"
        )
        pipeline_html = f"""
        <div class="metric-grid">
          <div class="metric"><div class="metric-num">{pipe['total']}</div><div class="metric-lbl">Total opportunities (db json)</div></div>
          <div class="metric"><div class="metric-num">{model['csv_rows'] if model['csv_rows'] is not None else '—'}</div><div class="metric-lbl">Rows in MASTER db CSV</div></div>
          <div class="metric"><div class="metric-num">{score_line}</div><div class="metric-lbl">total_score ({pipe['total']} items)</div></div>
        </div>
        <h3>Band distribution</h3>
        {band_rows}
        <div class="cols">
          <div><h4>Top categories</h4><ul>{cat_rows}</ul></div>
          <div><h4>Automation potential</h4><ul>{auto_rows}</ul></div>
          <div><h4>Execution status</h4><ul>{exec_rows}</ul></div>
        </div>
        """
    else:
        pipeline_html = '<p class="err">master_opportunity_database.json not found or unreadable.</p>'

    # ---- approval section ----
    if appr:
        item_rows = ""
        for it in appr["items"]:
            item_rows += (
                f'<tr><td>{esc(it.get("id"))}</td>'
                f'<td>{esc(it.get("type"))}</td>'
                f'<td>{esc(it.get("engine"))}</td>'
                f"<td>{badge(it.get('status'))}</td>"
                f"<td>{esc(it.get('reason_not_ready') or it.get('ask') or '')}</td></tr>"
            )
        status_pills = "".join(
            f'<span class="pill">{esc(k)}: <b>{v}</b></span>' for k, v in appr["statuses"]
        )
        policy = esc(appr["policy"]) if appr["policy"] else ""
        blocking = esc(appr["blocking_summary"]) if appr["blocking_summary"] else ""
        approval_html = f"""
        <div class="metric-grid">
          <div class="metric"><div class="metric-num">{appr['total']}</div><div class="metric-lbl">Items requiring Dion approval</div></div>
          <div class="metric"><div class="metric-num">{appr['awaiting']}</div><div class="metric-lbl">Awaiting / not ready</div></div>
          <div class="metric"><div class="metric-num">{appr['resolved']}</div><div class="metric-lbl">Resolved by Dion</div></div>
        </div>
        <div class="pills">{status_pills}</div>
        <p class="policy">{policy}</p>
        <table>
          <thead><tr><th>ID</th><th>Type</th><th>Engine</th><th>Status</th><th>Note / Ask</th></tr></thead>
          <tbody>{item_rows}</tbody>
        </table>
        <p class="blocking"><b>Blocking summary:</b> {blocking}</p>
        """
    else:
        approval_html = '<p class="err">approval/APPROVAL_QUEUE.yaml not found or unreadable.</p>'

    # ---- execution state section ----
    if st:
        pf = st.get("portfolio", {}) or {}
        pf_rows = "".join(
            f'<li>{esc(k)}: <b>{v}</b></li>'
            for k, v in pf.items()
            if k != "bands"
        )
        band_rows2 = ""
        bands = st.get("bands", {}) or {}
        max_b = max((v for v in bands.values() if isinstance(v, int)), default=1) or 1
        for b in BAND_ORDER:
            v = bands.get(b, 0)
            cls = BAND_CLASS.get(b, "bar-neutral")
            pct = (v / max_b * 100) if max_b else 0
            band_rows2 += (
                f'<div class="row"><span class="row-label">{esc(b)}</span>'
                f'<div class="track"><div class="fill {cls}" style="width:{pct:.1f}%"></div></div>'
                f'<span class="row-val">{v}</span></div>'
            )
        active_rows = "".join(
            f'<li><b>{esc(t.get("id"))}</b> — {esc(t.get("task"))} '
            f'<span class="tag">[{esc(t.get("status"))}]</span></li>'
            for t in st.get("active_tasks", [])
        )
        exec_html = f"""
        <div class="metric-grid">
          <div class="metric"><div class="metric-num">{esc(st.get('current_phase'))}</div><div class="metric-lbl">Current phase</div></div>
          <div class="metric"><div class="metric-num">{st.get('n_active_tasks')}</div><div class="metric-lbl">Active tasks</div></div>
          <div class="metric"><div class="metric-num">{st.get('n_completed_tasks')}</div><div class="metric-lbl">Completed tasks</div></div>
        </div>
        <p><b>Active engine:</b> {esc(st.get('active_engine'))} &nbsp;·&nbsp; <b>Owner:</b> {esc(st.get('owner'))} &nbsp;·&nbsp; <b>Updated:</b> {esc(st.get('updated_at'))}</p>
        <h3>Portfolio</h3>
        <ul class="inline">{pf_rows}</ul>
        <h3>Band distribution (state yaml)</h3>
        {band_rows2}
        <h3>Active tasks</h3>
        <ul>{active_rows}</ul>
        """
    else:
        exec_html = '<p class="err">state/HERMES_EXECUTION_STATE.yaml not found or unreadable.</p>'

    # ---- output reports section ----
    if reports:
        rep_rows = ""
        for name, abspath, size in reports:
            link = "file://" + abspath
            rep_rows += (
                f'<li><a href="{esc(link)}" target="_blank" rel="noopener">{esc(name)}</a> '
                f'<span class="muted">({size:,} bytes)</span></li>'
            )
        reports_html = f"<ul>{rep_rows}</ul>"
    else:
        reports_html = '<p class="err">No .md reports found in outputs/.</p>'

    # ---- assembly ----
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HERMES Money Engine — Internal Audit Dashboard</title>
<style>
  :root {{ --bg:#0f1419; --panel:#1a2129; --ink:#e6edf3; --muted:#8b98a5; --line:#2b3540;
          --ok:#3fb950; --warn:#d29922; --bad:#f85149; --neutral:#58a6ff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  header {{ padding:20px 28px; border-bottom:1px solid var(--line);
            background:linear-gradient(180deg,#141b22,#0f1419); }}
  header h1 {{ margin:0; font-size:20px; }}
  header .meta {{ color:var(--muted); font-size:12px; margin-top:4px; }}
  main {{ max-width:1080px; margin:0 auto; padding:24px 28px 60px; }}
  section {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
             padding:18px 20px; margin:18px 0; }}
  h2 {{ margin:0 0 12px; font-size:16px; border-left:3px solid var(--neutral); padding-left:10px; }}
  h3 {{ margin:18px 0 8px; font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
  h4 {{ margin:0 0 6px; font-size:13px; color:var(--muted); }}
  .metric-grid {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:8px; }}
  .metric {{ flex:1 1 160px; background:#11171d; border:1px solid var(--line); border-radius:8px; padding:14px; }}
  .metric-num {{ font-size:22px; font-weight:600; }}
  .metric-lbl {{ color:var(--muted); font-size:12px; margin-top:2px; }}
  .row {{ display:flex; align-items:center; gap:10px; margin:6px 0; }}
  .row-label {{ width:130px; font-size:12px; color:var(--muted); }}
  .track {{ flex:1; background:#11171d; border-radius:5px; height:14px; overflow:hidden; }}
  .fill {{ height:100%; }}
  .row-val {{ width:42px; text-align:right; font-variant-numeric:tabular-nums; }}
  .bar-ok {{ background:var(--ok); }} .bar-warn {{ background:var(--warn); }}
  .bar-bad {{ background:var(--bad); }} .bar-neutral {{ background:var(--neutral); }}
  .cols {{ display:flex; gap:24px; flex-wrap:wrap; }}
  .cols > div {{ flex:1 1 200px; }}
  ul {{ margin:6px 0; padding-left:18px; }} li {{ margin:3px 0; }}
  .inline {{ columns:2; }}
  .muted {{ color:var(--muted); }}
  .tag {{ color:var(--warn); font-size:11px; }}
  .pills {{ margin:10px 0; }}
  .pill {{ display:inline-block; background:#11171d; border:1px solid var(--line);
           border-radius:20px; padding:3px 10px; margin:3px 6px 3px 0; font-size:12px; }}
  .policy {{ color:var(--muted); font-style:italic; }}
  .blocking {{ border-top:1px dashed var(--line); padding-top:10px; color:var(--ink); }}
  table {{ width:100%; border-collapse:collapse; margin-top:10px; font-size:13px; }}
  th,td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }}
  .badge-ok {{ background:rgba(63,185,80,.18); color:var(--ok); }}
  .badge-warn {{ background:rgba(210,153,34,.18); color:var(--warn); }}
  .badge-bad {{ background:rgba(248,81,73,.18); color:var(--bad); }}
  .badge-neutral {{ background:#11171d; color:var(--muted); }}
  a {{ color:var(--neutral); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
  .err {{ color:var(--bad); }}
</style>
</head>
<body>
<header>
  <h1>HERMES Money Engine — Internal Audit Dashboard</h1>
  <div class="meta">Generated {esc(gen)} · repo: {esc(repo)} · reads artifacts live on every request</div>
</header>
<main>
  <section>
    <h2>1 · Pipeline Summary <span class="muted">(db/master_opportunity_database.json)</span></h2>
    {pipeline_html}
  </section>
  <section>
    <h2>2 · Approval Queue <span class="muted">(approval/APPROVAL_QUEUE.yaml)</span></h2>
    {approval_html}
  </section>
  <section>
    <h2>3 · Execution State <span class="muted">(state/HERMES_EXECUTION_STATE.yaml)</span></h2>
    {exec_html}
  </section>
  <section>
    <h2>4 · Output Reports <span class="muted">(outputs/*.md)</span></h2>
    {reports_html}
  </section>
</main>
</body>
</html>"""


# --- request handler --------------------------------------------------------
def build_model():
    db = read_json(DB_JSON)
    approval = read_yaml(APPROVAL_YAML)
    state = read_yaml(STATE_YAML)
    return {
        "pipeline": analyze_pipeline(db),
        "approval": analyze_approval(approval),
        "state": analyze_state(state),
        "reports": list_output_reports(),
        "csv_rows": csv_row_count(DB_CSV),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "repo_root": REPO_ROOT,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = render_html(build_model()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"not found")

    def log_message(self, fmt, *args):  # quieter logs
        sys.stderr.write("audit-dashboard: " + (fmt % args) + "\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8755
    host = "127.0.0.1"
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"HERMES Money Engine audit dashboard running at http://{host}:{port}/")
    print(f"Reading artifacts from: {REPO_ROOT}")
    print("Press Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        srv.shutdown()


if __name__ == "__main__":
    main()
