"""Private server sessions and shared rate limits for the single-owner portal."""

from __future__ import annotations

import hashlib
import hmac
import re
import time

AUTH_LOCK = 598114903


class PostgresPortalAuth:
    def __init__(self, store, *, pepper, password_hash):
        if not isinstance(pepper, bytes) or len(pepper) != 32:
            raise ValueError("A private 32-byte portal pepper is required")
        self.store = store
        self.pepper = pepper
        self.version = self.reference("password:" + password_hash)

    def reference(self, value):
        return hmac.new(self.pepper, value.encode(), hashlib.sha256).hexdigest()

    def verify_schema(self):
        with self.store.connection() as db:
            db.execute("SELECT token_hash,expires,csrf,auth_version FROM moneymachine.portal_sessions LIMIT 0")
            db.execute("SELECT bucket,window_id,attempts FROM moneymachine.portal_rate_limits LIMIT 0")

    def consume(self, buckets, *, now=None):
        """Charge attempts atomically across processes; no IP addresses are stored."""
        window = int(time.time() if now is None else now) // 60
        with self.store.connection() as db, db.transaction():
            db.execute("SELECT pg_advisory_xact_lock(%s)", (AUTH_LOCK,))
            db.execute("DELETE FROM moneymachine.portal_rate_limits WHERE window_id < %s", (window - 1,))
            rows = []
            for label, limit in buckets:
                bucket = self.reference(label)
                found = db.execute(
                    "SELECT window_id,attempts FROM moneymachine.portal_rate_limits WHERE bucket=%s",
                    (bucket,),
                ).fetchone()
                attempts = found[1] if found and found[0] == window else 0
                if attempts >= limit:
                    return False
                rows.append((bucket, window, attempts + 1))
            if db.execute("SELECT count(*) FROM moneymachine.portal_rate_limits").fetchone()[0] >= 1000:
                return False
            for row in rows:
                db.execute(
                    "INSERT INTO moneymachine.portal_rate_limits VALUES(%s,%s,%s) "
                    "ON CONFLICT(bucket) DO UPDATE SET window_id=EXCLUDED.window_id,attempts=EXCLUDED.attempts",
                    row,
                )
        return True

    def login_attempt(self, address, *, now=None):
        return self.consume([("all-logins", 20), ("login:" + address, 5)], now=now)

    def write_attempt(self, session_key, *, now=None):
        return self.consume([("write:" + session_key, 20)], now=now)

    def issue(self, token_hash, csrf, expires, *, now=None):
        now = time.time() if now is None else now
        if (not re.fullmatch(r"[0-9a-f]{64}", token_hash)
                or not re.fullmatch(r"[A-Za-z0-9_-]{43}", csrf)
                or not now < expires <= now + 86400):
            raise ValueError("Invalid bounded owner session")
        with self.store.connection() as db, db.transaction():
            db.execute("SELECT pg_advisory_xact_lock(%s)", (AUTH_LOCK,))
            db.execute(
                "DELETE FROM moneymachine.portal_sessions WHERE expires<=%s OR auth_version<>%s",
                (now, self.version),
            )
            if db.execute("SELECT count(*) FROM moneymachine.portal_sessions").fetchone()[0] >= 100:
                raise ValueError("Owner session capacity reached")
            db.execute(
                "INSERT INTO moneymachine.portal_sessions VALUES(%s,%s,%s,%s)",
                (token_hash, expires, csrf, self.version),
            )

    def get(self, token_hash, *, now=None):
        now = time.time() if now is None else now
        with self.store.connection() as db:
            row = db.execute(
                "SELECT expires,csrf FROM moneymachine.portal_sessions "
                "WHERE token_hash=%s AND expires>%s AND auth_version=%s",
                (token_hash, now, self.version),
            ).fetchone()
        return {"expires": row[0], "csrf": row[1]} if row else None

    def revoke(self, token_hash):
        with self.store.connection() as db:
            db.execute("DELETE FROM moneymachine.portal_sessions WHERE token_hash=%s", (token_hash,))
