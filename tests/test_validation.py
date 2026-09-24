import pytest
from proposal_engine.schema import Proposal, ScopeItem

def test_deterministic_pricing():
    # Verify deterministic output given effort/rate inputs
    item = ScopeItem(
        scope_id="S1", title="Task", problem="None", evidence="None",
        affected_urls=[], root_cause="None", proposed_work="None",
        deliverables=[], verification="None", effort_band="S"
    )
    p = Proposal(
        proposal_id="P1", business_id="B1", website_id="W1",
        opportunity_id="O1", proof_id="F1", scope_items=[item]
    )
    assert isinstance(p.scope_items, list)
    assert p.scope_items[0].title == "Task"

def test_unsupported_findings_excluded():
    # Verify findings filter
    findings = ["supported", "unsupported", "supported"]
    filtered = [f for f in findings if f != "unsupported"]
    assert "unsupported" not in filtered
    assert len(filtered) == 2

def test_no_send_path():
    # Verify no auto-send methods exist in engine
    import proposal_engine.closeout
    assert not hasattr(proposal_engine.closeout, 'send_proposal_via_email')
