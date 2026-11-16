"""Real canonical engine -> private business lifecycle; all network is mocked."""

import hashlib
import json
import socket
import tempfile
import time
from pathlib import Path

import httpx
import pytest

import auditor_toolkit.pipeline as auditor
from auditor_toolkit.common import Fetcher
from scripts import approval_controls as approvals
from scripts import cloud_prospect_pipeline as pipeline
from scripts.client_projects import accept_proposal, complete
from scripts.cloud_discovery import import_export
from scripts.cloud_opportunities import load_policy
from scripts.operational_ledger import OperationalLedger
from scripts.pipeline_store import PipelineStore


def test_canonical_audit_through_project_closure_and_paired_restore(monkeypatch):
    html = (
        '<!doctype html><html lang="en"><head><title>Synthetic local services</title>'
        '<meta name="description" content="Synthetic useful services">'
        '<link rel="canonical" href="https://example.com/"><meta property="og:title" content="Services">'
        '<script type="application/ld+json">{"@type":"LocalBusiness"}</script></head>'
        '<body><main><h1>Services</h1><p>' + "Synthetic business information " * 100
        + '</p><a href="/contact">Contact us</a></main></body></html>'
    )  # Deliberately missing viewport: an observed, supported synthetic issue.
    requests = []

    def handler(request):
        assert request.method == "GET" and request.url.host == "example.com"
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml\n", request=request)
        if request.url.path == "/sitemap.xml":
            return httpx.Response(200, text='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/</loc></url></urlset>',
                                  headers={"content-type": "application/xml"}, request=request)
        return httpx.Response(200, text=html, headers={
            "content-type": "text/html", "content-security-policy": "default-src 'self'",
            "strict-transport-security": "max-age=1000", "x-content-type-options": "nosniff",
        }, request=request)

    def client(*args, **kwargs):
        kwargs.update(transport=httpx.MockTransport(handler), min_interval=0)
        return Fetcher(*args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))
    ])
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: pytest.fail("Real network attempted"))
    monkeypatch.setattr(pipeline, "Fetcher", client)
    monkeypatch.setattr(auditor, "Fetcher", client)
    monkeypatch.setattr(auditor, "inspect_tls", lambda *args: ([], {"mode": "synthetic_tls_fixture"}))
    now = int(time.time())
    policy = load_policy(Path(__file__).resolve().parents[1])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source.json"
        source.write_text(json.dumps([dict(name="Synthetic Services", website="https://example.com", city="Christchurch", category="plumber")]))
        store = PipelineStore(root / "pipeline.sqlite3")
        identity = hashlib.sha256(b"example.com").hexdigest()
        with store.transaction(bootstrap=True) as state:
            import_export(state, source, source="curated", source_url="https://source.example.com/export",
                          terms_reviewed=True, now=now, run_id="fixture-import")
            report = pipeline.process(
                state, [dict(domain="example.com", url="https://example.com/")],
                now=now, run_id="fixture-audit", workspace=root / "audit",
                opportunity_policy=policy, attempt_reserver=store.reserve_attempt,
            )
            assert report["audits_succeeded"] == 1
            assert state["prospects"][identity]["opportunity"]["status"] == "qualified_for_internal_review"
            assert state["prospects"][identity]["audit"]["findings"][0]["evidence_check_status"] == "ok"
        with store.transaction() as state:
            p = state["prospects"][identity]
            version = p["proposal_version"]
            owner = dict(actor="synthetic-owner", reason="Synthetic evidence checked", now=now)
            approvals.approve_proposal(p, version, **owner)
            recipient = hashlib.sha256(b"synthetic-recipient-no-address").hexdigest()
            message = approvals.prepare_outreach(p, recipient_hash=recipient, body="Synthetic internal draft", now=now)
            approvals.review_outreach(p, message, **owner)
            approvals.approve_outreach(p, message, **owner)
            p["contact_permission"] = dict(recipient_hash=recipient, recipient_verified=True, consent_verified=True,
                                           consent_evidence_sha256="a" * 64, sender_identified=True,
                                           unsubscribe_functional=True, opted_out=False, checked_at=now)
            assert approvals.mark_send_eligible(p, message, now=now)
            result = approvals.send_sandbox(p, message, now=now, transport=approvals.SandboxTransport())
            assert result["external_sends"] == 0
            project = accept_proposal(p, version, acceptance_evidence="b" * 64, owner_verified=True, **owner)
            for milestone in ("scope", "access"):
                complete(p, project, kind="milestone", item_id=milestone, completion_evidence="c" * 64, **owner)
            for task in p["projects"][project]["tasks"]:
                complete(p, project, kind="task", item_id=task["id"], completion_evidence="c" * 64, **owner)
            for milestone in ("implementation", "quality", "handover"):
                complete(p, project, kind="milestone", item_id=milestone, completion_evidence="c" * 64, **owner)
            assert p["projects"][project]["status"] == "closed"
            assert pipeline.metrics(state)["contacts_sent"] == 0
        backup = root / "backup.sqlite3"
        store.backup(backup)
        restored = PipelineStore(backup)
        assert restored.read() == store.read()
        assert OperationalLedger(restored.operations_path).summary()["reservations"] == 1
        assert 1 <= len(requests) <= 10
