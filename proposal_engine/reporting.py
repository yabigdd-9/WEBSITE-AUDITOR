"""
Reporting module for the WEBSITE-AUDITOR proposal engine.
"""

import os
from typing import Dict, Any
from .schema import Proposal


def load_template(template_path: str) -> str:
    """
    Load a template file from the given path.
    """
    with open(template_path, 'r') as f:
        return f.render()


def render_proposal(proposal: Proposal, template_str: str) -> str:
    """
    Render a proposal using the given template string.
    Replaces placeholders of the form {{ variable_name }} with values from the proposal.
    """
    # Convert proposal to a dictionary for easy substitution
    proposal_dict = {
        "proposal_id": proposal.proposal_id,
        "business_id": proposal.business_id,
        "website_id": proposal.website_id,
        "opportunity_id": proposal.opportunity_id,
        "proof_id": proposal.proof_id,
        "proposal_version": proposal.proposal_version,
        "pricing_version": proposal.pricing_version,
        "currency": proposal.currency,
        "scope_items": proposal.scope_items,
        "deliverables": proposal.deliverables,
        "effort": proposal.effort,
        "estimate_band": proposal.estimate_band,
        "assumptions": proposal.assumptions,
        "exclusions": proposal.exclusions,
        "acceptance_criteria": proposal.acceptance_criteria,
        "optional_addons": proposal.optional_addons,
        "evidence_refs": proposal.evidence_refs,
        "limitations": proposal.limitations,
        "status": proposal.status,
        "created_at": proposal.created_at.isoformat(),
        "updated_at": proposal.updated_at.isoformat(),
    }

    # We also need to compute some derived fields for the template
    # For example, executive_summary, what_observed, etc.
    # These are not in the Proposal object but are expected by the template.
    # We'll leave them as empty strings for now; the user must fill them in.
    # Alternatively, we can compute them from scope_items and other data.
    # For simplicity, we'll add placeholder keys and leave them empty.
    # The user can extend this function to compute these fields.

    # Placeholder fields expected by the template
    placeholder_fields = [
        "executive_summary",
        "what_observed",
        "recommended_scope",
        "deliverables",  # we have deliverables but the template might expect a formatted string
        "evidence",
        "estimated_effort",
        "estimated_investment",
        "acceptance_criteria",
        "assumptions",
        "exclusions",
        "optional_items",
        "next_step",
        "limitations",
    ]

    for field in placeholder_fields:
        if field not in proposal_dict:
            proposal_dict[field] = ""

    # Replace placeholders
    rendered = template_str
    for key, value in proposal_dict.items():
        if isinstance(value, list):
            # Convert list to a bullet point string
            if value:
                value_str = "\n".join([f"- {item}" for item in value])
            else:
                value_str = ""
        else:
            value_str = str(value)
        rendered = rendered.replace(f"{{{{ {key} }}}}", value_str)

    return rendered


def generate_markdown_proposal(proposal: Proposal, template_name: str = "quick_fix") -> str:
    """
    Generate a markdown proposal from a proposal object and a template name.
    """
    template_path = f"templates/proposals/{template_name}.md"
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")
    template_str = load_template(template_path)
    return render_proposal(proposal, template_str)
