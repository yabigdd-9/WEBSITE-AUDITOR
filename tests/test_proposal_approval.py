"""
Tests for approval module.
"""

from proposal_engine.approval import generate_approval_hash, create_human_review_packet, is_approval_valid
from proposal_engine.schema import Proposal, ScopeItem


def test_approval_hash():
    proposal = Proposal(
        proposal_id="p1",
        business_id="b1",
        website_id="w1",
        opportunity_id="o1",
        proof_id="prf1",
    )
    hash1 = generate_approval_hash(proposal)
    # Change something in the proposal
    proposal.effort = "M"
    hash2 = generate_approval_hash(proposal)
    assert hash1 != hash2


def test_human_review_packet():
    proposal = Proposal(
        proposal_id="p1",
        business_id="b1",
        website_id="w1",
        opportunity_id="o1",
        proof_id="prf1",
    )
    packet = create_human_review_packet(proposal)
    assert "approval_hash" in packet
    assert packet["approval_hash"] == generate_approval_hash(proposal)
    assert "calculation" in packet
    assert "risks" in packet
    assert "controls" in packet


def test_approval_invalidated_after_edit():
    proposal = Proposal(
        proposal_id="p1",
        business_id="b1",
        website_id="w1",
        opportunity_id="o1",
        proof_id="prf1",
    )
    packet = create_human_review_packet(proposal)
    # Edit the proposal
    proposal.effort = "M"
    assert not is_approval_valid(packet, proposal)
    # If we don't edit, it should be valid
    proposal2 = Proposal(
        proposal_id="p1",
        business_id="b1",
        website_id="w1",
        opportunity_id="o1",
        proof_id="prf1",
    )
    assert is_approval_valid(packet, proposal2)
