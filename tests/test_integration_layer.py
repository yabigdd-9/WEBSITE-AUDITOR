import hashlib
import hmac
import json
import urllib.request
from http.server import ThreadingHTTPServer

from integrations.layer import CircuitBreaker, EventBus, Job, github_signature_valid, status
from integrations.server import Handler, handle_github_audit, process_batch


def start_server(tmp_path, monkeypatch=None, token=None):
    if monkeypatch is not None:
        if token:
            monkeypatch.setenv("WA_WEBHOOK_TOKEN", token)
        else:
            monkeypatch.delenv("WA_WEBHOOK_TOKEN", raising=False)
    Handler.root, Handler.bus = tmp_path, EventBus(tmp_path / "events.db")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_event_bus_round_trip(tmp_path):
    bus = EventBus(tmp_path / "events.db")
    job = Job("audit.completed", {"url": "https://example.com"})
    assert bus.publish(job) == job.id
    assert json.loads(bus.claim()[0]["payload"])["kind"] == job.kind
    bus.finish(job.id)
    assert bus.counts() == {"done": 1}


def test_event_bus_retries_then_dead_letters(tmp_path):
    bus = EventBus(tmp_path / "events.db")
    job = Job("retry.test", {})
    bus.publish(job)
    for attempt in range(5):
        claimed = bus.claim()[0]
        assert claimed["attempts"] == attempt
        bus.finish(job.id, "temporary error", retry_base=0)
    assert bus.counts() == {"dead_letter": 1}


def test_idempotency_deduplicates_delivery(tmp_path):
    bus = EventBus(tmp_path / "events.db")
    first = Job("delivery", {"v": 1})
    second = Job("delivery", {"v": 1})
    assert bus.publish(first, "hook-123") == first.id
    assert bus.publish(second, "hook-123") == first.id
    assert bus.counts() == {"queued": 1}


def test_retry_uses_backoff_and_stale_claim_goes_to_dead_letter(tmp_path):
    bus = EventBus(tmp_path / "events.db")
    job = Job("retry", {})
    bus.publish(job)
    event = bus.claim()[0]
    bus.finish(job.id, "temporary", retry_base=0)
    assert bus.claim()[0]["id"] == event["id"]
    with __import__("sqlite3").connect(bus.path) as db:
        db.execute("UPDATE events SET attempts=5, updated_at=0 WHERE id=?", (job.id,))
    assert bus.recover_stale(1) == 1
    assert bus.counts() == {"dead_letter": 1}


def test_github_hmac_signature():
    body = b'{"action":"opened"}'
    secret = "test-secret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert github_signature_valid(secret, body, sig)
    assert not github_signature_valid(secret, body, "sha256=bad")
    assert not github_signature_valid("", body, sig)


def test_worker_routes_allowlisted_github_event_to_handler(tmp_path, monkeypatch):
    import integrations.server as server_module

    calls = []
    monkeypatch.setattr(
        server_module,
        "handle_github_audit",
        lambda kind, payload: calls.append((kind, payload)) or {"status": "complete"},
    )
    bus = EventBus(tmp_path / "events.db")
    job = Job("github.push", {"delivery": "gh-1", "payload": {"ref": "refs/heads/main"}}, "github")
    bus.publish(job)
    assert process_batch(bus) == 1
    assert bus.counts() == {"done": 1}
    assert calls and calls[0][0] == "github.push"


def test_github_handler_fails_closed_without_configured_site(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_AUDIT_SITE_URL", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY_ALLOWLIST", "yabigdd-9/WEBSITE-AUDITOR")
    try:
        handle_github_audit(
            "github.push",
            {
                "delivery": "gh-1",
                "payload": {"repository": "yabigdd-9/WEBSITE-AUDITOR", "ref": "refs/heads/main"},
            },
        )
    except ValueError as exc:
        assert "not_configured" in str(exc)
    else:
        raise AssertionError("site target must be explicit")


def test_github_handler_requires_repository_allowlist(monkeypatch):
    monkeypatch.setenv("GITHUB_AUDIT_SITE_URL", "https://example.com")
    monkeypatch.delenv("GITHUB_REPOSITORY_ALLOWLIST", raising=False)
    try:
        handle_github_audit(
            "github.push",
            {"delivery": "gh-1", "payload": {"repository": "yabigdd-9/WEBSITE-AUDITOR"}},
        )
    except ValueError as exc:
        assert "not_allowlisted" in str(exc)
    else:
        raise AssertionError("missing repo allowlist must fail closed")


def test_github_handler_rejects_private_or_unresolvable_targets(monkeypatch):
    monkeypatch.setenv("GITHUB_AUDIT_SITE_URL", "http://127.0.0.1/")
    monkeypatch.setenv("GITHUB_REPOSITORY_ALLOWLIST", "yabigdd-9/WEBSITE-AUDITOR")
    try:
        handle_github_audit(
            "github.push",
            {
                "delivery": "gh-1",
                "payload": {"repository": "yabigdd-9/WEBSITE-AUDITOR", "ref": "refs/heads/main"},
            },
        )
    except ValueError as exc:
        assert "non_public" in str(exc)
    else:
        raise AssertionError("private audit target must be rejected")


def test_github_handler_skips_unsupported_pull_request_action(monkeypatch):
    monkeypatch.setenv("GITHUB_AUDIT_SITE_URL", "https://example.com")
    monkeypatch.setenv("GITHUB_REPOSITORY_ALLOWLIST", "yabigdd-9/WEBSITE-AUDITOR")
    result = handle_github_audit(
        "github.pull_request",
        {
            "delivery": "gh-1",
            "payload": {"repository": "yabigdd-9/WEBSITE-AUDITOR", "action": "closed"},
        },
    )
    assert result["status"] == "skipped"


def test_github_handler_runs_static_no_ai_audit(monkeypatch, tmp_path):
    import auditor_toolkit.pipeline as pipeline

    captured = {}

    def fake_run(url, options):
        captured["url"] = url
        captured["options"] = options
        return {"run_id": "run-1", "defect_count": 2, "artifacts": {"json": "report.json"}}

    monkeypatch.setenv("GITHUB_AUDIT_SITE_URL", "https://example.com")
    monkeypatch.setenv("GITHUB_REPOSITORY_ALLOWLIST", "yabigdd-9/WEBSITE-AUDITOR")
    monkeypatch.setenv("WA_ROOT", str(tmp_path))
    monkeypatch.setattr(pipeline, "run_audit", fake_run)
    result = handle_github_audit(
        "github.push",
        {
            "delivery": "gh-1",
            "payload": {"repository": "yabigdd-9/WEBSITE-AUDITOR", "ref": "refs/heads/main"},
        },
    )
    assert result["status"] == "complete" and result["findings"] == 2
    assert captured["options"].ai is False and captured["options"].external_tools is False


def test_omniroute_proxy_allowlist_is_read_only():
    from integrations.server import READONLY_OMNIROUTE_TOOLS as ALLOWED_TOOLS

    assert "omniroute_get_health" in ALLOWED_TOOLS
    assert "omniroute_route_request" not in ALLOWED_TOOLS
    assert "omniroute_switch_combo" not in ALLOWED_TOOLS
    assert all("search" not in name for name in ALLOWED_TOOLS)


def test_circuit_breaker_opens_after_failures():
    breaker = CircuitBreaker(failures=2, reset_after=60)
    for _ in range(2):
        try:
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("nope")), retries=0)
        except RuntimeError:
            pass
    assert breaker.open


def test_health_has_safety_and_reserved_fcc(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY_ALLOWLIST", raising=False)
    monkeypatch.delenv("GITHUB_AUDIT_SITE_URL", raising=False)
    result = status(tmp_path)
    assert result["fcc_reserved_port"] == 8082
    assert result["safety"]["paid_calls"] is False
    assert result["components"]["github_audit_handler"]["status"] == "blocked"


def test_webhook_accepts_event(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch, "test-token")
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/webhooks/event",
            data=b'{"kind":"test.event","value":1}',
            headers={"Content-Type": "application/json", "X-WA-Token": "test-token"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.load(response)
        assert response.status == 202 and payload["accepted"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_webhook_requires_configured_token(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch, "test-token")
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/webhooks/event",
            data=b'{"kind":"test.event"}',
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=2)
        except Exception as exc:
            assert getattr(exc, "code", None) == 401
        else:
            raise AssertionError("missing webhook token must be rejected")
    finally:
        server.shutdown()
        server.server_close()


def test_github_webhook_is_signed_and_idempotent(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    body = b'{"action":"opened"}'
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    try:

        def deliver(signature):
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/webhooks/github",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Delivery": "delivery-1",
                    "X-GitHub-Event": "issues",
                    "X-Hub-Signature-256": signature,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2) as response:
                return json.load(response)

        assert deliver(sig)["duplicate"] is False
        assert deliver(sig)["duplicate"] is True
        assert Handler.bus.counts() == {"queued": 1}
    finally:
        server.shutdown()
        server.server_close()


def test_github_webhook_rejects_bad_signature(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/webhooks/github",
            data=b"{}",
            headers={
                "X-GitHub-Delivery": "d1",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": "sha256=bad",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception as exc:
            assert getattr(exc, "code", None) == 401
        else:
            raise AssertionError("bad GitHub signature must be rejected")
        assert Handler.bus.counts() == {}
    finally:
        server.shutdown()
        server.server_close()


def test_public_health_is_redacted_and_mutations_fail_closed(tmp_path, monkeypatch):
    server = start_server(tmp_path, monkeypatch)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/health",
            headers={"Cf-Connecting-Ip": "203.0.113.9"},
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            health = json.load(response)
        assert "components" not in health
        claim = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/events/claim")
        try:
            urllib.request.urlopen(claim, timeout=2)
        except Exception as exc:
            assert getattr(exc, "code", None) == 401
        else:
            raise AssertionError("claim endpoint must fail closed without token")
        assert Handler.bus.counts() == {}
    finally:
        server.shutdown()
        server.server_close()
