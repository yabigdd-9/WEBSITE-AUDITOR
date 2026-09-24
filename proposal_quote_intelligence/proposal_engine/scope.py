"""
Scope generation engine for converting technical findings to proposal scope.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class Finding:
    """Represents a technical finding from an audit."""
    finding_id: str
    title: str
    description: str
    severity: str  # low, medium, high, critical
    category: str  # e.g., "broken_links", "performance", "seo"
    location: str  # URL or file path
    evidence: str  # proof of the issue
    platform: str  # CMS, framework, etc.
    remediation_effort: str  # estimated effort for fix
    verification_method: str  # how to verify the fix


@dataclass
class ScopeItem:
    """Represents a scoped item for a proposal."""
    scope_id: str
    title: str
    problem: str
    evidence: str
    affected_urls: List[str]
    root_cause: str
    proposed_work: str
    deliverables: List[str]
    verification: str
    effort_band: str
    dependencies: List[str]
    risk: str
    finding_ids: List[str]


class ScopeEngine:
    """Converts technical findings into proposal scope items."""

    def __init__(self):
        # Mapping from finding categories to scope families
        self.category_to_scope_family = {
            'broken_links': 'website_health',
            'redirect_issues': 'website_health',
            'indexability': 'website_health',
            'technical_hygiene': 'website_health',
            'ssl_certificate': 'website_health',
            'page_speed': 'performance',
            'resource_optimization': 'performance',
            'render_blocking': 'performance',
            'browser_caching': 'performance',
            'cta_issues': 'conversion',
            'form_usability': 'conversion',
            'booking_flow': 'conversion',
            'trust_signals': 'conversion',
            'local_business_schema': 'local_visibility',
            'nap_consistency': 'local_visibility',
            'google_my_business': 'local_visibility',
            'local_citations': 'local_visibility',
            'outdated_components': 'modernization',
            'page_builder_cleanup': 'modernization',
            'responsive_issues': 'modernization',
            'security_headers': 'security_hygiene',
            'vulnerable_js': 'security_hygiene',
            'malware_scan': 'security_hygiene'
        }

        # Mapping from scope families to templates
        self.scope_family_templates = {
            'website_health': {
                'title_template': "Fix {issue_type} on {url_count} pages",
                'problem_template': "Found {issue_type} affecting {url_count} pages, impacting user experience and SEO",
                'work_template': "Identify and fix {issue_type} across {url_count} pages",
                'deliverables': ["Issue identification report", "Fixed URLs", "Verification report"],
                'verification': "All identified issues resolved and verified"
            },
            'performance': {
                'title_template': "Optimize {issue_type} for {url_count} pages",
                'problem_template': "Slow {issue_type} affecting {url_count} pages, impacting user experience and SEO",
                'work_template': "Optimize {issue_type} across {url_count} pages to improve loading times",
                'deliverables': ["Optimization report", "Before/after performance metrics", "Optimized assets"],
                'verification': "Performance improvements verified with testing tools"
            },
            'conversion': {
                'title_template': "Improve {issue_type} for better conversion",
                'problem_template': "Issues with {issue_type} reducing conversion rates on {url_count} pages",
                'work_template': "Enhance {issue_type} on {url_count} pages to improve user flow and conversion",
                'deliverables': ["Design mockups", "Implemented changes", "A/B test results"],
                'verification': "Conversion improvements verified through analytics"
            },
            'local_visibility': {
                'title_template': "Enhance local visibility with {issue_type}",
                'problem_template': "Missing or incorrect {issue_type} impacting local search visibility",
                'work_template': "Implement and verify {issue_type} for improved local search presence",
                'deliverables': ["Implementation report", "Verification in local search tools", "NAP consistency report"],
                'verification': "Local visibility improvements verified in search results"
            },
            'modernization': {
                'title_template': "Modernize {issue_type} across site",
                'problem_template': "Outdated {issue_type} affecting {url_count} pages, impacting user experience",
                'work_template': "Update {issue_type} to modern standards across {url_count} pages",
                'deliverables': ["Updated components", "Cross-browser testing report", "Responsive verification"],
                'verification': "Modernization verified through manual and automated testing"
            },
            'security_hygiene': {
                'title_template': "Improve security with {issue_type}",
                'problem_template': "Security vulnerability {issue_type} exposing site to risks",
                'work_template': "Implement {issue_type} to enhance site security",
                'deliverables': ["Security implementation report", "Verification of security headers", "Security scan results"],
                'verification': "Security improvements verified through security scanning"
            }
        }

    def map_findings_to_scope(self, findings: List[Finding]) -> List[ScopeItem]:
        """
        Map technical findings to scope items.
        Groups related findings under scope items based on category and location.
        """
        if not findings:
            return []

        # Group findings by category and platform
        grouped_findings = self._group_findings(findings)

        # Convert each group to a scope item
        scope_items = []
        for group_key, group_findings in grouped_findings.items():
            scope_item = self._create_scope_item(group_key, group_findings)
            if scope_item:
                scope_items.append(scope_item)

        # Deduplicate scope items
        scope_items = self._deduplicate_scope_items(scope_items)

        return scope_items

    def _group_findings(self, findings: List[Finding]) -> Dict[str, List[Finding]]:
        """Group findings by category and platform for scope creation."""
        groups = {}

        for finding in findings:
            # Determine scope family from category
            scope_family = self.category_to_scope_family.get(
                finding.category.lower(),
                'website_health'  # default fallback
            )

            # Create group key based on scope family and platform
            group_key = f"{scope_family}:{finding.platform}"

            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(finding)

        return groups

    def _create_scope_item(self, group_key: str, findings: List[Finding]) -> Optional[ScopeItem]:
        """Create a scope item from a group of related findings."""
        if not findings:
            return None

        # Parse group key
        try:
            scope_family, platform = group_key.split(':', 1)
        except ValueError:
            scope_family, platform = group_key, 'unknown'

        # Get template for scope family
        template = self.scope_family_templates.get(
            scope_family,
            self.scope_family_templates['website_health']  # fallback
        )

        # Aggregate information from findings
        all_urls = list(set([f.location for f in findings if f.location]))
        all_evidence = "; ".join([f.evidence for f in findings if f.evidence])
        all_finding_ids = [f.finding_id for f in findings]

        # Determine primary issue type from findings
        issue_types = list(set([f.category for f in findings]))
        primary_issue = issue_types[0] if issue_types else "technical issues"

        # Calculate effort based on findings
        effort_band = self._calculate_effort_band(findings)

        # Create scope item
        scope_item = ScopeItem(
            scope_id=f"scope_{len(findings)}_{hash(str(findings)) % 10000:04d}",
            title=template['title_template'].format(
                issue_type=primary_issue.replace('_', ' '),
                url_count=len(all_urls)
            ),
            problem=template['problem_template'].format(
                issue_type=primary_issue.replace('_', ' '),
                url_count=len(all_urls)
            ),
            evidence=all_evidence[:500] + "..." if len(all_evidence) > 500 else all_evidence,  # Limit evidence length
            affected_urls=all_urls[:10],  # Limit to first 10 URLs
            root_cause=f"{primary_issue} issues on {platform} platform",
            proposed_work=template['work_template'].format(
                issue_type=primary_issue.replace('_', ' '),
                url_count=len(all_urls)
            ),
            deliverables=template['deliverables'].copy(),
            verification=template['verification'],
            effort_band=effort_band,
            dependencies=[],  # To be filled by integration with other systems
            risk=self._assess_risk(findings),
            finding_ids=all_finding_ids
        )

        return scope_item

    def _calculate_effort_band(self, findings: List[Finding]) -> str:
        """Calculate effort band based on findings."""
        # Simple heuristic: more findings = higher effort
        # In practice, this would integrate with the effort engine
        num_findings = len(findings)
        if num_findings <= 2:
            return "XS"
        elif num_findings <= 5:
            return "S"
        elif num_findings <= 10:
            return "M"
        elif num_findings <= 20:
            return "L"
        else:
            return "XL"

    def _assess_risk(self, findings: List[Finding]) -> str:
        """Assess risk level based on findings."""
        risk_levels = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for finding in findings:
            severity = finding.severity.lower()
            if severity in risk_levels:
                risk_levels[severity] += 1

        if risk_levels["critical"] > 0:
            return "HIGH"
        elif risk_levels["high"] > 2:
            return "HIGH"
        elif risk_levels["high"] > 0 or risk_levels["medium"] > 3:
            return "MEDIUM"
        else:
            return "LOW"

    def _deduplicate_scope_items(self, scope_items: List[ScopeItem]) -> List[ScopeItem]:
        """
        Remove duplicate scope items based on title and affected URLs.
        Implements the deduplication rule from the plan.
        """
        if not scope_items:
            return []

        # Track seen combinations of title and URLs
        seen = set()
        unique_items = []

        for item in scope_items:
            # Create a signature based on title and sorted URLs
            url_signature = tuple(sorted(item.affected_urls))
            signature = (item.title.lower(), url_signature)

            if signature not in seen:
                seen.add(signature)
                unique_items.append(item)
            else:
                logger.info(f"Deduplicated scope item: {item.title}")

        return unique_items

    def validate_scope_item(self, scope_item: ScopeItem) -> bool:
        """
        Validate that a scope item meets the requirements.
        Implements the acceptance gate rule: every scope item maps to verified evidence.
        """
        if not scope_item.evidence or len(scope_item.evidence.strip()) == 0:
            logger.warning(f"Scope item {scope_item.scope_id} has no evidence")
            return False

        if not scope_item.finding_ids or len(scope_item.finding_ids) == 0:
            logger.warning(f"Scope item {scope_item.scope_id} has no finding IDs")
            return False

        if not scope_item.affected_urls or len(scope_item.affected_urls) == 0:
            logger.warning(f"Scope item {scope_item.scope_id} has no affected URLs")
            return False

        return True