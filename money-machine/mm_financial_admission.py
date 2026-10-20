"""Shared pre-dispatch accounting for explicitly reviewed, included model calls.

No configuration is created or enabled by importing this module. The shared Git
directory owns policy and ledger identity, independent of MM_ROOT and worktrees.
CLI agents are deliberately unsupported: their internal request count is unknown.
"""

import hashlib
import json
import math
import os
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path


class AdmissionError(RuntimeError):
    """No inference may be dispatched under the available evidence."""


class AdmissionStoppedError(AdmissionError):
    """An uncertain/billable outcome requires independent operator review."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AdmissionError("Duplicate financial-policy field")
        result[key] = value
    return result


def _digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def control_directory(repository=None):
    """Resolve one control root for the primary checkout and all its worktrees."""
    repository = Path(repository) if repository else Path(__file__).resolve().parents[1]
    git = repository / ".git"
    if git.is_file():
        text = git.read_text().strip()
        if not text.startswith("gitdir: "):
            raise AdmissionError("Git ownership is unavailable")
        git = (repository / text[8:]).resolve()
    if not git.is_dir():
        raise AdmissionError("Git ownership is unavailable")
    common = git / "commondir"
    if common.exists():
        git = (git / common.read_text().strip()).resolve()
    return git.resolve() / "financial-admission"


def get_coordinator():
    return Coordinator(control_directory())


class Coordinator:
    def __init__(self, directory, clock=time.time):
        self.directory = Path(directory)
        self.clock = clock
        self.database = self.directory / "ledger.sqlite3"

    def _directory_safe(self):
        info = self.directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077):
            raise AdmissionError("Financial control directory must be private and owned")

    def _read(self, name):
        self._directory_safe()
        descriptor = os.open(self.directory / name, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > 65536):
                raise AdmissionError("Financial control artifact must be bounded, private and owned")
            return stream.read(65537)

    def _document(self, name):
        return json.loads(self._read(name), object_pairs_hook=_unique)

    def _policy(self):
        try:
            policy = self._document("policy.json")
            if not isinstance(policy, dict) or policy.get("enabled") is not True or policy.get("version") != 1:
                raise AdmissionError("External inference disabled: no approved account policy")
            for field in ["ledger_id", "account_id", "window_id"]:
                if not isinstance(policy.get(field), str) or not 1 <= len(policy[field]) <= 128:
                    raise AdmissionError("Account/window identity missing")
            for field in ["request_limit", "max_output_tokens", "reservation_ttl_seconds"]:
                if type(policy.get(field)) is not int or policy[field] <= 0:
                    raise AdmissionError("Unknown request/token/lease bounds")
            if not 1 <= policy["reservation_ttl_seconds"] <= 600:
                raise AdmissionError("Reservation lease exceeds supported bounds")
            if type(policy.get("used_requests")) is not int or not 0 <= policy["used_requests"] <= policy["request_limit"]:
                raise AdmissionError("Initial quota usage is unknown")
            if policy.get("quota_unit") != "requests" or policy.get("included_zero_cost") is not True:
                raise AdmissionError("Only reviewed included request quotas are supported")
            for field in ["window_start", "window_end"]:
                if (isinstance(policy.get(field), bool) or not isinstance(policy.get(field), (int, float))
                        or not math.isfinite(policy[field])):
                    raise AdmissionError("Quota reset window is unknown")
            if not policy["window_start"] <= self.clock() < policy["window_end"]:
                raise AdmissionError("Account evidence is outside its approved quota window")
            routes = policy.get("routes")
            if not isinstance(routes, list) or not routes:
                raise AdmissionError("No approved account routes")
            for route in routes:
                if (not isinstance(route, dict) or route.get("provider") not in {"fcc", "openrouter"}
                        or any(not isinstance(route.get(k), str) or not route[k] for k in ["model", "endpoint"])):
                    raise AdmissionError("Unsupported or unbounded account route")
            receipt_bytes = self._read("entitlement-receipt.json")
            if hashlib.sha256(receipt_bytes).hexdigest() != policy.get("entitlement_receipt_sha256"):
                raise AdmissionError("Account review receipt hash mismatch")
            receipt = json.loads(receipt_bytes, object_pairs_hook=_unique)
            signed = {k: v for k, v in policy.items() if k != "entitlement_receipt_sha256"}
            if (not isinstance(receipt, dict) or receipt.get("status") != "APPROVED_INCLUDED_ZERO_COST"
                    or receipt.get("policy_sha256") != _digest(signed)
                    or receipt.get("account_id") != policy["account_id"]
                    or not isinstance(receipt.get("reviewer"), str) or not receipt["reviewer"].strip()
                    or type(receipt.get("reviewed_at")) not in (int, float)
                    or not math.isfinite(receipt["reviewed_at"]) or receipt["reviewed_at"] > self.clock()
                    or type(receipt.get("valid_until")) not in (int, float)
                    or not math.isfinite(receipt["valid_until"]) or receipt["valid_until"] < policy["window_end"]):
                raise AdmissionError("Account entitlement review is missing or does not bind this policy")
            return policy
        except AdmissionError:
            raise
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            raise AdmissionError("External inference disabled: financial evidence unavailable") from exc

    def require_route(self, provider, model, endpoint, max_tokens):
        policy = self._policy()
        if (type(max_tokens) is not int or not 0 < max_tokens <= policy["max_output_tokens"]
                or {"provider": provider, "model": model, "endpoint": endpoint} not in policy["routes"]):
            raise AdmissionError("Exact route or output bound lacks account approval")
        return policy

    def require_provider(self, provider):
        policy = self._policy()
        if not any(r["provider"] == provider for r in policy["routes"]):
            raise AdmissionError("Provider lacks reviewed account evidence")

    def initialize(self):
        """Explicit offline ledger creation; never called by a request path.

        An existing ledger or marker is preserved, including interrupted setup.
        This does not generate an entitlement receipt or grant route approval.
        """
        policy = self._policy()
        if (self.directory / "initialized.json").exists():
            raise AdmissionError("Existing ledger identity cannot be initialized again")
        descriptor = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        with sqlite3.connect(self.database) as conn:
            conn.executescript("""
                CREATE TABLE identity(ledger_id TEXT NOT NULL);
                CREATE TABLE control(id INTEGER PRIMARY KEY CHECK(id=1), stop_reason TEXT);
                INSERT INTO control VALUES(1, NULL);
                CREATE TABLE windows(account_id TEXT, window_id TEXT, policy_digest TEXT NOT NULL,
                    request_limit INTEGER NOT NULL, used_requests INTEGER NOT NULL,
                    PRIMARY KEY(account_id,window_id));
                CREATE TABLE reservations(id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                    window_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
                    endpoint TEXT NOT NULL, max_tokens INTEGER NOT NULL, deadline REAL NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('RESERVED','DISPATCHED','SETTLED','RELEASED','UNKNOWN')));
            """)
            conn.execute("INSERT INTO identity VALUES(?)", (policy["ledger_id"],))
        descriptor = os.open(self.directory / "initialized.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"ledger_id": policy["ledger_id"]}, stream)
            stream.flush()
            os.fsync(stream.fileno())

    @contextmanager
    def _transaction(self):
        conn = None
        try:
            marker = self._document("initialized.json")
            for suffix in ["", "-journal", "-wal", "-shm"]:
                path = Path(str(self.database) + suffix)
                if path.exists() or path.is_symlink():
                    info = path.lstat()
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or info.st_uid != os.geteuid() or info.st_mode & 0o077):
                        raise AdmissionError("Unsafe financial ledger file")
            conn = sqlite3.connect(self.database.resolve().as_uri() + "?mode=rw", uri=True, timeout=2)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE")
            identity = conn.execute("SELECT ledger_id FROM identity").fetchall()
            if len(identity) != 1 or marker != {"ledger_id": identity[0][0]}:
                raise AdmissionError("Financial ledger identity mismatch")
            yield conn
            conn.commit()
        except AdmissionError:
            raise
        except (sqlite3.Error, OSError, ValueError, TypeError, RecursionError) as exc:
            raise AdmissionError("Financial accounting unavailable; no dispatch permitted") from exc
        finally:
            if conn is not None:
                conn.close()

    def reserve(self, provider, model, endpoint, max_tokens):
        policy = self.require_route(provider, model, endpoint, max_tokens)
        refusal = None
        token = uuid.uuid4().hex
        with self._transaction() as conn:
            identity = conn.execute("SELECT ledger_id FROM identity").fetchone()[0]
            if identity != policy["ledger_id"]:
                raise AdmissionError("Policy references a different ledger identity")
            expired = conn.execute("SELECT id FROM reservations WHERE state='DISPATCHED' AND deadline<=?",
                                   (self.clock(),)).fetchall()
            if expired:
                conn.execute("UPDATE reservations SET state='UNKNOWN' WHERE state='DISPATCHED' AND deadline<=?", (self.clock(),))
                conn.execute("UPDATE control SET stop_reason=coalesce(stop_reason,'expired_dispatch_outcome_unknown') WHERE id=1")
            stop = conn.execute("SELECT stop_reason FROM control WHERE id=1").fetchone()[0]
            if stop:
                refusal = AdmissionStoppedError(stop)
            else:
                conn.execute("UPDATE reservations SET state='RELEASED' WHERE state='RESERVED' AND deadline<=?", (self.clock(),))
                key = (policy["account_id"], policy["window_id"])
                digest = _digest(policy)
                conn.execute("INSERT OR IGNORE INTO windows VALUES(?,?,?,?,?)",
                             (*key, digest, policy["request_limit"], policy["used_requests"]))
                window = conn.execute("SELECT * FROM windows WHERE account_id=? AND window_id=?", key).fetchone()
                if window["policy_digest"] != digest:
                    raise AdmissionError("Quota policy changed within a window; independent reconciliation required")
                used = conn.execute("SELECT count(*) FROM reservations WHERE account_id=? AND window_id=? AND state!='RELEASED'", key).fetchone()[0]
                if used + window["used_requests"] >= window["request_limit"]:
                    refusal = AdmissionError("Included request quota exhausted; defer until reviewed reset")
                else:
                    conn.execute("INSERT INTO reservations VALUES(?,?,?,?,?,?,?,?, 'RESERVED')",
                                 (token, *key, provider, model, endpoint, max_tokens,
                                  self.clock() + policy["reservation_ttl_seconds"]))
        if refusal:
            raise refusal
        return token

    def dispatch(self, token):
        policy = self._policy()
        refusal = None
        with self._transaction() as conn:
            expired = conn.execute("SELECT id FROM reservations WHERE state='DISPATCHED' AND deadline<=?",
                                   (self.clock(),)).fetchall()
            if expired:
                conn.execute("UPDATE reservations SET state='UNKNOWN' WHERE state='DISPATCHED' AND deadline<=?", (self.clock(),))
                conn.execute("UPDATE control SET stop_reason=coalesce(stop_reason,'expired_dispatch_outcome_unknown') WHERE id=1")
            stop = conn.execute("SELECT stop_reason FROM control WHERE id=1").fetchone()[0]
            if stop:
                refusal = AdmissionStoppedError(stop)
            else:
                row = conn.execute("SELECT * FROM reservations WHERE id=?", (token,)).fetchone()
                if (row is None or row["state"] != "RESERVED" or row["deadline"] <= self.clock()
                        or row["account_id"] != policy["account_id"] or row["window_id"] != policy["window_id"]
                        or {"provider": row["provider"], "model": row["model"], "endpoint": row["endpoint"]} not in policy["routes"]):
                    raise AdmissionError("Stale or invalid dispatch reservation")
                window = conn.execute("SELECT policy_digest FROM windows WHERE account_id=? AND window_id=?",
                                      (row["account_id"], row["window_id"])).fetchone()
                if not window or window[0] != _digest(policy):
                    raise AdmissionError("Dispatch policy changed after reservation")
                conn.execute("UPDATE reservations SET state='DISPATCHED' WHERE id=?", (token,))
        if refusal:
            raise refusal

    def uncertain(self, token, reason):
        with self._transaction() as conn:
            changed = conn.execute("UPDATE reservations SET state='UNKNOWN' WHERE id=? AND state='DISPATCHED'", (token,)).rowcount
            if changed != 1:
                raise AdmissionError("Cannot reconcile a stale dispatch")
            conn.execute("UPDATE control SET stop_reason=coalesce(stop_reason,?) WHERE id=1", (reason,))

    def reconcile(self, token, status, body):
        reason = None
        usage = body.get("usage") if isinstance(body, dict) else None
        cost = usage.get("cost") if isinstance(usage, dict) else None
        try:
            if cost is None or isinstance(cost, bool):
                raise ValueError
            amount = Decimal(str(cost))
            if not amount.is_finite() or amount < 0:
                raise ValueError
            if amount != 0:
                reason = "reported_nonzero_cost"
        except (InvalidOperation, TypeError, ValueError):
            reason = "reported_cost_unknown_or_invalid"
        if type(status) is not int or not 100 <= status <= 599:
            reason = "dispatch_outcome_unknown"
        elif status in {401, 402, 429}:
            reason = "account_auth_billing_or_quota_block"
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM reservations WHERE id=?", (token,)).fetchone()
            if row is None or row["state"] != "DISPATCHED":
                raise AdmissionError("Cannot reconcile a stale dispatch")
            if isinstance(body, dict) and ((status == 200 and body.get("model") != row["model"])
                                          or (body.get("model") is not None and body["model"] != row["model"])):
                reason = reason or "response_model_not_approved"
            if reason:
                conn.execute("UPDATE reservations SET state='UNKNOWN' WHERE id=?", (token,))
                conn.execute("UPDATE control SET stop_reason=coalesce(stop_reason,?) WHERE id=1", (reason,))
            else:
                conn.execute("UPDATE reservations SET state='SETTLED' WHERE id=?", (token,))
        if reason:
            raise AdmissionStoppedError(reason)

    def execute(self, provider, model, endpoint, max_tokens, action):
        token = self.reserve(provider, model, endpoint, max_tokens)
        self.dispatch(token)
        try:
            status, body = action()
        except BaseException:
            self.uncertain(token, "dispatch_outcome_unknown")
            raise
        self.reconcile(token, status, body)
        return status, body
