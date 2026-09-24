"""
Tests for the template engine.
"""

import os
import tempfile
from datetime import datetime
from proposal_engine.templates import TemplateEngine
from proposal_engine.schema import Proposal, ScopeItem


def test_template_engine_initialization():
    engine = TemplateEngine()
    assert engine.default_template == "quick_fix"
    assert engine.template_dir == "templates/proposals"
    assert engine._template_map == {}


def test_register_and_select_template():
    engine = TemplateEngine()
    engine.register_template("ecommerce", "shopify", "medium", "shopify_medium")
    assert engine.select_template("ecommerce", "shopify", "medium") == "shopify_medium"
    # Test fallback to default
    assert engine.select_template("ecommerce", "shopify", "high") == "quick_fix"
    assert engine.select_template("saas", "wordpress", "low") == "quick_fix"


def test_render_template():
    # Create a temporary directory for templates
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple template file
        template_path = os.path.join(tmpdir, "test_template.md")
        with open(template_path, 'w') as f:
            f.write("Proposal ID: {{ proposal_id }}\nBusiness ID: {{ business_id }}")

        engine = TemplateEngine(template_dir=tmpdir, default_template="test_template")
        # Create a minimal proposal
        proposal = Proposal(
            proposal_id="prop_123",
            business_id="biz_456",
            website_id="web_789",
            opportunity_id="opp_012",
            proof_id="proof_345",
            scope_items=[
                ScopeItem(
                    scope_id="scope_1",
                    title="Test Scope",
                    problem="Test problem",
                    evidence="Test evidence",
                    affected_urls=["http://example.com"],
                    root_cause="Test root cause",
                    proposed_work="Test work",
                    deliverables=["Test deliverable"],
                    verification="Test verification",
                    effort_band="M",
                    risk="LOW",
                )
            ],
            status="NOT_READY",
        )
        rendered = engine.render("test_template", proposal)
        assert "Proposal ID: prop_123" in rendered
        assert "Business ID: biz_456" in rendered


def test_render_template_not_found():
    engine = TemplateEngine()
    proposal = Proposal(
        proposal_id="prop_123",
        business_id="biz_456",
        website_id="web_789",
        opportunity_id="opp_012",
        proof_id="proof_345",
        status="NOT_READY",
    )
    try:
        engine.render("non_existent_template", proposal)
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass  # Expected