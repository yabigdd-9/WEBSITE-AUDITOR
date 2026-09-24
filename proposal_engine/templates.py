"""
Template selection for the WEBSITE-AUDITOR proposal engine.
"""

import os
from typing import Dict, Optional, Tuple
from .schema import Proposal
from .reporting import render_proposal


class TemplateEngine:
    def __init__(self, template_dir: str = "templates/proposals", default_template: str = "quick_fix"):
        """
        Initialize the template engine.

        Args:
            template_dir: Directory where template files are stored (relative to this file or absolute).
            default_template: Template name to use when no match is found.
        """
        self.template_dir = template_dir
        self.default_template = default_template
        # Mapping from (business_type, tech_stack, audit_severity) to template name
        self._template_map: Dict[Tuple[str, str, str], str] = {}

    def register_template(self, business_type: str, tech_stack: str, audit_severity: str, template_name: str) -> None:
        """
        Register a template for a specific combination of business_type, tech_stack, and audit_severity.

        Args:
            business_type: The type of business (e.g., 'ecommerce', 'saas').
            tech_stack: The technology stack (e.g., 'wordpress', 'react', 'shopify').
            audit_severity: The severity of the audit (e.g., 'low', 'medium', 'high').
            template_name: The name of the template file (without extension) to use.
        """
        key = (business_type, tech_stack, audit_severity)
        self._template_map[key] = template_name

    def select_template(self, business_type: str, tech_stack: str, audit_severity: str) -> str:
        """
        Select a template name based on business_type, tech_stack, and audit_severity.

        Args:
            business_type: The type of business.
            tech_stack: The technology stack.
            audit_severity: The severity of the audit.

        Returns:
            The template name to use (without extension).
        """
        key = (business_type, tech_stack, audit_severity)
        return self._template_map.get(key, self.default_template)

    def render(self, template_name: str, proposal: Proposal) -> str:
        """
        Render a proposal using the specified template.

        Args:
            template_name: The name of the template file (without extension).
            proposal: The proposal object to render.

        Returns:
            The rendered markdown string.

        Raises:
            FileNotFoundError: If the template file does not exist.
        """
        template_path = os.path.join(self.template_dir, f"{template_name}.md")
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")
        with open(template_path, 'r') as f:
            template_str = f.read()
        return render_proposal(proposal, template_str)