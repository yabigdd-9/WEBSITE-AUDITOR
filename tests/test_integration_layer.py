import json
import hashlib
import hmac
import urllib.request
from http.server import ThreadingHTTPServer

from integrations.layer import CircuitBreaker, EventBus, Job, github_signature_valid, status
from integrations.server import Handler, process_batch

def start_server(tmp_path, monkeypatch=None, token=None):
    if monkeypatch is not None:
        if token: monkeypatch.setenv("WA_WEBHOOK_TOKEN", token)
        else: monkeypatch.delenv("WA_WEBHOOK_TOKEN", raising=False)
    Handler.root, Handler.bus = tmp_path, EventBus(tmp_path / "events.db")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_event_bus_round_trip(tmp_path):
    bus = EventBus(tmp_path / "events.db"); job = Job("audit.completed", {"url": "https://example.com"}); assert bus.publish(job) == job.id; assert json.loads(bus.claim()[0]["payload"])["kind"] == job.kind; bus.finish(job.id); assert bus.counts() == {"done": 1}

def test_event_bus_retries_then_dead_letters(tmp_path):
    bus = EventBus(tmp_path / "events.db"); job = Job("retry.test", {}); bus.publish(job)
    for attempt in range(5):
        claimed = bus.claim()[0]; assert claimed["attempts"] == attempt
        bus.finish(job.id, "temporary error", retry_base=0)
    assert bus.counts() == {"dead_letter": 1}

def test_idempotency_deduplicates_delivery(tmp_path):
    bus = EventBus(tmp_path / "events.db"); first = Job("delivery", {"v": 1}); second = Job("delivery", {"v": 1})
    assert bus.publish(first, "hook-123") == first.id
    assert bus.publish(second, "hook-123") == first.id
    assert bus.counts() == {"queued": 1}

def test_retry_uses_backoff_and_stale_claim_goes_to_dead_letter(tmp_path):
    bus = EventBus(tmp_path / "events.db"); job = Job("retry", {}); bus.publish(job)
    event = bus.claim()[0]; bus.finish(job.id, "temporary", retry_base=0)
    assert bus.claim()[0]["id"] == event["id"]
    with __import__("sqlite3").connect(bus.path) as db: db.execute("UPDATE events SET attempts=5, updated_at=0 WHERE id=?", (job.id,))
    assert bus.recover_stale(1) == 1
    assert bus.counts() == {"dead_letter": 1}

def test_github_hmac_signature():
    body = b'{"action":"opened"}'; secret = "test-secret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert github_signature_valid(secret, body, sig)
    assert not github_signature_valid(secret, body, "sha256=bad")
    assert not github_signature_valid("", body, sig)

def test_worker_receives_github_event_without_side_effects(tmp_path):
    bus = EventBus(tmp_path / "events.db")
    job = Job("github.push", {"delivery":"gh-1", "payload":{"ref":"refs/heads/main"}}, "github")
    bus.publish(job)
    assert process_batch(bus) == 1
    assert bus.counts() == {"done": 1}
def test_circuit_breaker_opens_after_failures():
    breaker = CircuitBreaker(failures=2, reset_after=60)
    for _ in range(2):
        try: breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("nope")), retries=0)
        except RuntimeError: pass
    assert breaker.open
def test_health_has_safety_and_reserved_fcc(tmp_path):
    result = status(tmp_path); assert result["fcc_reserved_port"] == 8082; assert result["safety"]["paid_calls"] is False
def test_webhook_accepts_event(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch, "test-token")
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/webhooks/event", data=b'{"kind":"test.event","value":1}', headers={"Content-Type": "application/json", "X-WA-Token":"test-token"}, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response: payload = json.load(response)
        assert response.status == 202 and payload["accepted"] is True
    finally: server.shutdown(); server.server_close()

def test_webhook_requires_configured_token(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch, "test-token")
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/webhooks/event", data=b'{"kind":"test.event"}', method="POST")
        try: urllib.request.urlopen(request, timeout=2)
        except Exception as exc: assert getattr(exc, "code", None) == 401
        else: raise AssertionError("missing webhook token must be rejected")
    finally: server.shutdown(); server.server_close()

def test_github_webhook_is_signed_and_idempotent(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch); monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    body = b'{"action":"opened"}'; sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    try:
        def deliver(signature):
            req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/webhooks/github", data=body,
                headers={"Content-Type":"application/json", "X-GitHub-Delivery":"delivery-1", "X-GitHub-Event":"issues", "X-Hub-Signature-256":signature}, method="POST")
            with urllib.request.urlopen(req, timeout=2) as response: return json.load(response)
        assert deliver(sig)["duplicate"] is False
        assert deliver(sig)["duplicate"] is True
        assert Handler.bus.counts() == {"queued":1}
    finally: server.shutdown(); server.server_close()

def test_github_webhook_rejects_bad_signature(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch); monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/webhooks/github", data=b'{}',
            headers={"X-GitHub-Delivery":"d1", "X-GitHub-Event":"push", "X-Hub-Signature-256":"sha256=bad"}, method="POST")
        try: urllib.request.urlopen(req, timeout=2)
        except Exception as exc: assert getattr(exc, "code", None) == 401
        else: raise AssertionError("bad GitHub signature must be rejected")
        assert Handler.bus.counts() == {}
    finally: server.shutdown(); server.server_close()

def test_public_health_is_redacted_and_mutations_fail_closed(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch)
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/health", headers={"Cf-Connecting-Ip":"203.0.113.9"})
        with urllib.request.urlopen(req, timeout=2) as response: health = json.load(response)
        assert "components" not in health
        claim = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/events/claim")
        try: urllib.request.urlopen(claim, timeout=2)
        except Exception as exc: assert getattr(exc, "code", None) == 401
        else: raise AssertionError("claim endpoint must fail closed without token")
        assert Handler.bus.counts() == {}
    finally: server.shutdown(); server.server_close()
