"""Local canonical audit captures, separate from stage signals and verified claims.

Status and recovery preview are read-only. Recovery only anchors existing static
toolkit reports; it never scans, changes stages, approves claims, or sends.
"""
import contextlib
import datetime as dt
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import mm_core as core

from auditor_toolkit.models import SCHEMA_VERSION

RULE_VERSION = "evidence-bridge-v1"
STATIC_CHECKS = (
    "fetch", "page", "schema", "headers", "technology", "js_vulnerabilities",
    "structured_validation", "hreflang", "language", "images", "social_meta",
    "hygiene", "ux",
)
MAX_REPORT_BYTES = 8 * 1024 * 1024
_ANCHOR_COLUMNS = {
    "id", "business_id", "run_id", "report_path", "report_hash", "captured_at",
    "registered_at", "rule_version",
}
_DDL = (
    """CREATE TABLE IF NOT EXISTS mm_audit_evidence(
        id INTEGER PRIMARY KEY,
        business_id INTEGER NOT NULL REFERENCES businesses(id),
        run_id TEXT NOT NULL,
        report_path TEXT NOT NULL,
        report_hash TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        registered_at TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        UNIQUE(business_id,run_id))""",
    """CREATE TRIGGER IF NOT EXISTS mm_audit_evidence_no_update
        BEFORE UPDATE ON mm_audit_evidence BEGIN
        SELECT RAISE(ABORT,'canonical audit evidence is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS mm_audit_evidence_no_delete
        BEFORE DELETE ON mm_audit_evidence BEGIN
        SELECT RAISE(ABORT,'canonical audit evidence is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS mm_audit_evidence_no_replace
        BEFORE INSERT ON mm_audit_evidence WHEN EXISTS(
          SELECT 1 FROM mm_audit_evidence WHERE id=NEW.id OR
          (business_id=NEW.business_id AND run_id=NEW.run_id)) BEGIN
        SELECT RAISE(ABORT,'canonical audit evidence is append-only'); END""",
)


def _columns(d, table):
    return {row[1] for row in d.execute(f"PRAGMA table_info({table})")}


class EvidenceSchemaError(ValueError):
    """An existing evidence source cannot safely be read with this schema."""


def _schema_columns(d, table, required):
    columns = _columns(d, table)
    if columns and not required <= columns:
        missing = ", ".join(sorted(required - columns))
        raise EvidenceSchemaError(f"incompatible evidence schema: {table} missing {missing}")
    return columns


def _check_schema(d):
    if not _schema_columns(d, "businesses", {"id", "public_website"}):
        raise EvidenceSchemaError("incompatible evidence schema: businesses missing")
    for table, required in (
        ("pipeline_items", {"business_id", "state"}),
        ("mm_deals", {"business_id", "stage"}),
        ("mm_holds", {"business_id"}),
        ("contacts", {"business_id"}),
        ("mm_contact_evidence", {"business_id"}),
        ("mm_suppression", {"address"}),
        ("mm_evidence", {"business_id"}),
        ("mm_audit_evidence", _ANCHOR_COLUMNS),
    ):
        _schema_columns(d, table, required)
    _event_columns(d)


def _event_columns(d):
    columns = _columns(d, "pipeline_events")
    required = {"id", "business_id", "to_state", "evidence"}
    if not columns or required <= columns:
        return columns
    legacy = {"id", "business_id", "stage", "event_at", "detail"}
    if legacy <= columns and not {"to_state", "evidence"} & columns:
        # The original event ledger has no canonical report projection. Keep
        # it readable without performing the pipeline's separate migration.
        return set()
    return _schema_columns(d, "pipeline_events", required)


def exclusion_reason(d, bid):
    """Check every existing terminal/hold source before any capture or write."""
    row = d.execute("SELECT * FROM businesses WHERE id=?", (bid,)).fetchone()
    if row is None:
        return "business missing"
    business = dict(row)
    if business.get("is_dummy"):
        return "dummy business"
    if business.get("suppression_reason"):
        return "business suppressed"
    if str(business.get("current_status") or "").upper() in {"REJECTED", "SUPPRESSED"}:
        return "business rejected or suppressed"
    for table, column in (("pipeline_items", "state"), ("mm_deals", "stage")):
        if _schema_columns(d, table, {"business_id", column}) and d.execute(
            f"SELECT 1 FROM {table} WHERE business_id=? "
            f"AND upper({column}) IN ('REJECTED','SUPPRESSED')", (bid,),
        ).fetchone():
            return "terminal rejected or suppressed business"
    if _schema_columns(d, "mm_holds", {"business_id"}) and d.execute(
        "SELECT 1 FROM mm_holds WHERE business_id=?", (bid,),
    ).fetchone():
        return "unresolved legacy hold"
    for table, flag, predicate in (
        ("contacts", "do_not_contact", "do_not_contact=1"),
        ("mm_contact_evidence", "unsubscribe_state", "lower(unsubscribe_state)='unsubscribed'"),
    ):
        if flag in _schema_columns(d, table, {"business_id"}) and d.execute(
            f"SELECT 1 FROM {table} WHERE business_id=? AND {predicate}", (bid,),
        ).fetchone():
            return "business has suppressed contact evidence"
    if _schema_columns(d, "mm_suppression", {"address"}):
        for table, address_column in (("contacts", "address_or_channel"), ("mm_contact_evidence", "recipient")):
            if address_column in _schema_columns(d, table, {"business_id"}) and d.execute(
                f"SELECT 1 FROM {table} c JOIN mm_suppression s "
                f"ON lower(trim(c.{address_column}))=lower(trim(s.address)) WHERE c.business_id=?", (bid,),
            ).fetchone():
                return "business has a suppressed contact address"
    return None


def _root(toolkit_root):
    return Path(toolkit_root or core.root() / "outputs" / "toolkit").resolve()


def _site_key(url):
    host = core.public_url(url)
    parsed = urlsplit(url)
    return host, parsed.path.rstrip("/") or "/", parsed.query


def validate_report(d, bid, report_path, toolkit_root=None,
                    expected_run_id=None, expected_hash=None):
    """Validate a saved static report without creating history or refreshing time."""
    result = {"status": "INVALID", "reason": "invalid canonical report"}
    try:
        root = _root(toolkit_root)
        path = Path(report_path).resolve()
        if not path.is_relative_to(root) or path.name != "report.json":
            raise ValueError("report outside canonical toolkit run directory")
        if not path.is_file():
            return {"status": "MISSING", "reason": "canonical report missing"}
        if not 0 < path.stat().st_size <= MAX_REPORT_BYTES:
            raise ValueError("canonical report empty or too large")
        raw = path.read_bytes()
        report_hash = core.sha(raw)
        if expected_hash is not None and report_hash != expected_hash:
            raise ValueError("canonical report hash mismatch")
        report = json.loads(raw)
        if not isinstance(report, dict):
            raise ValueError("canonical report must be an object")
        run_id = report.get("run_id")
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
            raise ValueError("canonical run ID invalid")
        if path != root / run_id / "report.json":
            raise ValueError("canonical run ID/path mismatch")
        if expected_run_id is not None and run_id != expected_run_id:
            raise ValueError("canonical event/run ID mismatch")
        if report.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported canonical report schema")
        if report.get("profile") != "static":
            raise ValueError("deterministic static report required")
        b = d.execute("SELECT public_website FROM businesses WHERE id=?", (bid,)).fetchone()
        if b is None or _site_key(report.get("url")) != _site_key(b[0]):
            raise ValueError("canonical report belongs to a different website")
        captured = core.timestamp(report.get("timestamp"))
        age = dt.datetime.now(core.UTC) - captured
        if age < dt.timedelta(0):
            raise ValueError("canonical report is future-dated")
        result.update(report=report, report_path=str(path), report_hash=report_hash,
                      run_id=run_id, captured_at=report["timestamp"])
        checks = report.get("checks")
        if not isinstance(checks, dict) or any(
            not isinstance(value, dict) or not isinstance(value.get("required"), bool)
            for value in checks.values()
        ):
            raise ValueError("canonical check coverage invalid")
        if report.get("status") != "complete" or any(
            name not in checks or checks[name].get("required") is not True
            or checks[name].get("status") != "ok" for name in STATIC_CHECKS
        ) or any(v["required"] and v.get("status") != "ok" for v in checks.values()):
            return dict(result, status="PARTIAL", reason="required static audit checks incomplete")
        required = sum(value["required"] for value in checks.values())
        coverage = report.get("coverage")
        if coverage is not None and coverage != {"required": required, "passed": required}:
            raise ValueError("canonical coverage totals mismatch")
        defects = report.get("defects")
        if not isinstance(defects, list) or any(not isinstance(item, dict) for item in defects):
            raise ValueError("canonical findings must be an array of objects")
        observed = (report.get("evidence") or {}).get("fetch")
        if not isinstance(observed, dict) or observed.get("mode") != "static":
            raise ValueError("canonical fetch observation missing")
        observed_at = core.timestamp(observed.get("observed_at"))
        observed_age = dt.datetime.now(core.UTC) - observed_at
        if observed_age < dt.timedelta(0):
            raise ValueError("canonical source observation is future-dated")
        response_status = (observed.get("data") or {}).get("status_code")
        if isinstance(response_status, bool) or not isinstance(response_status, int) or not 200 <= response_status < 400:
            raise ValueError("canonical source HTTP result invalid")
        artifacts, manifest = report.get("artifacts"), report.get("manifest")
        if not isinstance(artifacts, dict) or not isinstance(manifest, dict):
            raise ValueError("canonical artifact manifest missing")
        if "html" not in artifacts or set(manifest) != set(artifacts) - {"json"}:
            raise ValueError("canonical artifact manifest coverage mismatch")
        if Path(artifacts.get("json", "")).resolve() != path:
            raise ValueError("declared canonical JSON path mismatch")
        for key, meta in manifest.items():
            artifact = Path(artifacts[key]).resolve()
            if not artifact.is_relative_to(path.parent) or not isinstance(meta, dict):
                raise ValueError("artifact outside canonical run directory")
            if Path(meta.get("path", "")).resolve() != artifact:
                raise ValueError("canonical manifest path mismatch")
            if not artifact.is_file() or artifact.stat().st_size != meta.get("size"):
                raise ValueError("canonical artifact missing or size mismatch")
            if core.sha(artifact.read_bytes()) != meta.get("sha256"):
                raise ValueError("canonical artifact hash mismatch")
        if age > dt.timedelta(days=7):
            return dict(result, status="STALE", reason="canonical report older than seven days")
        if observed_age > dt.timedelta(days=7):
            return dict(result, status="STALE", reason="canonical source observation older than seven days")
        return dict(result, status="CURRENT", reason="current complete static audit capture")
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RuntimeError) as exc:
        return dict(result, status="INVALID", reason=str(exc)[:240])


def register_audit(d, bid, report_path, toolkit_root=None, expected_run_id=None):
    """Anchor validated bytes atomically; never mutate legacy claims or stages."""
    reason = exclusion_reason(d, bid)
    if reason:
        raise ValueError(reason)
    _check_schema(d)
    check = validate_report(d, bid, report_path, toolkit_root, expected_run_id)
    if check["status"] != "CURRENT":
        raise ValueError(check["status"] + ": " + check["reason"])
    d.execute("SAVEPOINT evidence_bridge_register")
    try:
        # Eligibility and the write share the same SQLite snapshot. Suppression
        # that arrived while reading artifacts must prevent even schema writes.
        reason = exclusion_reason(d, bid)
        if reason:
            raise ValueError(reason)
        _check_schema(d)
        for statement in _DDL:
            d.execute(statement)
        previous = d.execute(
            "SELECT report_hash FROM mm_audit_evidence WHERE business_id=? AND run_id=?",
            (bid, check["run_id"]),
        ).fetchone()
        if previous and previous[0] != check["report_hash"]:
            raise ValueError("registered canonical report changed; new audit run required")
        recorded = previous is None
        if recorded:
            d.execute(
                "INSERT INTO mm_audit_evidence(business_id,run_id,report_path,report_hash,"
                "captured_at,registered_at,rule_version) VALUES(?,?,?,?,?,?,?)",
                (bid, check["run_id"], check["report_path"], check["report_hash"],
                 check["captured_at"], core.now(), RULE_VERSION),
            )
        d.execute("RELEASE evidence_bridge_register")
    except Exception:
        d.execute("ROLLBACK TO evidence_bridge_register")
        d.execute("RELEASE evidence_bridge_register")
        raise
    return {key: check[key] for key in ("run_id", "report_path", "report_hash", "captured_at")} | {
        "recorded": recorded, "independently_verified": False,
        "claim_status": "unverified", "rule_version": RULE_VERSION,
    }


def _event_evidence(row):
    try:
        evidence = json.loads(row["evidence"])
    except (TypeError, ValueError):
        evidence = {}
    evidence = evidence if isinstance(evidence, dict) else {}
    return dict(evidence, event_at=dict(row).get("event_at"))


def _events(d, bid):
    if not _event_columns(d):
        return []
    return [_event_evidence(row) for row in d.execute(
        "SELECT * FROM pipeline_events WHERE business_id=? AND to_state='AUDITED' "
        "AND evidence IS NOT NULL ORDER BY id DESC", (bid,),
    )]


def _event(d, bid):
    events = _events(d, bid)
    return events[0] if events else None


def _history_site_key(url):
    try:
        return json.dumps(_site_key(url), separators=(",", ":"))
    except (ValueError, TypeError, AttributeError):
        return None


def _history_capture_time(value):
    try:
        return core.timestamp(value).timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def _history_candidate(d, bid, toolkit_root):
    # Read old toolkit history without invoking History (which initializes it).
    history = _root(toolkit_root) / "history.sqlite3"
    if not history.is_file():
        return None
    b = d.execute("SELECT public_website FROM businesses WHERE id=?", (bid,)).fetchone()
    try:
        site = _history_site_key(b[0])
        with contextlib.closing(sqlite3.connect(history.as_uri() + "?mode=ro", uri=True)) as h:
            if not _schema_columns(h, "runs", {"id", "url", "timestamp"}):
                raise EvidenceSchemaError("incompatible evidence history schema: runs missing")
            if h.execute("PRAGMA user_version").fetchone()[0] > 1:
                raise EvidenceSchemaError("unsupported evidence history schema version")
            h.create_function("evidence_site_key", 1, _history_site_key, deterministic=True)
            h.create_function("evidence_capture_time", 1, _history_capture_time, deterministic=True)
            row = h.execute(
                "SELECT id,timestamp FROM runs WHERE evidence_site_key(url)=? "
                # An unorderable exact-site row cannot silently fall behind a
                # healthy older capture. Offset and fractional timestamps use
                # the same UTC parser as report validation.
                "ORDER BY (evidence_capture_time(timestamp) IS NOT NULL),"
                "evidence_capture_time(timestamp) DESC,id DESC LIMIT 1", (site,),
            ).fetchone()
            if row:
                run_id, captured_at = row
                if _history_capture_time(captured_at) is None:
                    raise EvidenceSchemaError("canonical history candidate timestamp invalid")
                return {"run_id": run_id, "captured_at": captured_at,
                        "history_timestamp": captured_at,
                        "report_path": str(_root(toolkit_root) / run_id / "report.json")}
    except sqlite3.Error as exc:
        raise EvidenceSchemaError("unreadable evidence history: " + str(exc)) from exc
    except (ValueError, TypeError, AttributeError) as exc:
        if isinstance(exc, EvidenceSchemaError):
            raise
        raise EvidenceSchemaError("invalid evidence history candidate: " + str(exc)) from exc
    return None


def _anchor_for_run(d, bid, run_id):
    if not _schema_columns(d, "mm_audit_evidence", _ANCHOR_COLUMNS):
        return None
    row = d.execute(
        "SELECT * FROM mm_audit_evidence WHERE business_id=? AND run_id=?", (bid, run_id),
    ).fetchone()
    return dict(row) if row else None


def _candidate(d, bid, toolkit_root):
    linked = None
    if _schema_columns(d, "mm_audit_evidence", _ANCHOR_COLUMNS):
        row = d.execute(
            "SELECT * FROM mm_audit_evidence WHERE business_id=? "
            "ORDER BY julianday(captured_at) DESC,id DESC LIMIT 1", (bid,),
        ).fetchone()
        linked = dict(row) if row else None
    history = _history_candidate(d, bid, toolkit_root)
    candidate = linked or history
    try:
        if linked and history and history["run_id"] != linked["run_id"]:
            if core.timestamp(history["captured_at"]) > core.timestamp(linked["captured_at"]):
                candidate = history
        for event in _events(d, bid):
            if event.get("audit_engine") != "auditor_toolkit":
                continue
            if candidate and event.get("run_id") == candidate["run_id"]:
                continue
            # Capture time determines supersession. A delayed stage event for
            # an older run cannot hide a newer incomplete canonical event.
            anchor = _anchor_for_run(d, bid, event.get("run_id"))
            expected_hash = anchor["report_hash"] if anchor else event.get("report_hash")
            checked = validate_report(d, bid, event.get("report_path"), toolkit_root,
                                      event.get("run_id"), expected_hash)
            event_time = core.timestamp(checked.get("captured_at") or
                                        (anchor or {}).get("captured_at") or event.get("event_at"))
            if candidate is None or event_time > core.timestamp(candidate["captured_at"]):
                candidate = dict(event, captured_at=event_time.isoformat())
                if anchor:
                    candidate.update(report_hash=anchor["report_hash"], registered_at=anchor["registered_at"])
        return candidate or _event(d, bid)
    except (TypeError, ValueError, AttributeError):
        return {"invalid_reason": "canonical candidate timestamp invalid"}


def audit_evidence_status(d, bid, toolkit_root=None):
    result = {"business_id": bid, "status": "MISSING", "complete": False,
              "independently_verified": False, "claim_status": "unverified",
              "legacy_observations": 0, "stage_signal": False,
              "reason": "no canonical audit capture", "rule_version": RULE_VERSION}
    try:
        _check_schema(d)
        if _columns(d, "mm_evidence"):
            result["legacy_observations"] = d.execute(
                "SELECT count(*) FROM mm_evidence WHERE business_id=?", (bid,),
            ).fetchone()[0]
        result["stage_signal"] = bool(_event(d, bid))
        reason = exclusion_reason(d, bid)
        if reason:
            return dict(result, status="EXCLUDED", reason=reason)
        candidate = _candidate(d, bid, toolkit_root)
    except (EvidenceSchemaError, sqlite3.Error) as exc:
        return dict(result, status="INVALID", schema_valid=False, reason=str(exc)[:240])
    if not candidate:
        return result
    if candidate.get("invalid_reason"):
        return dict(result, status="INVALID", reason=candidate["invalid_reason"])
    if not candidate.get("report_path") or not candidate.get("run_id"):
        return dict(result, reason="stage signal lacks canonical run ID/report path")
    if "event_at" in candidate and candidate.get("audit_engine") != "auditor_toolkit":
        return dict(result, status="INVALID", reason="stage signal is not a canonical toolkit audit")
    check = validate_report(d, bid, candidate["report_path"], toolkit_root,
                            candidate["run_id"], candidate.get("report_hash"))
    if candidate.get("history_timestamp") and check.get("captured_at") and check["captured_at"] != candidate["history_timestamp"]:
        check.update(status="INVALID", reason="canonical report/history timestamp mismatch")
    status = check["status"]
    if status == "CURRENT" and not candidate.get("registered_at"):
        status = "RECOVERABLE"
    result.update({key: value for key, value in check.items() if key != "report"})
    return dict(result, status=status, complete=status == "CURRENT")


def audit_evidence_summary(d, toolkit_root=None):
    dummy = "coalesce(is_dummy,0)=0" if "is_dummy" in _columns(d, "businesses") else "1=1"
    statuses = Counter(audit_evidence_status(d, row[0], toolkit_root)["status"] for row in d.execute(
        f"SELECT id FROM businesses WHERE {dummy} ORDER BY id",
    ))
    return {"prospects_assessed": sum(statuses.values()), "status_counts": dict(sorted(statuses.items())),
            "eligible_without_current_evidence": sum(statuses.values()) - statuses["CURRENT"] - statuses["EXCLUDED"],
            "excluded": statuses["EXCLUDED"], "independently_verified": False,
            "rule_version": RULE_VERSION}


def recover_evidence(d, ids=None, apply=False, toolkit_root=None, report_path=None):
    """Preview by default; apply requires explicit IDs and revalidates each report."""
    if apply and not ids:
        raise ValueError("recovery apply requires explicit business IDs")
    if report_path is not None and (not ids or len(set(ids)) != 1):
        raise ValueError("an explicit report requires exactly one business ID")
    if ids is None:
        dummy = "coalesce(is_dummy,0)=0" if "is_dummy" in _columns(d, "businesses") else "1=1"
        ids = [row[0] for row in d.execute(f"SELECT id FROM businesses WHERE {dummy} ORDER BY id")]
    results = []
    for bid in sorted(set(ids)):
        status = audit_evidence_status(d, bid, toolkit_root)
        anchored_noop = False
        if report_path is not None and status["status"] != "EXCLUDED" and status.get("schema_valid") is not False:
            check = validate_report(d, bid, report_path, toolkit_root)
            if check["status"] == "CURRENT":
                anchor = _anchor_for_run(d, bid, check["run_id"])
                if anchor and check["report_hash"] != anchor["report_hash"]:
                    check.update(status="INVALID", reason="registered canonical report changed; new audit run required")
                elif anchor:
                    # An unchanged existing anchor is a no-op in both modes.
                    # Preserve the latest-capture status if this explicit run
                    # has since been superseded by a failed canonical capture.
                    anchored_noop = True
                else:
                    check.update(status="RECOVERABLE")
            if not anchored_noop:
                status.update({key: value for key, value in check.items() if key != "report"})
                status["complete"] = False
        status["recorded"] = False
        if apply and not anchored_noop and status["status"] in {"RECOVERABLE", "CURRENT"}:
            try:
                status.update(register_audit(d, bid, status["report_path"], toolkit_root, status["run_id"]))
                registered = status["recorded"]
                status.update(audit_evidence_status(d, bid, toolkit_root), recorded=registered)
            except ValueError as exc:
                status.update(status="INVALID", complete=False, reason=str(exc))
        results.append(status)
    return {"apply": apply, "results": results, "recorded": sum(row["recorded"] for row in results),
            "model_calls": 0, "paid_api_calls": 0, "external_sends": 0,
            "stage_changes": 0, "claim_verifications": 0, "rule_version": RULE_VERSION}
