"""
Integration test for the proposal pipeline.
"""

from proposal_engine.scope import map_finding_to_scope
from proposal_engine.effort import hours_to_effort_band
from proposal_engine.pricing import calculate_quote
from proposal_engine.schema import Proposal, ScopeItem
from proposal_engine.reporting import generate_markdown_proposal
import tempfile
import os


def test_proposal_pipeline():
    # Step 1: Map a finding to a scope item
    finding = {
        "id": "f1",
        "title": "Missing meta description",
        "description": "The homepage is missing a meta description.",
        "evidence": "Seen on homepage",
        "urls": ["https://example.com/"],
        "root_cause": "Not set in CMS",
        "recommended_action": "Add meta description",
        "deliverables": ["Updated meta description"],
        "verification_method": "View source",
        "effort_band": "XS",
        "dependencies": [],
        "risk": "LOW",
    }
    scope_item = map_finding_to_scope(finding)
    assert isinstance(scope_item, ScopeItem)

    # Step 2: Determine effort band (we already have it from finding, but we can also compute from hours)
    # For demonstration, we'll use the effort_band from the finding
    effort_band = scope_item.effort_band  # "XS"

    # Step 3: Load pricing configuration (we'll create a mock config)
    rates_config = {
        "internal_hourly_rate_nzd": 150,
        "minimum_project_nzd": 500,
        "complexity_multiplier": 1.0,
        "risk_buffer": 0.1,
        "rounding_increment": 5,
        "pricing_version": 1,
    }
    # Step 4: Calculate quote based on effort band
    # We'll convert effort band to hours using midpoint (for XS: (0.25+1)/2 = 0.625)
    from proposal_engine.effort import midpoint_hours
    estimated_hours = midpoint_hours(effort_band)
    quote = calculate_quote(
        estimated_hours=estimated_hours,
        rates_config=rates_config,
        complexity_modifier=1.0,
        risk_modifier=1.0,
    )

    # Step 5: Create a proposal
    proposal = Proposal(
        proposal_id="prop-001",
        business_id="biz-001",
        website_id="web-001",
        opportunity_id="opp-001",
        proof_id="proof-001",
        scope_items=[scope_item],
        effort=effort_band,
        estimate_band="XS-S",  # placeholder
        status="PROPOSAL_DRAFTED",
    )
    proposal.effort = effort_band
    # We could also set the estimate_band based on effort, but we'll leave it as is.

    # Step 6: Generate markdown proposal using a template
    # We'll use the quick_fix template we created earlier.
    # Since we are in a test environment, we can use a temporary directory or the existing templates.
    # We'll assume the templates are in the standard location relative to the current directory.
    # We'll change the current directory to the project root? We'll just use the template path as is.
    # We'll create a temporary template for testing to avoid relying on the existing template content.
    # Instead, we'll test the reporting functions separately; for integration we just want to see that the modules work together.
    # We'll skip the actual markdown generation and just check that the proposal object is correctly populated.
    assert proposal.proposal_id == "prop-001"
    assert len(proposal.scope_items) == 1
    assert proposal.scope_items[0].title == "Missing meta description"
    assert proposal.effort == "XS"
    # We can also check that the quote was calculated (we don't store it in the proposal, but we can use it)
    assert quote["target_estimate"] > 0

    # If we want to test the markdown generation, we would need to create a template file.
    # For simplicity, we'll just test that the reporting function doesn't crash when given a template string.
    from proposal_engine.reporting import render_proposal
    template_str = "# Proposal: {{ proposal_id }}\n\n## Executive Summary\n{{ executive_summary }}"
    rendered = render_proposal(proposal, template_str)
    assert "prop-001" in rendered
    assert "Executive Summary" in rendered
