import copy
import hashlib
import json

import pytest

from scripts import approval_controls as controls
from scripts.cloud_opportunities import digest

NOW = 1767225600
RECIPIENT = hashlib.sha256(b"synthetic-recipient-no-email").hexdigest()


@pytest.fixture
def prospect():
    body = dict(kind="INTERNAL_PROPOSAL_DRAFT", items=[], business_name="Synthetic fixture")
    version = digest(body)
    return dict(
        domain="example.com",
        status="complete",
        draft="Unsent internal scope",
        proposal_version=version,
        proposal_versions=[{**body, "version_sha256": version}],
    )


def prepare(prospect):
    return controls.prepare_outreach(
        prospect, recipient_hash=RECIPIENT, body="Synthetic internal message", now=NOW
    )


def permission(prospect):
    prospect["contact_permission"] = dict(
        recipient_hash=RECIPIENT,
        consent_verified=True,
        consent_evidence_sha256="a" * 64,
        recipient_verified=True,
        sender_identified=True,
        unsubscribe_functional=True,
        opted_out=False,
        checked_at=NOW,
    )


def approve(prospect, version):
    controls.review_outreach(
        prospect, version, actor="fixture-owner", reason="Review fixture", now=NOW
    )
    controls.approve_outreach(
        prospect, version, actor="fixture-owner", reason="Approve exact fixture", now=NOW
    )


def test_proposal_approval_never_approves_outreach(prospect):
    controls.approve_proposal(
        prospect,
        prospect["proposal_version"],
        actor="fixture-owner",
        reason="Scope approved",
        now=NOW,
    )
    version = prepare(prospect)
    permission(prospect)
    assert controls.eligibility(prospect, version, now=NOW) is False
    transport = controls.SandboxTransport()
    with pytest.raises(ValueError):
        controls.send_sandbox(prospect, version, now=NOW, transport=transport)
    assert transport.calls == 0


def test_stages_exact_approval_and_duplicate_simulation(prospect):
    version = prepare(prospect)
    assert prepare(prospect) == version
    assert len(prospect["outreach_drafts"]) == 1
    with pytest.raises(ValueError):
        controls.approve_outreach(
            prospect, version, actor="fixture-owner", reason="Bypass review", now=NOW
        )
    approve(prospect, version)
    permission(prospect)
    assert controls.mark_send_eligible(prospect, version, now=NOW)
    transport = controls.SandboxTransport()
    result = controls.send_sandbox(prospect, version, now=NOW, transport=transport)
    assert result["sandbox"] is True
    assert result["external_sends"] == 0
    assert controls.send_sandbox(prospect, version, now=NOW, transport=transport) == result
    assert transport.calls == 1
    assert [e["status"] for e in prospect["outreach_events"]] == [
        "DRAFT",
        "REVIEW",
        "APPROVED",
        "SEND_ELIGIBLE",
        "SENT",
    ]
    assert all(e["sandbox_only"] for e in prospect["outreach_events"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("recipient_verified", False),
        ("consent_verified", False),
        ("consent_evidence_sha256", "missing"),
        ("sender_identified", False),
        ("unsubscribe_functional", False),
        ("opted_out", True),
        ("recipient_hash", "b" * 64),
        ("checked_at", NOW - 8 * 86400),
    ],
)
def test_permission_and_suppression_gates(prospect, field, value):
    version = prepare(prospect)
    approve(prospect, version)
    permission(prospect)
    prospect["contact_permission"][field] = value
    assert controls.mark_send_eligible(prospect, version, now=NOW) is False
    assert controls.stage(prospect, version) == "BLOCKED"


def test_immediate_pre_simulation_recheck_and_revocation(prospect):
    version = prepare(prospect)
    approve(prospect, version)
    permission(prospect)
    assert controls.mark_send_eligible(prospect, version, now=NOW)
    prospect["contact_permission"]["opted_out"] = True
    transport = controls.SandboxTransport()
    with pytest.raises(ValueError):
        controls.send_sandbox(prospect, version, now=NOW, transport=transport)
    assert transport.calls == 0
    prospect["contact_permission"]["opted_out"] = False
    approve(prospect, version)
    assert controls.mark_send_eligible(prospect, version, now=NOW)
    controls.revoke_outreach(
        prospect, version, actor="fixture-owner", reason="Changed scope", now=NOW
    )
    with pytest.raises(ValueError):
        controls.send_sandbox(prospect, version, now=NOW, transport=transport)
    assert transport.calls == 0


def test_changed_content_or_proposal_invalidates_approval(prospect):
    version = prepare(prospect)
    approve(prospect, version)
    permission(prospect)
    before = copy.deepcopy(prospect)
    prospect["outreach_drafts"][0]["body"] = "tampered"
    assert controls.eligibility(prospect, version, now=NOW) is False
    prospect = before
    prospect["proposal_version"] = "b" * 64
    assert controls.eligibility(prospect, version, now=NOW) is False


def test_opt_out_is_sticky_and_clears_current_work(prospect):
    version = prepare(prospect)
    approve(prospect, version)
    permission(prospect)
    controls.opt_out(prospect, actor="fixture-owner", reason="Opt-out evidence recorded", now=NOW)
    assert prospect["status"] == "suppressed"
    assert prospect["draft"] is None
    assert prospect["proposal_version"] is None
    assert controls.stage(prospect, version) == "OPTED_OUT"
    assert controls.eligibility(prospect, version, now=NOW) is False
    with pytest.raises(ValueError):
        prepare(prospect)


def test_live_transport_injection_rejected_and_failures_redacted(prospect, monkeypatch):
    version = prepare(prospect)
    approve(prospect, version)
    permission(prospect)
    controls.mark_send_eligible(prospect, version, now=NOW)

    class UnapprovedTransport:
        def send(self, key):
            pytest.fail("External transport invoked")

    unapproved = UnapprovedTransport()
    with pytest.raises(ValueError):
        controls.send_sandbox(prospect, version, now=NOW, transport=unapproved)
    transport = controls.SandboxTransport()

    def fail(key):
        raise RuntimeError("password=private-test-only")

    monkeypatch.setattr(transport, "send", fail)
    with pytest.raises(ValueError, match="Sandbox transport failed"):
        controls.send_sandbox(prospect, version, now=NOW, transport=transport)
    assert controls.stage(prospect, version) == "FAILED"
    assert "private-test-only" not in json.dumps(prospect)


def test_owner_identity_and_reason_are_required(prospect):
    for actor, reason in (("", "review"), ("owner", "")):
        with pytest.raises(ValueError):
            controls.approve_proposal(
                prospect, prospect["proposal_version"], actor=actor, reason=reason, now=NOW
            )


def test_sandbox_rate_cap_is_enforced(prospect):
    permission(prospect)
    transport = controls.SandboxTransport()
    for index in range(4):
        version = controls.prepare_outreach(
            prospect, recipient_hash=RECIPIENT, body=f"Synthetic distinct message {index}", now=NOW
        )
        approve(prospect, version)
        assert controls.mark_send_eligible(prospect, version, now=NOW)
        if index < 3:
            controls.send_sandbox(prospect, version, now=NOW, transport=transport)
        else:
            with pytest.raises(ValueError, match="daily cap"):
                controls.send_sandbox(prospect, version, now=NOW, transport=transport)
    assert transport.calls == 3


def test_approval_and_sandbox_history_persist_without_counting_real_sends(prospect):
    import tempfile
    from pathlib import Path

    from scripts.cloud_prospect_pipeline import metrics
    from scripts.pipeline_store import PipelineStore

    with tempfile.TemporaryDirectory() as directory:
        store = PipelineStore(Path(directory) / "pipeline.sqlite3")
        identity = hashlib.sha256(b"example.com").hexdigest()
        with store.transaction(bootstrap=True) as state:
            state["prospects"][identity] = prospect
            version = prepare(prospect)
            approve(prospect, version)
            permission(prospect)
            controls.mark_send_eligible(prospect, version, now=NOW)
            controls.send_sandbox(prospect, version, now=NOW, transport=controls.SandboxTransport())
        with store.transaction() as state:
            transport = controls.SandboxTransport()
            result = controls.send_sandbox(
                state["prospects"][identity], version, now=NOW, transport=transport
            )
            assert result["external_sends"] == 0
            assert transport.calls == 0
            assert metrics(state)["contacts_sent"] == 0
        with pytest.raises(ValueError):
            with store.transaction() as state:
                state["prospects"][identity]["approvals"] = []
