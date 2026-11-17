"""Opening the owner review must never approve, simulate or send a draft."""

import copy
import hashlib
import json

from bs4 import BeautifulSoup

from scripts import approval_controls as controls
from scripts.cloud_prospect_pipeline import metrics
from toolkit_tests.test_pipeline_portal import login
from toolkit_tests.test_pipeline_portal import owner as owner


def seed_draft(store, identity):
    recipient = hashlib.sha256(b"synthetic-review-recipient-no-email").hexdigest()
    body = '<script>alert("fixture")</script> Unsent internal proposal'
    with store.transaction() as state:
        prospect = state["prospects"][identity]
        version = controls.prepare_outreach(
            prospect, recipient_hash=recipient, body=body, now=1767225600,
        )
        decision = {"actor": "fixture-owner", "reason": "Synthetic exact draft review", "now": 1767225600}
        controls.review_outreach(prospect, version, **decision)
        controls.approve_outreach(prospect, version, **decision)
    return version, body


def assert_review(client, expected):
    response = client.get("/pipeline/outreach")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "script-src 'none'" in response.headers["content-security-policy"]
    document = BeautifulSoup(response.text, "html.parser")
    assert document.find("script") is None
    assert json.loads(document.find("pre").get_text()) == expected
    return response


def test_authenticated_review_escapes_approved_drafts_without_advancing_sending(owner, monkeypatch):
    client, store, identity, _ = owner
    login(client)
    version, body = seed_draft(store, identity)
    before = copy.deepcopy(store.read())
    prospect = before["prospects"][identity]

    def forbid_simulation(*args, **kwargs):
        raise AssertionError("Viewing a review page invoked a transport")

    monkeypatch.setattr(controls.SandboxTransport, "send", forbid_simulation)
    expected = [{
        "domain": "example.com", "drafts": prospect["outreach_drafts"],
        "approvals": prospect["approvals"], "events": prospect["outreach_events"],
        "suppressed": False,
    }]
    response = assert_review(client, expected)
    assert body not in response.text
    assert "&lt;script&gt;" in response.text
    assert_review(client, expected)
    assert store.read() == before
    assert controls.stage(prospect, version) == "APPROVED"
    assert controls.eligibility(prospect, version, now=1767225600) is False
    assert metrics(store.read())["contacts_sent"] == 0


def test_review_preserves_empty_state_and_displays_sticky_opt_out_history(owner):
    client, store, identity, _ = owner
    login(client)
    before = copy.deepcopy(store.read())
    assert_review(client, [])
    assert store.read() == before
    version, _ = seed_draft(store, identity)
    with store.transaction() as state:
        controls.opt_out(
            state["prospects"][identity], actor="fixture-owner",
            reason="Synthetic opt-out evidence", now=1767225601,
        )
    before = copy.deepcopy(store.read())
    prospect = before["prospects"][identity]
    assert_review(client, [{
        "domain": "example.com", "drafts": prospect["outreach_drafts"],
        "approvals": prospect["approvals"], "events": prospect["outreach_events"],
        "suppressed": True,
    }])
    assert store.read() == before
    assert prospect["status"] == "suppressed"
    assert controls.stage(prospect, version) == "OPTED_OUT"
    assert metrics(store.read())["contacts_sent"] == 0
