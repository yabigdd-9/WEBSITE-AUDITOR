"""
Deterministic price calculator for proposals.
"""

import yaml
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
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
class PricingConfig:
    internal_hourly_rate_nzd: float
    minimum_project_nzd: float
    complexity_multiplier: float
    risk_buffer: float
    rounding_increment: float
    version: str


@dataclass
class PriceEstimate:
    low_estimate: float
    target_estimate: float
    high_estimate: float
    calculation_components: Dict[str, float]
    pricing_version: str


class PricingEngine:
    """Calculates deterministic prices based on configuration and effort estimates."""

    def __init__(self, config_dir: str = "config/pricing"):
        self.config_dir = config_dir
        self.pricing_config = self._load_rates_config()
        self.config_version = self.pricing_config.version

    def _load_rates_config(self) -> PricingConfig:
        """Load rates configuration from YAML file."""
        rates_file = os.path.join(self.config_dir, "rates.yaml")
        try:
            with open(rates_file, 'r') as f:
                config = yaml.safe_load(f)

            rates = config.get('rates', {})
            return PricingConfig(
                internal_hourly_rate_nzd=float(rates.get('internal_hourly_rate_nzd', 150.0)),
                minimum_project_nzd=float(rates.get('minimum_project_nzd', 500.0)),
                complexity_multiplier=float(rates.get('complexity_multiplier', 1.0)),
                risk_buffer=float(rates.get('risk_buffer', 0.15)),
                rounding_increment=float(rates.get('rounding_increment', 25.0)),
                version=config.get('version', 'unknown')
            )
        except Exception as e:
            logger.error(f"Failed to load pricing config: {e}")
            # Return default values
            return PricingConfig(
                internal_hourly_rate_nzd=150.0,
                minimum_project_nzd=500.0,
                complexity_multiplier=1.0,
                risk_buffer=0.15,
                rounding_increment=25.0,
                version='default'
            )

    def get_config_version(self) -> str:
        """Get the version of the pricing configuration."""
        return self.config_version

    def effort_band_to_hours(self, effort_band: str) -> Tuple[float, float]:
        """
        Convert effort band to indicative hours range.
        Returns (min_hours, max_hours)
        """
        effort_mapping = {
            'XS': (0.25, 1.0),
            'S': (1.0, 3.0),
            'M': (3.0, 8.0),
            'L': (8.0, 24.0),
            'XL': (24.0, None),  # None indicates open upper bound
            'UNKNOWN': (0.0, 0.0)  # Requires human estimation
        }
        return effort_mapping.get(effort_band.upper(), (0.0, 0.0))

    def calculate_price(
        self,
        effort_band: str,
        complexity_factor: float = 1.0,
        risk_factor: float = 1.0
    ) -> PriceEstimate:
        """
        Calculate price estimate from effort band and modifiers.

        Formula:
        base_hours = midpoint of effort band range
        base_cost = base_hours * internal_hourly_rate
        adjusted_cost = base_cost * complexity_multiplier * complexity_factor
        risk_adjusted_cost = adjusted_cost * (1 + risk_buffer * risk_factor)
        final_cost = max(risk_adjusted_cost, minimum_project_nzd)
        rounded_cost = round(final_cost / rounding_increment) * rounding_increment
        """
        # Get hours range for effort band
        min_hours, max_hours = self.effort_band_to_hours(effort_band)

        if effort_band.upper() == 'UNKNOWN':
            raise ValueError("UNKNOWN effort requires human estimation")

        # Calculate midpoint for estimation
        if max_hours is None:
            # For XL band, use min_hours * 2 as estimate
            estimated_hours = min_hours * 2
        else:
            estimated_hours = (min_hours + max_hours) / 2

        # Base calculation
        base_cost = estimated_hours * self.pricing_config.internal_hourly_rate_nzd

        # Apply complexity multiplier from config and factor
        complexity_adjusted_cost = base_cost * self.pricing_config.complexity_multiplier * complexity_factor

        # Apply risk buffer
        risk_adjusted_cost = complexity_adjusted_cost * (1 + self.pricing_config.risk_buffer * risk_factor)

        # Apply minimum project fee
        final_cost = max(risk_adjusted_cost, self.pricing_config.minimum_project_nzd)

        # Round to increment
        rounded_cost = round(final_cost / self.pricing_config.rounding_increment) * self.pricing_config.rounding_increment

        # Calculate low/high estimates based on hours range
        if max_hours is None:
            # For XL, use a range based on min_hours
            low_hours = min_hours
            high_hours = min_hours * 3  # Arbitrary upper bound for XL
        else:
            low_hours = min_hours
            high_hours = max_hours

        # Calculate low and high estimates using same formula
        low_base = low_hours * self.pricing_config.internal_hourly_rate_nzd
        low_adjusted = low_base * self.pricing_config.complexity_multiplier * complexity_factor
        low_risk_adjusted = low_adjusted * (1 + self.pricing_config.risk_buffer * risk_factor)
        low_final = max(low_risk_adjusted, self.pricing_config.minimum_project_nzd)
        low_rounded = round(low_final / self.pricing_config.rounding_increment) * self.pricing_config.rounding_increment

        high_base = high_hours * self.pricing_config.internal_hourly_rate_nzd
        high_adjusted = high_base * self.pricing_config.complexity_multiplier * complexity_factor
        high_risk_adjusted = high_adjusted * (1 + self.pricing_config.risk_buffer * risk_factor)
        high_final = max(high_risk_adjusted, self.pricing_config.minimum_project_nzd)
        high_rounded = round(high_final / self.pricing_config.rounding_increment) * self.pricing_config.rounding_increment

        # Ensure low <= target <= high
        low_estimate = min(low_rounded, rounded_cost)
        high_estimate = max(high_rounded, rounded_cost)
        target_estimate = rounded_cost

        return PriceEstimate(
            low_estimate=low_estimate,
            target_estimate=target_estimate,
            high_estimate=high_estimate,
            calculation_components={
                'base_hours': estimated_hours,
                'base_cost': base_cost,
                'complexity_adjusted_cost': complexity_adjusted_cost,
                'risk_adjusted_cost': risk_adjusted_cost,
                'final_cost_before_rounding': final_cost,
                'internal_hourly_rate': self.pricing_config.internal_hourly_rate_nzd,
                'complexity_multiplier': self.pricing_config.complexity_multiplier,
                'risk_buffer': self.pricing_config.risk_buffer,
                'rounding_increment': self.pricing_config.rounding_increment,
                'minimum_project_nzd': self.pricing_config.minimum_project_nzd,
                'complexity_factor': complexity_factor,
                'risk_factor': risk_factor,
                'pricing_config_version': self.config_version
            },
            pricing_version=self.config_version
        )

    def get_pricing_bands(self) -> Dict:
        """Get pricing bands configuration."""
        bands_file = os.path.join(self.config_dir, "bands.yaml")
        try:
            with open(bands_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load bands config: {e}")
            return {}

    def get_packages(self) -> Dict:
        """Get packages configuration."""
        packages_file = os.path.join(self.config_dir, "packages.yaml")
        try:
            with open(packages_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load packages config: {e}")
            return {}

    def get_addons(self) -> Dict:
        """Get addons configuration."""
        addons_file = os.path.join(self.config_dir, "addons.yaml")
        try:
            with open(addons_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load addons config: {e}")
            return {}