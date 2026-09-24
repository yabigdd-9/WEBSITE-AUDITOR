"""
Effort estimation engine for proposals.
"""

from dataclasses import dataclass
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class EffortBand(Enum):
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
    UNKNOWN = "UNKNOWN"


@dataclass
class EffortRange:
    min_hours: float
    max_hours: Optional[float]  # None indicates open upper bound


# Effort bands definition from plan
EFFORT_BANDS = {
    EffortBand.XS: EffortRange(min_hours=0.25, max_hours=1.0),
    EffortBand.S: EffortRange(min_hours=1.0, max_hours=3.0),
    EffortBand.M: EffortRange(min_hours=3.0, max_hours=8.0),
    EffortBand.L: EffortRange(min_hours=8.0, max_hours=24.0),
    EffortBand.XL: EffortRange(min_hours=24.0, max_hours=None),
    EffortBand.UNKNOWN: EffortRange(min_hours=0.0, max_hours=0.0),
}


@dataclass
class EffortEstimate:
    band: EffortBand
    min_hours: float
    max_hours: Optional[float]
    estimated_hours: float
    confidence: str  # "low", "medium", "high"


class EffortEngine:
    """Estimates implementation effort from scope, platform and known complexity."""

    def __init__(self):
        self.modifiers = {
            'known_platform': -0.1,  # reduce uncertainty
            'unknown_proprietary_system': 0.2,  # increase uncertainty
            'repeated_proven_recipe': -0.15,  # reduce effort confidence interval
            'sitewide_template_change': 0.25,  # increase effort
        }

    def band_to_range(self, band: str) -> EffortRange:
        """Convert effort band string to EffortRange."""
        try:
            effort_band = EffortBand[band.upper()]
            return EFFORT_BANDS[effort_band]
        except KeyError:
            logger.warning(f"Unknown effort band: {band}")
            return EFFORT_BANDS[EffortBand.UNKNOWN]

    def range_to_band(self, min_hours: float, max_hours: Optional[float]) -> EffortBand:
        """Convert hours range to closest effort band."""
        for band, range_obj in EFFORT_BANDS.items():
            if range_obj.min_hours == min_hours and range_obj.max_hours == max_hours:
                return band
        # If exact match not found, return closest based on midpoint
        if max_hours is None:
            test_value = min_hours * 2  # For XL bands
        else:
            test_value = (min_hours + max_hours) / 2

        closest_band = EffortBand.XS
        min_diff = float('inf')

        for band, range_obj in EFFORT_BANDS.items():
            if range_obj.max_hours is None:
                band_value = range_obj.min_hours * 2
            else:
                band_value = (range_obj.min_hours + range_obj.max_hours) / 2

            diff = abs(band_value - test_value)
            if diff < min_diff:
                min_diff = diff
                closest_band = band

        return closest_band

    def apply_modifiers(self, base_hours: float, modifiers: List[str]) -> Tuple[float, float]:
        """
        Apply modifiers to base hours estimate.
        Returns (modified_min_hours, modified_max_hours)
        """
        total_modifier = 0.0
        for modifier in modifiers:
            if modifier in self.modifiers:
                total_modifier += self.modifiers[modifier]

        # Apply modifier as percentage change
        modified_hours = base_hours * (1 + total_modifier)
        return max(0.25, modified_hours)  # Minimum 15 minutes

    def estimate_effort(
        self,
        scope_type: str,
        num_affected_pages: int,
        cms_framework: str,
        theme_page_builder: str,
        third_party_dependencies: List[str],
        source_code_available: bool,
        proof_factory_complexity: str,
        historical_data_available: bool
    ) -> EffortEstimate:
        """
        Estimate effort based on various factors.
        This is a simplified implementation - in practice would use more sophisticated models.
        """
        # Base estimation logic (simplified)
        base_hours = 2.0  # Starting point

        # Adjust for scope type
        scope_factors = {
            'website_health': 1.0,
            'performance': 1.2,
            'conversion': 1.1,
            'local_visibility': 0.9,
            'modernization': 1.5,
            'security_hygiene': 1.3
        }
        base_hours *= scope_factors.get(scope_type, 1.0)

        # Adjust for number of affected pages
        if num_affected_pages > 10:
            base_hours *= 1.5
        elif num_affected_pages > 5:
            base_hours *= 1.2

        # Adjust for CMS/framework
        cms_factors = {
            'wordpress': 1.0,
            'shopify': 1.1,
            'wix': 0.9,
            'squarespace': 0.9,
            'custom': 1.8,
            'html': 0.8
        }
        base_hours *= cms_factors.get(cms_framework.lower(), 1.2)

        # Adjust for theme/page builder
        builder_factors = {
            'custom': 1.4,
            'elementor': 1.2,
            'divi': 1.2,
            'beaver_builder': 1.1,
            'gutenberg': 1.0,
            'none': 0.8
        }
        base_hours *= builder_factors.get(theme_page_builder.lower(), 1.1)

        # Adjust for third-party dependencies
        base_hours *= (1 + len(third_party_dependencies) * 0.1)

        # Adjust for source code availability
        if not source_code_available:
            base_hours *= 1.3

        # Adjust for proof-factory complexity
        complexity_factors = {
            'low': 0.8,
            'medium': 1.0,
            'high': 1.4
        }
        base_hours *= complexity_factors.get(proof_factory_complexity.lower(), 1.0)

        # Adjust for historical data
        if historical_data_available:
            base_hours *= 0.9  # Slight reduction when we have historical data

        # Determine effort band
        band = self.range_to_band(base_hours, base_hours * 1.5)  # Assume 50% variance

        # Get the range for this band
        effort_range = self.band_to_range(band.value)

        # Calculate confidence based on available information
        confidence_factors = []
        if source_code_available:
            confidence_factors.append("source")
        if cms_framework.lower() in ['wordpress', 'shopify']:
            confidence_factors.append("known_platform")
        if historical_data_available:
            confidence_factors.append("historical_data")
        if len(third_party_dependencies) == 0:
            confidence_factors.append("no_third_party")

        confidence_level = "low"
        if len(confidence_factors) >= 3:
            confidence_level = "high"
        elif len(confidence_factors) >= 2:
            confidence_level = "medium"

        return EffortEstimate(
            band=band,
            min_hours=effort_range.min_hours,
            max_hours=effort_range.max_hours,
            estimated_hours=base_hours,
            confidence=confidence_level
        )

    def get_band_description(self, band: EffortBand) -> str:
        """Get human-readable description of effort band."""
        descriptions = {
            EffortBand.XS: "Extra Small (0.25-1 hours)",
            EffortBand.S: "Small (1-3 hours)",
            EffortBand.M: "Medium (3-8 hours)",
            EffortBand.L: "Large (8-24 hours)",
            EffortBand.XL: "Extra Large (24+ hours)",
            EffortBand.UNKNOWN: "Unknown - requires human estimation"
        }
        return descriptions.get(band, "Unknown band")