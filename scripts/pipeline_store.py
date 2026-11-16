"""Private single-owner SQLite persistence for the existing bounded queue.

Never upload this plaintext database as an Actions artifact. A trusted durable
filesystem is required; this module does not provision a cloud service.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from scripts.review_ledger import _is_safe_db_location

VERSION = 2
MAX_BYTES = 5_000_000
SCHEMA = (
    "CREATE TABLE metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
    "body TEXT NOT NULL CHECK(json_valid(body)))",
    "CREATE TABLE audit_runs (audit_id TEXT PRIMARY KEY, "
    "prospect_id TEXT NOT NULL REFERENCES prospects(id), "
    "body TEXT NOT NULL CHECK(json_valid(body)))",
    "CREATE TABLE prospects (id TEXT PRIMARY KEY, domain TEXT NOT NULL UNIQUE, "
    "body TEXT NOT NULL CHECK(json_valid(body)))",
    "CREATE TABLE system_events (sequence INTEGER PRIMARY KEY, "
    "body TEXT NOT NULL CHECK(json_valid(body)))",
    "CREATE TABLE business_events (sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, "
    "prospect_id TEXT NOT NULL REFERENCES prospects(id), "
    "body TEXT NOT NULL CHECK(json_valid(body)))",
)
DISCOVERY_SCHEMA = (
    "CREATE TABLE discovery_candidates (id TEXT PRIMARY KEY, domain TEXT NOT NULL UNIQUE, "
    "prospect_id TEXT REFERENCES prospects(id), body TEXT NOT NULL CHECK(json_valid(body)))",
    "CREATE TABLE discovery_events (sequence INTEGER PRIMARY KEY, "
    "candidate_id TEXT NOT NULL REFERENCES discovery_candidates(id), "
    "body TEXT NOT NULL CHECK(json_valid(body)))",
)


def validate(state):
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != 1
        or not isinstance(state.get("prospects"), dict)
        or not isinstance(state.get("events"), list)
        or not isinstance(state.get("business_events", []), list)
        or len(state["prospects"]) > 100
        or len(state["events"]) > 10000
        or len(state.get("business_events", [])) > 10000
        or not isinstance(state.get("audit_runs", []), list)
        or len(state.get("audit_runs", [])) > 10000
        or not isinstance(state.get("discovery_candidates", {}), dict)
        or len(state.get("discovery_candidates", {})) > 100
        or not isinstance(state.get("discovery_events", []), list)
        or len(state.get("discovery_events", [])) > 10000
        or ("discovery_candidates" in state) != ("discovery_events" in state)
        or any(k.startswith("_store_") for k in state)
    ):
        raise ValueError("Invalid bounded pipeline state")
    for records in (state.get("discovery_candidates", {}), state["prospects"]):
        domains = set()
        for identity, prospect in records.items():
            domain = prospect.get("domain")
            if (
                not isinstance(domain, str)
                or domain != domain.lower().rstrip(".")
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", domain)
                or "." not in domain
                or domain in domains
                or hashlib.sha256(domain.encode()).hexdigest() != identity
            ):
                raise ValueError("Invalid canonical prospect identity")
            domains.add(domain)
    raw = json.dumps(state, sort_keys=True, allow_nan=False)
    if len(raw.encode()) > MAX_BYTES:
        raise ValueError("Archive pipeline history before continuing")
    return raw


class PipelineStore:
    def __init__(self, path: Path):
        self.path = _is_safe_db_location(path)

    def _connect(self):
        # Repeat validation for every access, including backups and reopen.
        _is_safe_db_location(self.path)
        if not self.path.exists():
            fd = os.open(
                self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.close(fd)
        db = sqlite3.connect(self.path, timeout=1)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                # Refuse a legacy MoneyMachine/History/review ledger DB.
                if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError("Use a separate pipeline database")
                for statement in (*SCHEMA, *DISCOVERY_SCHEMA):
                    db.execute(statement)
                db.execute(f"PRAGMA user_version={VERSION}")
            elif version == 1:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"metadata", "prospects", "audit_runs", "system_events", "business_events"} <= tables:
                    raise ValueError("Unrecognized version 1 database")
                for statement in DISCOVERY_SCHEMA:
                    db.execute(statement)
                db.execute(f"PRAGMA user_version={VERSION}")
            elif version != VERSION:
                raise ValueError("Unsupported pipeline schema; migration required")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database integrity check failed")
            db.commit()
            return db
        except BaseException:
            db.rollback()
            db.close()
            raise

    @staticmethod
    def _load(db):
        row = db.execute("SELECT body FROM metadata WHERE singleton=1").fetchone()
        if row is None:
            return None
        state = json.loads(row[0])
        state["prospects"] = {
            identity: json.loads(body)
            for identity, body in db.execute("SELECT id,body FROM prospects ORDER BY rowid")
        }
        state["events"] = [
            json.loads(row[0])
            for row in db.execute("SELECT body FROM system_events ORDER BY sequence")
        ]
        if state.pop("_store_has_business_events", False):
            state["business_events"] = [
                json.loads(row[0])
                for row in db.execute("SELECT body FROM business_events ORDER BY sequence")
            ]
        if state.pop("_store_has_audit_runs", False):
            state["audit_runs"] = [
                json.loads(row[0])
                for row in db.execute("SELECT body FROM audit_runs ORDER BY rowid")
            ]
        if state.pop("_store_has_discovery", False):
            state["discovery_candidates"] = {
                identity: json.loads(body) for identity, body in db.execute(
                    "SELECT id,body FROM discovery_candidates ORDER BY rowid"
                )
            }
            state["discovery_events"] = [
                json.loads(row[0]) for row in db.execute(
                    "SELECT body FROM discovery_events ORDER BY sequence"
                )
            ]
        validate(state)
        return state

    @staticmethod
    def _save(db, state):
        validate(state)
        previous = PipelineStore._load(db)
        if previous is not None:
            for key in ("events", "business_events", "audit_runs", "discovery_events"):
                prior = previous.get(key, [])
                if state.get(key, [])[:len(prior)] != prior:
                    raise ValueError("Persisted history is append-only; use explicit backup recovery")
            for identity, prospect in previous["prospects"].items():
                current = state["prospects"].get(identity)
                if current is None or current["domain"] != prospect["domain"]:
                    raise ValueError("Prospect deletion/identity change requires a retention migration")
                if prospect.get("status") == "suppressed" and current.get("status") != "suppressed":
                    raise ValueError("Suppression cannot be cleared by a worker")
            for identity, candidate in previous.get("discovery_candidates", {}).items():
                current = state.get("discovery_candidates", {}).get(identity)
                if (
                    current is None or current["domain"] != candidate["domain"]
                    or current["first_seen"] != candidate["first_seen"]
                    or any(s not in current["sources"] for s in candidate["sources"])
                ):
                    raise ValueError("Discovery provenance cannot be discarded by a worker")
        metadata = {
            k: v for k, v in state.items()
            if k not in {"prospects", "events", "business_events", "audit_runs",
                         "discovery_candidates", "discovery_events"}
        }
        metadata["_store_has_business_events"] = "business_events" in state
        metadata["_store_has_audit_runs"] = "audit_runs" in state
        metadata["_store_has_discovery"] = "discovery_candidates" in state
        # All replacement writes share the caller's transaction. A failed FK,
        # constraint or process interruption preserves the previous full state.
        for table in ("discovery_events", "discovery_candidates", "business_events", "audit_runs",
                      "system_events", "prospects", "metadata"):
            db.execute(f"DELETE FROM {table}")
        db.execute("INSERT INTO metadata VALUES (1,?)", (json.dumps(metadata),))
        db.executemany(
            "INSERT INTO prospects VALUES (?,?,?)",
            [(i, p["domain"], json.dumps(p)) for i, p in state["prospects"].items()],
        )
        db.executemany(
            "INSERT INTO discovery_candidates VALUES (?,?,?,?)",
            [(i, c["domain"], c.get("prospect_id"), json.dumps(c))
             for i, c in state.get("discovery_candidates", {}).items()],
        )
        db.executemany(
            "INSERT INTO discovery_events VALUES (?,?,?)",
            [(i, e["candidate_id"], json.dumps(e))
             for i, e in enumerate(state.get("discovery_events", []))],
        )
        db.executemany(
            "INSERT INTO audit_runs VALUES (?,?,?)",
            [(a["audit_id"], a["prospect_id"], json.dumps(a)) for a in state.get("audit_runs", [])],
        )
        db.executemany(
            "INSERT INTO system_events VALUES (?,?)",
            [(i, json.dumps(e)) for i, e in enumerate(state["events"])],
        )
        db.executemany(
            "INSERT INTO business_events VALUES (?,?,?,?)",
            [
                (i, e["event_id"], e["entity_id"], json.dumps(e))
                for i, e in enumerate(state.get("business_events", []))
            ],
        )

    @contextmanager
    def transaction(self, *, bootstrap=False):
        """Hold a single writer lock across selection, audit and state commit.

        Competing workers fail before performing requests. Crash rolls back the
        transaction; no claim of exactly-once HTTP fetching is made.
        """
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            state = self._load(db)
            if bootstrap:
                if state is not None:
                    raise ValueError("Refusing to bootstrap over existing state")
                from scripts.cloud_prospect_pipeline import empty_state

                state = empty_state()
            elif state is None:
                raise ValueError("First run requires explicit bootstrap")
            yield state
            self._save(db, state)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def read(self):
        db = self._connect()
        try:
            # A consistent read snapshot across all tables.
            db.execute("BEGIN")
            return self._load(db)
        finally:
            db.close()

    def prospects(self, *, query="", limit=25, offset=0):
        """Bounded pagination for future authenticated owner-facing callers."""
        if (
            not isinstance(query, str) or len(query) > 253
            or type(limit) is not int or not 1 <= limit <= 100
            or type(offset) is not int or offset < 0
        ):
            raise ValueError("Invalid page parameters")
        db = self._connect()
        try:
            # instr treats user % and _ as literal text, never SQL patterns.
            return [
                json.loads(row[0]) for row in db.execute(
                    "SELECT body FROM prospects WHERE instr(domain,?)>0 "
                    "ORDER BY domain LIMIT ? OFFSET ?", (query.lower(), limit, offset),
                )
            ]
        finally:
            db.close()

    def backup(self, destination: Path):
        """SQLite online backup, private new file only; no remote upload."""
        target = _is_safe_db_location(destination)
        if target == self.path:
            raise ValueError("Backup must use a separate new file")
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        source = None
        output = None
        try:
            source = self._connect()
            output = sqlite3.connect(target)
            source.backup(output)
            if output.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup failed integrity validation")
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            if output is not None:
                output.close()
            if source is not None:
                source.close()
