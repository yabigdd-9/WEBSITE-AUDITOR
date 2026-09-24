import pytest
from proposal_engine.schema import Proposal, ScopeItem

def get_synthetic_pricing_fixtures():
    return [
        Proposal(id=f"SYNTH-{i}", scope=[ScopeItem(name=f"Service-{i}", effort=i*10, rate=100)])
        for i in range(1, 6)
    ]
