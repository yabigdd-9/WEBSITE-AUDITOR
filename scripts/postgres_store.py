"""Private, bounded Postgres adapter for the existing pipeline state contract.

Runtime never provisions or migrates. A direct/session connection preserves the
writer lock; reservations commit separately and survive queue rollback.
"""
from __future__ import annotations

import copy
import os
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from scripts.pipeline_store import validate, validate_transition

PROJECT_REF = "srymerkhraklwuttzexi"
WRITER_LOCK = 598114901
RESERVATION_LOCK = 598114902
COLLECTIONS = {
    "prospects": ("id", True), "audit_runs": ("audit_id", False),
    "events": ("sequence", False), "business_events": ("sequence", False),
    "discovery_candidates": ("id", True), "discovery_events": ("sequence", False),
    "report_artifacts": ("id", True), "audit_artifact_links": ("sequence", False),
}


def connection_options(dsn):
    from psycopg.conninfo import conninfo_to_dict

    try:
        values = conninfo_to_dict(dsn)
        host, user = values.get("host", ""), values.get("user", "")
        direct = host == f"db.{PROJECT_REF}.supabase.co"
        pooled = bool(re.fullmatch(r"[a-z0-9-]+\.pooler\.supabase\.com", host))
        allowed = {"host", "port", "dbname", "user", "password", "sslmode", "sslrootcert"}
        if (not dsn or not (direct or pooled) or values.get("port", "5432") != "5432"
                or values.get("dbname") != "postgres" or not values.get("password")
                or user != ("moneymachine_runner." + PROJECT_REF if pooled else "moneymachine_runner")
                or values.get("sslmode") != "verify-full" or set(values) - allowed
                or pooled and not user.endswith("." + PROJECT_REF)
                or values.get("sslrootcert", "system") != "system"):
            raise ValueError("Invalid connection")
    except Exception:
        raise ValueError("Configure the selected project's verified TLS direct/session connection privately") from None
    values.update(sslrootcert="system", connect_timeout=10, application_name="wa-private-pipeline")
    return values


def project_rows(state):
    rows = {name: [] for name in COLLECTIONS}
    rows["prospects"] = [(i, p["domain"], p) for i, p in state["prospects"].items()]
    rows["audit_runs"] = [(a["audit_id"], a["prospect_id"], i, a)
                          for i, a in enumerate(state.get("audit_runs", []))]
    rows["events"] = list(enumerate(state["events"]))
    rows["business_events"] = [(i, e["event_id"], e["entity_id"], e)
                               for i, e in enumerate(state.get("business_events", []))]
    rows["discovery_candidates"] = [(i, c["domain"], c.get("prospect_id"), c)
                                    for i, c in state.get("discovery_candidates", {}).items()]
    rows["discovery_events"] = [(i, e["candidate_id"], e)
                                for i, e in enumerate(state.get("discovery_events", []))]
    rows["report_artifacts"] = [(i, a["ciphertext_sha256"], a)
                                for i, a in state.get("report_artifacts", {}).items()]
    rows["audit_artifact_links"] = [(i, a["artifact_id"], a["audit_id"], a)
                                    for i, a in enumerate(state.get("audit_artifact_links", []))]
    metadata = dict(header={k: v for k, v in state.items() if k not in COLLECTIONS},
                    collections=[key for key in COLLECTIONS if key in state])
    return metadata, rows


class PostgresPipelineStore:
    storage_kind = "private Postgres"

    def __init__(self, dsn=None, *, connect=None):
        # Only local tests inject a connector. Runtime always validates target/TLS.
        if connect is None:
            import psycopg

            options = connection_options(dsn or os.environ.get("WA_POSTGRES_DSN", ""))

            def connect():
                return psycopg.connect(**options, autocommit=True)
        self._connector = connect
        self._active_job = None

    @contextmanager
    def connection(self):
        import psycopg

        try:
            with self._connector() as db:
                db.execute("SET statement_timeout='10s'")
                db.execute("SET lock_timeout='1s'")
                db.execute("SET idle_in_transaction_session_timeout='25min'")
                db.execute("SET ROLE moneymachine_worker")
                if db.execute("SELECT version FROM moneymachine.schema_version WHERE singleton=1").fetchone() != (1,):
                    raise ValueError("Reviewed Postgres migration is required")
                yield db
        except psycopg.Error:
            raise ValueError("Private Postgres unavailable; inspect credentials and migration privately") from None

    @staticmethod
    def load(db):
        from psycopg import sql

        row = db.execute("SELECT body FROM moneymachine.metadata WHERE singleton=1").fetchone()
        if row is None:
            return None
        state = copy.deepcopy(row[0]["header"])
        for name in row[0]["collections"]:
            key, keyed = COLLECTIONS[name]
            ordering = "sequence" if name == "audit_runs" else key
            query = sql.SQL("SELECT {},body FROM moneymachine.{} ORDER BY {}").format(
                sql.Identifier(key), sql.Identifier(name), sql.Identifier(ordering))
            records = db.execute(query).fetchall()
            state[name] = dict(records) if keyed else [r[1] for r in records]
        validate(state)
        return state

    @staticmethod
    def save(db, state, previous, job_id):
        from psycopg import sql
        from psycopg.types.json import Jsonb

        validate_transition(previous, state)
        metadata, rows = project_rows(state)
        _, old_rows = project_rows(previous) if previous is not None else (None, {})
        for name, records in rows.items():
            key, keyed = COLLECTIONS[name]
            old = {row[0]: row for row in old_rows.get(name, [])}
            for row in records:
                if old.get(row[0]) == row:
                    continue
                if row[0] in old and not keyed:
                    raise ValueError("Persisted histories are immutable")
                query = sql.SQL("INSERT INTO moneymachine.{} VALUES ({})").format(
                    sql.Identifier(name), sql.SQL(",").join(sql.Placeholder() for _ in row))
                if name in {"prospects", "discovery_candidates"}:
                    query += sql.SQL(" ON CONFLICT ({}) DO UPDATE SET body=EXCLUDED.body").format(sql.Identifier(key))
                    if name == "discovery_candidates":
                        query += sql.SQL(",prospect_id=EXCLUDED.prospect_id")
                db.execute(query, (*row[:-1], Jsonb(row[-1])))
        db.execute(
            "INSERT INTO moneymachine.metadata VALUES(1,%s,%s) ON CONFLICT(singleton) "
            "DO UPDATE SET body=EXCLUDED.body,last_committed_job=EXCLUDED.last_committed_job",
            (Jsonb(metadata), job_id))

    @contextmanager
    def transaction(self, *, bootstrap=False):
        if self._active_job is not None:
            raise ValueError("Nested queue transactions are not supported")
        with self.connection() as db:
            if not db.execute("SELECT pg_try_advisory_lock(%s)", (WRITER_LOCK,)).fetchone()[0]:
                raise ValueError("Another private pipeline writer is active")
            job_id, committed = None, False
            try:
                with db.transaction():
                    previous = self.load(db)
                    if bootstrap:
                        if previous is not None:
                            raise ValueError("Refusing to bootstrap over existing state")
                        from scripts.cloud_prospect_pipeline import empty_state

                        state = empty_state()
                    elif previous is None:
                        raise ValueError("First run requires explicit bootstrap")
                    else:
                        state = copy.deepcopy(previous)
                    marker = db.execute("SELECT last_committed_job FROM moneymachine.metadata WHERE singleton=1").fetchone()
                    job_id = self.start_job(marker[0] if marker else None)
                    self._active_job = (job_id, copy.deepcopy(state))
                    yield state
                    self.save(db, state, previous, job_id)
                committed = True
                self.finish_job(job_id, "succeeded")
            except BaseException:
                if job_id is not None and not committed:
                    self.finish_job(job_id, "failed")
                raise
            finally:
                self._active_job = None
                db.execute("SELECT pg_advisory_unlock(%s)", (WRITER_LOCK,))

    def start_job(self, committed_job):
        identity = uuid.uuid4().hex
        with self.connection() as db, db.transaction():
            if db.execute("SELECT count(*) FROM moneymachine.jobs").fetchone()[0] >= 10000:
                raise ValueError("Archive operational history before continuing")
            db.execute("UPDATE moneymachine.jobs SET status='succeeded',finished=%s WHERE status='running' AND id=%s", (time.time(), committed_job))
            db.execute("UPDATE moneymachine.jobs SET status='interrupted',finished=%s WHERE status='running'", (time.time(),))
            db.execute("INSERT INTO moneymachine.jobs VALUES(%s,%s,NULL,'running')", (identity, time.time()))
        return identity

    def finish_job(self, job_id, status):
        if status not in {"succeeded", "failed"}:
            raise ValueError("Invalid final status")
        with self.connection() as db:
            db.execute("UPDATE moneymachine.jobs SET status=%s,finished=%s WHERE id=%s AND status='running'", (status, time.time(), job_id))

    def reserve_attempt(self, prospect_id, audit_id, *, now, daily_limit):
        if self._active_job is None or type(daily_limit) is not int or not 0 <= daily_limit <= 6:
            raise ValueError("Active queue job and bounded daily limit required")
        if not all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for v in (prospect_id, audit_id)):
            raise ValueError("Hashed prospect and audit references required")
        job_id, baseline = self._active_job
        day = datetime.fromtimestamp(now, timezone.utc).isoformat()[:10]
        with self.connection() as db, db.transaction():
            db.execute("SELECT pg_advisory_xact_lock(%s)", (RESERVATION_LOCK,))
            if db.execute("SELECT status FROM moneymachine.jobs WHERE id=%s", (job_id,)).fetchone() != ("running",):
                raise ValueError("Active queue job required")
            if db.execute("SELECT 1 FROM moneymachine.reservations WHERE job_id=%s AND audit_id=%s", (job_id, audit_id)).fetchone():
                return True
            if self.daily_usage(db, day, baseline) >= daily_limit:
                return False
            if db.execute("SELECT count(*) FROM moneymachine.reservations WHERE job_id=%s", (job_id,)).fetchone()[0] >= 3:
                return False
            rows = db.execute("SELECT audit_id FROM moneymachine.reservations WHERE prospect_id=%s", (prospect_id,)).fetchall()
            known = {a["audit_id"] for a in baseline.get("audit_runs", []) if a["prospect_id"] == prospect_id}
            legacy = max(0, baseline["prospects"].get(prospect_id, {}).get("attempts", 0) - len(known & {r[0] for r in rows}))
            if legacy + len(rows) >= 3:
                return False
            if db.execute("SELECT count(*) FROM moneymachine.reservations").fetchone()[0] >= 10000:
                raise ValueError("Archive reservations before continuing")
            db.execute("INSERT INTO moneymachine.reservations VALUES(%s,%s,%s,%s)", (job_id, audit_id, prospect_id, day))
        return True

    @staticmethod
    def daily_usage(db, day, baseline):
        rows = db.execute("SELECT audit_id FROM moneymachine.reservations WHERE day=%s", (day,)).fetchall()
        known = {a["audit_id"] for a in baseline.get("audit_runs", []) if a["execution_timestamp"][:10] == day}
        count = sum(e.get("action") == "audit" and e.get("timestamp_utc", "")[:10] == day for e in baseline.get("events", []))
        return max(0, count - len(known & {r[0] for r in rows})) + len(rows)

    def read(self):
        with self.connection() as db, db.transaction():
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return self.load(db)

    def prospects(self, *, query="", limit=25, offset=0):
        if (not isinstance(query, str) or len(query) > 253 or type(limit) is not int
                or not 1 <= limit <= 100 or type(offset) is not int or offset < 0):
            raise ValueError("Invalid page parameters")
        with self.connection() as db:
            return [r[0] for r in db.execute("SELECT body FROM moneymachine.prospects WHERE strpos(domain,%s)>0 ORDER BY domain LIMIT %s OFFSET %s", (query.lower(), limit, offset))]

    def operational_summary(self, baseline=None):
        with self.connection() as db, db.transaction():
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return dict(
                jobs=[dict(id=r[0], started=r[1], finished=r[2], status=r[3]) for r in db.execute("SELECT id,started,finished,status FROM moneymachine.jobs ORDER BY started DESC LIMIT 25")],
                reservations=db.execute("SELECT count(*) FROM moneymachine.reservations").fetchone()[0],
                charged_today=self.daily_usage(db, datetime.now(timezone.utc).isoformat()[:10], baseline or {}))

    def backup(self, destination):
        from scripts.postgres_backup import export_private

        export_private(self, destination)

    def restore_empty(self, source):
        from scripts.postgres_backup import restore_empty

        restore_empty(self, source)
