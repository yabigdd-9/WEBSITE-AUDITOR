from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .security import (
    DEFAULT_TOTP_ALGORITHM,
    TOTP_ENVELOPE_PREFIX,
    decrypt_totp_secret,
    encrypt_totp_secret,
    normalize_totp_algorithm,
    parse_totp_encryption_key,
)

AUTH_RATE_LIMIT_MAX_WINDOW_SECONDS = 3600
AUTH_RATE_LIMIT_CLEANUP_BATCH_SIZE = 100
MAX_CUSTOMER_WORKSPACES = 5


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


DatabaseError = sqlite3.DatabaseError
DatabaseIntegrityError = sqlite3.IntegrityError


class _HybridRow(dict):
    """Mapping row that preserves SQLite's historical integer-index access."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def _postgres_row_factory(cursor):
    if cursor.description is None:
        return lambda _values: None
    columns = [column.name for column in cursor.description]

    def make_row(values):
        return _HybridRow(zip(columns, values))

    return make_row


class _PostgresConnection:
    """Small adapter for the parameter and cursor behavior used by this app."""

    def __init__(self, connection, psycopg):
        self._connection = connection
        self._psycopg = psycopg

    def execute(self, statement: str, parameters=()):
        statement = statement.strip()
        if statement.upper() == "BEGIN IMMEDIATE":
            statement = "BEGIN"
        try:
            return self._connection.execute(statement.replace("?", "%s"), parameters)
        except self._psycopg.IntegrityError:
            raise DatabaseIntegrityError("Database constraint was not satisfied") from None
        except self._psycopg.Error:
            raise DatabaseError("Database operation failed") from None

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)


class Database:
    def __init__(
        self,
        path: str | Path,
        *,
        initialize: bool = True,
        totp_encryption_key: bytes | None = None,
    ):
        value = str(path)
        self.database_url = value if value.startswith(("postgres://", "postgresql://")) else None
        local_path = Path(path).expanduser() if not self.database_url else None
        if local_path is not None and local_path.is_symlink():
            raise DatabaseError("The local application database must not be a symbolic link.")
        self.path = None if local_path is None else local_path.resolve()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._secure_local_database_file()
        if totp_encryption_key is not None and len(totp_encryption_key) != 32:
            raise DatabaseError("The TOTP encryption key must contain exactly 32 bytes.")
        self._totp_encryption_key = totp_encryption_key or self._load_totp_encryption_key()
        if initialize:
            self.initialize()

    def _secure_local_database_file(self) -> None:
        """Create or restrict the SQLite file before opening it for database work."""
        no_follow = getattr(os, "O_NOFOLLOW", 0)
        if not no_follow and self.path.is_symlink():
            raise DatabaseError("The local application database must not be a symbolic link.")
        try:
            descriptor = os.open(
                self.path,
                os.O_RDWR | os.O_CREAT | no_follow,
                0o600,
            )
        except OSError:
            raise DatabaseError("The local application database could not be opened safely.") from None
        try:
            metadata = os.fstat(descriptor)
            owner = getattr(os, "geteuid", lambda: metadata.st_uid)()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != owner:
                raise DatabaseError(
                    "The local application database must be a regular file owned by this user."
                )
            os.fchmod(descriptor, 0o600)
            protected = os.fstat(descriptor)
            if protected.st_mode & 0o077:
                raise DatabaseError(
                    "The local application database must have owner-only permissions (0600)."
                )
        except DatabaseError:
            raise
        except OSError:
            raise DatabaseError(
                "The local application database permissions could not be secured."
            ) from None
        finally:
            os.close(descriptor)

    @contextmanager
    def connect(self):
        postgres = self.database_url is not None
        raw = None
        psycopg = None
        try:
            if postgres:
                try:
                    import psycopg as psycopg_module
                except ImportError as exc:
                    raise DatabaseError("PostgreSQL support requires the psycopg runtime dependency") from exc
                psycopg = psycopg_module
                parsed = urlsplit(self.database_url)
                connect_options = {"row_factory": _postgres_row_factory, "connect_timeout": 10}
                if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                    connect_options["sslmode"] = "verify-full"
                raw = psycopg.connect(self.database_url, **connect_options)
                db = _PostgresConnection(raw, psycopg)
            else:
                raw = sqlite3.connect(self.path, timeout=10, isolation_level="IMMEDIATE")
                raw.row_factory = sqlite3.Row
                raw.execute("PRAGMA foreign_keys=ON")
                raw.execute("PRAGMA busy_timeout=10000")
                db = raw
            yield db
            raw.commit()
        except Exception as exc:
            if raw is not None:
                raw.rollback()
            if postgres and psycopg is not None:
                if isinstance(exc, psycopg.IntegrityError):
                    raise DatabaseIntegrityError("Database constraint was not satisfied") from None
                if isinstance(exc, psycopg.Error):
                    raise DatabaseError("Database operation failed") from None
            if not postgres and isinstance(exc, sqlite3.Error):
                if isinstance(exc, sqlite3.IntegrityError):
                    raise DatabaseIntegrityError("Database constraint was not satisfied") from None
                raise DatabaseError("Database operation failed") from None
            raise
        finally:
            if raw is not None:
                raw.close()

    def integrity_check(self) -> str:
        with self.connect() as db:
            if self.database_url:
                return "ok" if db.execute("SELECT 1").fetchone()[0] == 1 else "unavailable"
            return db.execute("PRAGMA quick_check").fetchone()[0]

    def allow_rate_attempt(
        self,
        scope: str,
        subject: str,
        limit: int,
        window_seconds: int,
        *,
        now: int | None = None,
    ) -> bool:
        """Atomically consume a persistent, hashed-subject rate-limit attempt."""
        current = int(time.time()) if now is None else int(now)
        subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        with self.connect() as db:
            row = db.execute(
                "INSERT INTO auth_rate_limits(scope,subject_hash,window_started,hits,updated_at) "
                "VALUES(?,?,?,1,?) ON CONFLICT(scope,subject_hash) DO UPDATE SET "
                "window_started=CASE WHEN auth_rate_limits.window_started+?<=? THEN ? "
                "ELSE auth_rate_limits.window_started END, "
                "hits=CASE WHEN auth_rate_limits.window_started+?<=? THEN 1 "
                "ELSE auth_rate_limits.hits+1 END, updated_at=excluded.updated_at RETURNING hits",
                (
                    scope,
                    subject_hash,
                    current,
                    current,
                    window_seconds,
                    current,
                    current,
                    window_seconds,
                    current,
                ),
            ).fetchone()
            # Prune expired subjects from the active scope promptly, and
            # slowly sweep other scopes too. All application auth windows
            # are at most one hour; the indexed batch bounds work per request.
            global_cutoff = current - max(
                AUTH_RATE_LIMIT_MAX_WINDOW_SECONDS, window_seconds
            )
            scope_cutoff = current - window_seconds
            db.execute(
                "DELETE FROM auth_rate_limits "
                "WHERE (scope,subject_hash) IN ("
                "SELECT scope,subject_hash FROM auth_rate_limits "
                "WHERE updated_at<=? OR (scope=? AND updated_at<=?) "
                "ORDER BY updated_at,scope,subject_hash LIMIT ?) "
                "AND (updated_at<=? OR (scope=? AND updated_at<=?))",
                (
                    global_cutoff,
                    scope,
                    scope_cutoff,
                    AUTH_RATE_LIMIT_CLEANUP_BATCH_SIZE,
                    global_cutoff,
                    scope,
                    scope_cutoff,
                ),
            )
        return row["hits"] <= limit

    def rate_attempt_available(
        self,
        scope: str,
        subject: str,
        limit: int,
        window_seconds: int,
        *,
        now: int | None = None,
    ) -> bool:
        """Check a persistent rate bucket without consuming an attempt."""
        current = int(time.time()) if now is None else int(now)
        subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        with self.connect() as db:
            row = db.execute(
                "SELECT window_started,hits FROM auth_rate_limits WHERE scope=? AND subject_hash=?",
                (scope, subject_hash),
            ).fetchone()
        return (
            not row
            or current >= row["window_started"] + window_seconds
            or row["hits"] < limit
        )

    def clear_rate_attempts(self, scope: str, subject: str) -> None:
        """Clear a subject's failed-attempt bucket after successful auth."""
        subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        with self.connect() as db:
            db.execute(
                "DELETE FROM auth_rate_limits WHERE scope=? AND subject_hash=?",
                (scope, subject_hash),
            )

    def consume_totp_step(self, workspace_id: str, user_id: str, step: int) -> bool:
        """Atomically reject a privileged TOTP step that was already accepted."""
        with self.connect() as db:
            row = db.execute(
                "UPDATE memberships SET totp_last_step=? "
                "WHERE workspace_id=? AND user_id=? AND active=1 "
                "AND (totp_last_step IS NULL OR totp_last_step<?) "
                "RETURNING user_id",
                (step, workspace_id, user_id, step),
            ).fetchone()
        return row is not None

    def initialize(self) -> None:
        if self.database_url:
            self._initialize_postgres()
            self._protect_totp_secrets()
            return
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 8:
                raise RuntimeError("Catalyx application database is newer than this version")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    email_verified_at TEXT,
                    disabled_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    user_id TEXT NOT NULL REFERENCES users(id),
                    role TEXT NOT NULL CHECK(role IN ('owner','admin','reviewer','support','customer')),
                    active INTEGER NOT NULL DEFAULT 1,
                    totp_secret TEXT,
                    totp_algorithm TEXT NOT NULL DEFAULT 'SHA1' CHECK(totp_algorithm IN ('SHA1','SHA256','SHA512')),
                    totp_last_step INTEGER,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS sites (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    origin TEXT NOT NULL,
                    host TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_by TEXT NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    deleted_at TEXT,
                    UNIQUE(workspace_id, origin)
                );
                CREATE INDEX IF NOT EXISTS idx_sites_workspace ON sites(workspace_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS authorization_receipts (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    site_id TEXT NOT NULL REFERENCES sites(id),
                    user_id TEXT NOT NULL REFERENCES users(id),
                    statement TEXT NOT NULL,
                    version TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_requests (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    site_id TEXT NOT NULL REFERENCES sites(id),
                    requested_by TEXT NOT NULL REFERENCES users(id),
                    authorization_id TEXT NOT NULL REFERENCES authorization_receipts(id),
                    profile TEXT NOT NULL CHECK(profile='static'),
                    state TEXT NOT NULL CHECK(state IN ('authorization_review','queued','running','quality_review','released','denied','cancelled','failed','expired','withheld','deletion_pending','deleted')),
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reviewed_by TEXT REFERENCES users(id),
                    review_reason TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    worker_lease_until INTEGER,
                    worker_lease_token TEXT,
                    UNIQUE(workspace_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_audits_workspace ON audit_requests(workspace_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_audits_state ON audit_requests(state, created_at);
                CREATE TABLE IF NOT EXISTS worker_leases (
                    name TEXT PRIMARY KEY CHECK(name='audit'),
                    token TEXT,
                    expires_at INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO worker_leases(name,token,expires_at) VALUES('audit',NULL,0)
                    ON CONFLICT(name) DO NOTHING;
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    csrf_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS auth_rate_limits (
                    scope TEXT NOT NULL,
                    subject_hash TEXT NOT NULL,
                    window_started INTEGER NOT NULL,
                    hits INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY(scope, subject_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_auth_rate_limits_updated ON auth_rate_limits(updated_at);
                CREATE TABLE IF NOT EXISTS verification_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admin_activity (
                    id TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL REFERENCES users(id),
                    actor_role TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_admin_activity_time ON admin_activity(created_at DESC);
                CREATE TABLE IF NOT EXISTS privacy_requests (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    user_id TEXT NOT NULL REFERENCES users(id),
                    request_type TEXT NOT NULL CHECK(request_type IN ('access','export','delete')),
                    state TEXT NOT NULL CHECK(state IN ('received','identity_review','approved','completed','declined')),
                    customer_note TEXT NOT NULL DEFAULT '',
                    admin_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reviewed_by TEXT REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_privacy_requests_state ON privacy_requests(state, created_at DESC);
                CREATE TABLE IF NOT EXISTS audit_results (
                    audit_id TEXT PRIMARY KEY REFERENCES audit_requests(id),
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    schema_version INTEGER NOT NULL,
                    profile TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    report_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_results_workspace ON audit_results(workspace_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS report_releases (
                    audit_id TEXT PRIMARY KEY REFERENCES audit_results(audit_id),
                    reviewer_id TEXT NOT NULL REFERENCES users(id),
                    state TEXT NOT NULL CHECK(state IN ('released','withheld')),
                    reason TEXT NOT NULL,
                    report_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_password_reset_expiry ON password_reset_tokens(expires_at);
                """
            )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(audit_requests)")}
            if "attempt_count" not in columns:
                db.execute("ALTER TABLE audit_requests ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
            if "worker_lease_until" not in columns:
                db.execute("ALTER TABLE audit_requests ADD COLUMN worker_lease_until INTEGER")
            if "worker_lease_token" not in columns:
                db.execute("ALTER TABLE audit_requests ADD COLUMN worker_lease_token TEXT")
            membership_columns = {row["name"] for row in db.execute("PRAGMA table_info(memberships)")}
            if "totp_last_step" not in membership_columns:
                db.execute("ALTER TABLE memberships ADD COLUMN totp_last_step INTEGER")
            if "totp_algorithm" not in membership_columns:
                db.execute(
                    "ALTER TABLE memberships ADD COLUMN totp_algorithm TEXT NOT NULL "
                    "DEFAULT 'SHA1' CHECK(totp_algorithm IN ('SHA1','SHA256','SHA512'))"
                )
            db.execute("PRAGMA user_version=8")
        self._protect_totp_secrets()

    def _load_totp_encryption_key(self) -> bytes:
        configured = os.getenv("CATALYX_TOTP_ENCRYPTION_KEY", "")
        if configured:
            try:
                return parse_totp_encryption_key(configured)
            except ValueError:
                raise DatabaseError(
                    "CATALYX_TOTP_ENCRYPTION_KEY must be base64url-encoded 32-byte data."
                ) from None
        if self.database_url:
            raise DatabaseError(
                "CATALYX_TOTP_ENCRYPTION_KEY is required when using PostgreSQL."
            )

        key_path = self.path.with_name(self.path.name + ".totp-key")
        no_follow = getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(key_path, os.O_RDONLY | no_follow)
        except FileNotFoundError:
            generated = base64.urlsafe_b64encode(os.urandom(32)) + b"\n"
            try:
                descriptor = os.open(
                    key_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | no_follow,
                    0o600,
                )
            except FileExistsError:
                return self._read_local_totp_encryption_key(key_path)
            except OSError:
                raise DatabaseError("The local TOTP encryption key could not be created.") from None
            try:
                with os.fdopen(descriptor, "wb") as key_file:
                    key_file.write(generated)
                    key_file.flush()
                    os.fsync(key_file.fileno())
            except OSError:
                raise DatabaseError("The local TOTP encryption key could not be saved.") from None
            return parse_totp_encryption_key(generated.decode("ascii").strip())
        except OSError:
            raise DatabaseError("The local TOTP encryption key could not be opened safely.") from None
        os.close(descriptor)
        return self._decode_local_totp_encryption_key(key_path)

    @staticmethod
    def _decode_local_totp_encryption_key(key_path: Path) -> bytes:
        try:
            descriptor = os.open(key_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                metadata = os.fstat(descriptor)
                owner = getattr(os, "geteuid", lambda: metadata.st_uid)()
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != owner
                    or metadata.st_mode & 0o077
                ):
                    raise DatabaseError(
                        "The local TOTP key must be a regular owner-only file with mode 0600."
                    )
                encoded = os.read(descriptor, 129).decode("ascii").strip()
            finally:
                os.close(descriptor)
            return parse_totp_encryption_key(encoded)
        except DatabaseError:
            raise
        except (OSError, UnicodeDecodeError, ValueError):
            raise DatabaseError("The local TOTP encryption key is invalid or unreadable.") from None

    def _read_local_totp_encryption_key(self, key_path: Path) -> bytes:
        return self._decode_local_totp_encryption_key(key_path)

    def _protect_totp_secrets(self) -> None:
        """Encrypt legacy plaintext seeds and verify ciphertext before app startup."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT workspace_id,user_id,totp_secret FROM memberships "
                "WHERE totp_secret IS NOT NULL"
            ).fetchall()
            for row in rows:
                secret = row["totp_secret"]
                if secret.startswith(TOTP_ENVELOPE_PREFIX):
                    try:
                        decrypt_totp_secret(
                            secret,
                            self._totp_encryption_key,
                            row["workspace_id"],
                            row["user_id"],
                        )
                    except ValueError:
                        raise DatabaseError(
                            "A stored administrator TOTP secret failed authentication."
                        ) from None
                    continue
                protected = encrypt_totp_secret(
                    secret,
                    self._totp_encryption_key,
                    row["workspace_id"],
                    row["user_id"],
                )
                db.execute(
                    "UPDATE memberships SET totp_secret=? "
                    "WHERE workspace_id=? AND user_id=? AND totp_secret=?",
                    (protected, row["workspace_id"], row["user_id"], secret),
                )

    def decrypt_totp_secret(self, envelope: str, workspace_id: str, user_id: str) -> str:
        return decrypt_totp_secret(
            envelope, self._totp_encryption_key, workspace_id, user_id
        )

    def rotate_totp_secrets(self, old_key: bytes, new_key: bytes, *, apply: bool = False) -> dict:
        """Validate and optionally re-encrypt all administrator seeds in one transaction."""
        if len(old_key) != 32 or len(new_key) != 32:
            raise ValueError("TOTP rotation keys must contain exactly 32 bytes.")
        if hmac.compare_digest(old_key, new_key):
            raise ValueError("The old and new TOTP encryption keys must differ.")

        rotated = []
        already_current = 0
        with self.connect() as db:
            rows = db.execute(
                "SELECT workspace_id,user_id,totp_secret FROM memberships "
                "WHERE totp_secret IS NOT NULL"
            ).fetchall()
            for row in rows:
                value = row["totp_secret"]
                if not value.startswith(TOTP_ENVELOPE_PREFIX):
                    raise ValueError(
                        "A stored administrator TOTP secret is not encrypted; initialize the schema first."
                    )
                associated = (row["workspace_id"], row["user_id"])
                try:
                    plaintext = decrypt_totp_secret(value, old_key, *associated)
                except ValueError:
                    try:
                        decrypt_totp_secret(value, new_key, *associated)
                    except ValueError:
                        raise ValueError(
                            "A stored administrator TOTP secret matches neither rotation key."
                        ) from None
                    already_current += 1
                    continue
                rotated.append(
                    (
                        encrypt_totp_secret(plaintext, new_key, *associated),
                        row["workspace_id"],
                        row["user_id"],
                        value,
                    )
                )

            if apply:
                for envelope, workspace_id, user_id, previous in rotated:
                    changed = db.execute(
                        "UPDATE memberships SET totp_secret=? "
                        "WHERE workspace_id=? AND user_id=? AND totp_secret=?",
                        (envelope, workspace_id, user_id, previous),
                    )
                    if changed.rowcount != 1:
                        raise ValueError(
                            "An administrator TOTP secret changed during key rotation."
                        )
        return {
            "total": len(rows),
            "rotated": len(rotated) if apply else 0,
            "would_rotate": len(rotated),
            "already_current": already_current,
            "applied": apply,
        }

    def _initialize_postgres(self) -> None:
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS catalyx_schema_version ("
                "singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton), "
                "version INTEGER NOT NULL CHECK(version >= 0))"
            )
            db.execute("SELECT pg_advisory_xact_lock(hashtext('catalyx_web_schema'))")
            db.execute("INSERT INTO catalyx_schema_version(singleton,version) VALUES(TRUE,0) ON CONFLICT(singleton) DO NOTHING")
            version = db.execute("SELECT version FROM catalyx_schema_version WHERE singleton=TRUE").fetchone()["version"]
            if version > 8:
                raise DatabaseError("Catalyx application database is newer than this version")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    email_verified_at TEXT,
                    disabled_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    user_id TEXT NOT NULL REFERENCES users(id),
                    role TEXT NOT NULL CHECK(role IN ('owner','admin','reviewer','support','customer')),
                    active INTEGER NOT NULL DEFAULT 1,
                    totp_secret TEXT,
                    totp_algorithm TEXT NOT NULL DEFAULT 'SHA1' CHECK(totp_algorithm IN ('SHA1','SHA256','SHA512')),
                    totp_last_step BIGINT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS sites (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    origin TEXT NOT NULL,
                    host TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_by TEXT NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    deleted_at TEXT,
                    UNIQUE(workspace_id, origin)
                );
                CREATE INDEX IF NOT EXISTS idx_sites_workspace ON sites(workspace_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS authorization_receipts (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    site_id TEXT NOT NULL REFERENCES sites(id),
                    user_id TEXT NOT NULL REFERENCES users(id),
                    statement TEXT NOT NULL,
                    version TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_requests (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    site_id TEXT NOT NULL REFERENCES sites(id),
                    requested_by TEXT NOT NULL REFERENCES users(id),
                    authorization_id TEXT NOT NULL REFERENCES authorization_receipts(id),
                    profile TEXT NOT NULL CHECK(profile='static'),
                    state TEXT NOT NULL CHECK(state IN ('authorization_review','queued','running','quality_review','released','denied','cancelled','failed','expired','withheld','deletion_pending','deleted')),
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reviewed_by TEXT REFERENCES users(id),
                    review_reason TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    worker_lease_until INTEGER,
                    worker_lease_token TEXT,
                    UNIQUE(workspace_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_audits_workspace ON audit_requests(workspace_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_audits_state ON audit_requests(state, created_at);
                CREATE TABLE IF NOT EXISTS worker_leases (
                    name TEXT PRIMARY KEY CHECK(name='audit'),
                    token TEXT,
                    expires_at BIGINT NOT NULL DEFAULT 0
                );
                INSERT INTO worker_leases(name,token,expires_at) VALUES('audit',NULL,0)
                    ON CONFLICT(name) DO NOTHING;
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    csrf_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS auth_rate_limits (
                    scope TEXT NOT NULL,
                    subject_hash TEXT NOT NULL,
                    window_started BIGINT NOT NULL,
                    hits INTEGER NOT NULL,
                    updated_at BIGINT NOT NULL,
                    PRIMARY KEY(scope, subject_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_auth_rate_limits_updated ON auth_rate_limits(updated_at);
                CREATE TABLE IF NOT EXISTS verification_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admin_activity (
                    id TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL REFERENCES users(id),
                    actor_role TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_admin_activity_time ON admin_activity(created_at DESC);
                CREATE TABLE IF NOT EXISTS privacy_requests (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    user_id TEXT NOT NULL REFERENCES users(id),
                    request_type TEXT NOT NULL CHECK(request_type IN ('access','export','delete')),
                    state TEXT NOT NULL CHECK(state IN ('received','identity_review','approved','completed','declined')),
                    customer_note TEXT NOT NULL DEFAULT '',
                    admin_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reviewed_by TEXT REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_privacy_requests_state ON privacy_requests(state, created_at DESC);
                CREATE TABLE IF NOT EXISTS audit_results (
                    audit_id TEXT PRIMARY KEY REFERENCES audit_requests(id),
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    schema_version INTEGER NOT NULL,
                    profile TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    report_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_results_workspace ON audit_results(workspace_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS report_releases (
                    audit_id TEXT PRIMARY KEY REFERENCES audit_results(audit_id),
                    reviewer_id TEXT NOT NULL REFERENCES users(id),
                    state TEXT NOT NULL CHECK(state IN ('released','withheld')),
                    reason TEXT NOT NULL,
                    report_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_password_reset_expiry ON password_reset_tokens(expires_at);
                """
            )
            db.execute("ALTER TABLE audit_requests ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0")
            db.execute("ALTER TABLE audit_requests ADD COLUMN IF NOT EXISTS worker_lease_until INTEGER")
            db.execute("ALTER TABLE audit_requests ADD COLUMN IF NOT EXISTS worker_lease_token TEXT")
            db.execute("ALTER TABLE memberships ADD COLUMN IF NOT EXISTS totp_last_step BIGINT")
            db.execute(
                "ALTER TABLE memberships ADD COLUMN IF NOT EXISTS totp_algorithm TEXT "
                "NOT NULL DEFAULT 'SHA1' CHECK(totp_algorithm IN ('SHA1','SHA256','SHA512'))"
            )
            db.execute("UPDATE catalyx_schema_version SET version=8 WHERE singleton=TRUE")

    def create_customer(self, email: str, password_hash: str) -> tuple[str, str]:
        user_id, workspace_id = str(uuid.uuid4()), str(uuid.uuid4())
        with self.connect() as db:
            if self.database_url is not None:
                db.execute("SELECT pg_advisory_xact_lock(1128350801, 1)")
            else:
                db.execute("BEGIN IMMEDIATE")
            customer_workspaces = db.execute(
                "SELECT count(DISTINCT workspace_id) FROM memberships WHERE role='customer'"
            ).fetchone()[0]
            if customer_workspaces >= MAX_CUSTOMER_WORKSPACES:
                raise ValueError("The first-release beta is currently full.")
            db.execute(
                "INSERT INTO users(id,email,password_hash,created_at) VALUES(?,?,?,?)",
                (user_id, email, password_hash, now_iso()),
            )
            db.execute(
                "INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)",
                (workspace_id, email.split("@", 1)[0][:80] + " workspace", now_iso()),
            )
            db.execute(
                "INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES(?,?,?,?)",
                (workspace_id, user_id, "customer", now_iso()),
            )
        return user_id, workspace_id

    def acquire_worker_lease(self, token: str, *, now: int, duration: int) -> bool:
        """Atomically acquire the single global audit-worker lease."""
        with self.connect() as db:
            row = db.execute(
                "INSERT INTO worker_leases(name,token,expires_at) VALUES('audit',?,?) "
                "ON CONFLICT(name) DO UPDATE SET token=excluded.token,expires_at=excluded.expires_at "
                "WHERE worker_leases.expires_at<=? RETURNING token",
                (token, now + duration, now),
            ).fetchone()
        return row is not None and row["token"] == token

    def release_worker_lease(self, token: str) -> None:
        """Release the worker lease only if this process still owns it."""
        with self.connect() as db:
            db.execute(
                "UPDATE worker_leases SET token=NULL,expires_at=0 "
                "WHERE name='audit' AND token=?",
                (token,),
            )

    def create_admin(
        self,
        email: str,
        password_hash: str,
        totp_secret: str,
        totp_algorithm: str = DEFAULT_TOTP_ALGORITHM,
    ) -> str:
        user_id, workspace_id = str(uuid.uuid4()), str(uuid.uuid4())
        totp_algorithm = normalize_totp_algorithm(totp_algorithm)
        protected_totp_secret = encrypt_totp_secret(
            totp_secret, self._totp_encryption_key, workspace_id, user_id
        )
        with self.connect() as db:
            db.execute(
                "INSERT INTO users(id,email,password_hash,email_verified_at,created_at) VALUES(?,?,?,?,?)",
                (user_id, email, password_hash, now_iso(), now_iso()),
            )
            db.execute(
                "INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)",
                (workspace_id, "CatalyxLabs operations", now_iso()),
            )
            db.execute(
                "INSERT INTO memberships(workspace_id,user_id,role,totp_secret,totp_algorithm,created_at) VALUES(?,?,?,?,?,?)",
                (
                    workspace_id,
                    user_id,
                    "owner",
                    protected_totp_secret,
                    totp_algorithm,
                    now_iso(),
                ),
            )
        return user_id

    def audit_admin(self, actor: dict, action: str, target_type: str, target_id: str, reason: str, metadata=None, connection=None):
        sql = (
            "INSERT INTO admin_activity(id,actor_id,actor_role,action,target_type,target_id,reason,metadata,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)"
        )
        values = (
            str(uuid.uuid4()), actor["user_id"], actor["role"], action, target_type,
            target_id, reason.strip()[:500], json.dumps(metadata or {}, sort_keys=True), now_iso(),
        )
        if connection is not None:
            connection.execute(sql, values)
            return
        with self.connect() as db:
            db.execute(sql, values)
