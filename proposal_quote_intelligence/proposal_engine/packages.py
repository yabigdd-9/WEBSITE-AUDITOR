"""
Package intelligence engine for grouping scope items into understandable packages.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Package:
    """Represents a service package."""
    package_id: str
    name: str
    description: str
    included_scope: List[str]  # scope item IDs
    excluded_scope: List[str]  # scope item IDs that are explicitly excluded
    effort_band: str
    estimate_band: str  # Could be a range like "S-M"
    base_price: float
    optional_addons: List[str]  # addon IDs


@dataclass
class PackageRecommendation:
    """Recommended package for a set of scope items."""
    package: Package
    fit_score: float  # 0.0 to 1.0, how well the package fits the scope
    missing_scope: List[str]  # scope items not covered by package
    extra_scope: List[str]  # scope items covered by package but not needed
    recommended_addons: List[str]  # addons that would enhance the package


class PackageIntelligenceEngine:
    """Matches related scope items into understandable packages only where evidence supports grouping them."""

    def __init__(self):
        # In a real implementation, these would be loaded from config/packages.yaml
        self.packages = self._load_default_packages()

        # package_intelligence rules from plan
        self.rules = {
            'do_not_upsell_unrelated_work': True,
            'primary_package_solves_primary_verified_problem': True,
            'optional_work_remains_clearly_optional': True
        }

    def _load_default_packages(self) -> Dict[str, Package]:
        """Load default package definitions."""
        # These would normally be loaded from packages.yaml
        return {
            'local_seo_starter': Package(
                package_id='local_seo_starter',
                name='Local SEO Starter',
                description='Essential local visibility improvements',
                included_scope=['local_business_schema', 'google_my_business_optimization', 'napa_consistency_check'],
                excluded_scope=['content_creation', 'paid_advertising'],
                effort_band='S',
                estimate_band='S',
                base_price=1500.0,
                optional_addons=['review_monitoring', 'local_content_creation']
            ),
            'technical_performance': Package(
                package_id='technical_performance',
                name='Technical Performance Package',
                description='Site speed and technical health improvements',
                included_scope=['image_optimization', 'browser_caching', 'css_js_minification', 'redirect_cleanup'],
                excluded_scope=['server_upgrade', 'architecture_redesign'],
                effort_band='M',
                estimate_band='M',
                base_price=3500.0,
                optional_addons=['cdn_setup', 'advanced_caching']
            ),
            'conversion_optimization': Package(
                package_id='conversion_optimization',
                name='Conversion Optimization Package',
                description='Improve lead generation and sales funnel',
                included_scope=['cta_optimization', 'form_usability_improvements', 'booking_flow_optimization', 'trust_signal_enhancement'],
                excluded_scope=['complete_redesign', 'ecommerce_platform_change'],
                effort_band='L',
                estimate_band='L',
                base_price=6000.0,
                optional_addons=['ab_testing_framework', 'heatmap_analysis']
            ),
            'focused_fix': Package(
                package_id='focused_fix',
                name='Focused Fix',
                description='One narrow problem, short implementation',
                included_scope=[],  # To be determined based on scope
                excluded_scope=[],
                effort_band='XS',
                estimate_band='XS',
                base_price=500.0,
                optional_addons=[]
            )
        }

    def recommend_package(self, scope_items: List[Any]) -> PackageRecommendation:
        """
        Recommend the best package for a set of scope items.
        Implements package_intelligence logic from plan.
        """
        if not scope_items:
            # Return a basic focused fix package for empty scope
            return PackageRecommendation(
                package=self.packages['focused_fix'],
                fit_score=0.0,
                missing_scope=[],
                extra_scope=[],
                recommended_addons=[]
            )

        # Convert scope items to scope IDs if they're objects
        scope_item_ids = []
        for item in scope_items:
            if hasattr(item, 'scope_id'):
                scope_item_ids.append(item.scope_id)
            elif isinstance(item, str):
                scope_item_ids.append(item)
            else:
                # Try to get ID from item
                scope_item_ids.append(str(item))

        # Find the best fitting package
        best_package = None
        best_fit_score = 0.0

        for package_id, package in self.packages.items():
            fit_score = self._calculate_package_fit(package, scope_item_ids)
            if fit_score > best_fit_score:
                best_fit_score = fit_score
                best_package = package

        # If no good fit, create a custom focused fix package
        if best_fit_score < 0.3:  # Threshold for acceptable fit
            best_package = self._create_custom_focused_fix(scope_item_ids)
            best_fit_score = 0.8  # Custom fit is good by definition

        # Calculate missing and extra scope
        included_scope_set = set(best_package.included_scope)
        scope_item_set = set(scope_item_ids)

        missing_scope = list(scope_item_set - included_scope_set)
        extra_scope = list(included_scope_set - scope_item_set)

        # Recommend addons based on scope
        recommended_addons = self._recommend_addons(scope_item_ids, best_package.optional_addons)

        return PackageRecommendation(
            package=best_package,
            fit_score=best_fit_score,
            missing_scope=missing_scope,
            extra_scope=extra_scope,
            recommended_addons=recommended_addons
        )

    def _calculate_package_fit(self, package: Package, scope_item_ids: List[str]) -> float:
        """
        Calculate how well a package fits the given scope items.
        Returns score between 0.0 and 1.0.
        """
        if not package.included_scope:
            # Empty package (like focused_fix) fits anything poorly but is better than nothing
            return 0.1

        scope_item_set = set(scope_item_ids)
        package_scope_set = set(package.included_scope)

        if not package_scope_set:
            return 0.0

        # Calculate overlap
        overlap = len(scope_item_set.intersection(package_scope_set))
        package_coverage = overlap / len(package_scope_set) if package_scope_set else 0
        scope_coverage = overlap / len(scope_item_set) if scope_item_set else 0

        # Weighted score - we want good coverage of the package AND good coverage of scope
        # But we penalize if package has lots of extra stuff we don't need
        fit_score = (package_coverage * 0.6) + (scope_coverage * 0.4)

        # Apply package intelligence rules
        if self.rules['do_not_upsell_unrelated_work'] and scope_coverage < 0.5:
            # If we're covering less than 50% of the scope with this package, it might be upselling
            fit_score *= 0.7

        return min(1.0, fit_score)

    def _create_custom_focused_fix(self, scope_item_ids: List[str]) -> Package:
        """Create a custom focused fix package for the given scope items."""
        return Package(
            package_id=f'custom_focused_fix_{hash(str(scope_item_ids)) % 10000:04d}',
            name='Custom Focused Fix',
            description='Tailored fix for specific scope items',
            included_scope=scope_item_ids,
            excluded_scope=[],
            effort_band='XS',  # Would be calculated based on actual scope
            estimate_band='XS',
            base_price=500.0,  # Would be calculated
            optional_addons=[]
        )

    def _recommend_addons(self, scope_item_ids: List[str], available_addons: List[str]) -> List[str]:
        """
        Recommend addons based on scope items.
        Implements evidence-gated addons logic.
        """
        # In a real implementation, this would check evidence for addon relevance
        # For now, return a subset of available addons
        recommended = []

        # Simple heuristic: recommend up to 2 addons for non-empty scope
        if scope_item_ids:
            # Just take first couple addons as example
            recommended = available_addons[:min(2, len(available_addons))]

        return recommended

    def validate_package_recommendation(self, recommendation: PackageRecommendation) -> bool:
        """
        Validate that a package recommendation follows package_intelligence rules.
        """
        # Rule: Do not upsell unrelated work
        if recommendation.fit_score < 0.3:
            logger.warning("Package recommendation has low fit score - may be upselling unrelated work")
            return False

        # Rule: Primary package solves primary verified problem
        # This would be checked by ensuring the package covers the main scope items

        # Rule: Optional work remains clearly optional
        # This is handled by separating included_scope from optional_addons

        return True

    def get_available_packages(self) -> List[Package]:
        """Get all available packages."""
        return list(self.packages.values())

    def get_package_by_id(self, package_id: str) -> Optional[Package]:
        """Get a package by its ID."""
        return self.packages.get(package_id)