"""Local-first integration primitives for WEBSITE-AUDITOR."""
from __future__ import annotations
import hashlib, json, os, shutil, sqlite3, time, uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_PORT = int(os.getenv("WA_INTEGRATION_PORT", "8091"))
FCC_URL = os.getenv("FCC_BASE_URL", "http://127.0.0.1:8082")
OMNIROUTE_URL = os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128")

@dataclass
class Job:
    kind: str
    payload: dict[str, Any]
    source: str = "website-auditor"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    attempt: int = 0
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    def to_dict(self): return asdict(self)

class EventBus:
    """SQLite-backed, at-least-once event queue with a stable schema."""
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, last_error TEXT,
                available_at REAL NOT NULL DEFAULT 0, idempotency_key TEXT UNIQUE)""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            if "available_at" not in columns: db.execute("ALTER TABLE events ADD COLUMN available_at REAL NOT NULL DEFAULT 0")
            if "idempotency_key" not in columns:
                db.execute("ALTER TABLE events ADD COLUMN idempotency_key TEXT")
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS events_idempotency_key ON events(idempotency_key) WHERE idempotency_key IS NOT NULL")
    def publish(self, job: Job, idempotency_key: str | None = None) -> str:
        now = time.time()
        with sqlite3.connect(self.path) as db:
            if idempotency_key:
                existing = db.execute("SELECT id FROM events WHERE idempotency_key=?", (idempotency_key,)).fetchone()
                if existing: return existing[0]
            try:
                db.execute("INSERT INTO events (id,kind,payload,status,attempts,created_at,updated_at,last_error,available_at,idempotency_key) VALUES (?, ?, ?, 'queued', 0, ?, ?, NULL, 0, ?)",
                           (job.id, job.kind, json.dumps(job.to_dict()), now, now, idempotency_key))
            except sqlite3.IntegrityError:
                existing = db.execute("SELECT id FROM events WHERE idempotency_key=?", (idempotency_key,)).fetchone()
                if not existing: raise
                return existing[0]
        return job.id
    def claim(self, limit=10):
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT * FROM events WHERE status='queued' AND available_at<=? ORDER BY created_at LIMIT ?", (time.time(), limit)).fetchall()
            for row in rows:
                db.execute("UPDATE events SET status='processing', attempts=attempts+1, updated_at=? WHERE id=?", (time.time(), row["id"]))
        return [dict(row) for row in rows]
    def finish(self, event_id, error=None, max_attempts=5, retry_base=2.0):
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT attempts FROM events WHERE id=?", (event_id,)).fetchone()
            if not row: return
            state = ("queued" if row[0] < max_attempts else "dead_letter") if error else "done"
            now = time.time()
            delay = min(300.0, retry_base * (2 ** max(0, row[0] - 1))) if error and state == "queued" else 0
            db.execute("UPDATE events SET status=?, last_error=?, updated_at=?, available_at=? WHERE id=?", (state, str(error)[:1000] if error else None, now, now + delay, event_id))

    def recover_stale(self, stale_after=300):
        """Return abandoned claims to the queue after a consumer crash."""
        cutoff = time.time() - stale_after
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE events SET status=CASE WHEN attempts>=5 THEN 'dead_letter' ELSE 'queued' END, updated_at=?, available_at=? WHERE status='processing' AND updated_at<?", (time.time(), time.time(), cutoff))
            return db.total_changes

    def get(self, event_id):
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            return dict(row) if row else None

    def counts(self):
        with sqlite3.connect(self.path) as db:
            return dict(db.execute("SELECT status, COUNT(*) FROM events GROUP BY status").fetchall())


def github_signature_valid(secret: str, body: bytes, signature: str | None) -> bool:
    import hmac
    if not secret or not signature or not signature.startswith("sha256="): return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

class CircuitBreaker:
    def __init__(self, failures=3, reset_after=30.0): self.failures, self.reset_after, self.count, self.opened_at = failures, reset_after, 0, 0.0
    @property
    def open(self):
        if self.opened_at and time.monotonic() - self.opened_at >= self.reset_after: self.opened_at, self.count = 0.0, 0
        return bool(self.opened_at)
    def call(self, fn: Callable[[], Any], retries=2):
        if self.open: raise RuntimeError("circuit_open")
        for attempt in range(retries + 1):
            try: result = fn(); self.count = 0; return result
            except Exception:
                self.count += 1
                if self.count >= self.failures: self.opened_at = time.monotonic()
                if attempt == retries: raise
                time.sleep(0.05 * (2 ** attempt))

def _http_probe(url, path="/", timeout=1.2):
    try:
        request = Request(url.rstrip("/") + path, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300, f"http_{response.status}"
    except URLError as exc:
        code = getattr(exc, "code", None)
        if code is not None: return False, f"http_{code}"
        return False, type(exc.reason).__name__ if getattr(exc, "reason", None) else type(exc).__name__
    except (TimeoutError, OSError) as exc: return False, type(exc).__name__

def _command(name):
    path = shutil.which(name)
    return {"status": "available" if path else "blocked", "path": path, "reason": None if path else "command_not_found"}

def _obsidian_vault():
    configured = os.getenv("OBSIDIAN_VAULT_PATH")
    if configured:
        path = Path(configured).expanduser()
        return (str(path), "environment") if path.is_dir() else (None, "OBSIDIAN_VAULT_PATH_not_found")
    registry = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    try:
        vaults = json.loads(registry.read_text()).get("vaults", {}).values()
        for vault in vaults:
            path = Path(vault.get("path", "")).expanduser()
            if (path / ".obsidian").is_dir() and (path / "40 Projects" / "WEBSITE-AUDITOR").is_dir():
                os.environ.setdefault("OBSIDIAN_VAULT_PATH", str(path))
                return str(path), "obsidian_app_registry"
    except (OSError, ValueError, TypeError):
        pass
    return None, "OBSIDIAN_VAULT_PATH_not_set"

def status(root="."):
    root = Path(root)
    components = {name: _command(name) for name in ("hermes", "cline", "opencode", "ollama", "omniroute", "fcc-server", "fcc-cline", "fcc-hermes", "fcc-opencode")}
    for name, url, path in (("fcc", FCC_URL, "/admin/api/status"), ("ollama_http", os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"), "/api/tags"), ("omniroute_http", OMNIROUTE_URL, "/api/health")):
        ok, reason = _http_probe(url, path); components[name] = {"status": "healthy" if ok else "blocked", "url": url, "reason": None if ok else reason}
    vault, vault_source = _obsidian_vault()
    notion = os.getenv("NOTION_API_KEY")
    components["obsidian"] = {"status": "configured" if vault else "blocked", "path": vault, "source": vault_source, "reason": None if vault else vault_source}
    components["notion"] = {"status": "configured" if notion else "blocked", "reason": None if notion else "NOTION_API_KEY_not_set"}
    bus = EventBus(root / "outputs" / "integration-events.db")
    return {"service": "website-auditor-integrations", "status": "ok", "port": DEFAULT_PORT, "fcc_reserved_port": 8082, "queue": bus.counts(),
            "database": str(root / "outputs" / "integration-events.db"), "components": components,
            "safety": {"paid_calls": False, "outreach": False, "secrets_from_env_only": True}}
