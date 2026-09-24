"""
Feature-state resolver for capabilities.
"""

import yaml
import os
from typing import Dict, Optional

class FeatureState(str):
    OFF = "OFF"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    DEFAULT = "DEFAULT"
    DEPRECATED = "DEPRECATED"

class CapabilityRegistry:
    def __init__(self, registry_path: str = "config/capabilities.yaml"):
        self.registry_path = registry_path
        self.capabilities = self._load_registry()

    def _load_registry(self) -> Dict[str, Dict]:
        if not os.path.exists(self.registry_path):
            return {}
        with open(self.registry_path, 'r') as f:
            data = yaml.safe_load(f)
            # Convert list to dict by capability_id
            return {cap['capability_id']: cap for cap in data}

    def get_capability(self, capability_id: str) -> Optional[Dict]:
        return self.capabilities.get(capability_id)

    def get_feature_state(self, capability_id: str) -> FeatureState:
        cap = self.get_capability(capability_id)
        if not cap:
            return FeatureState.OFF
        state_str = cap.get('feature_state', FeatureState.OFF)
        try:
            return FeatureState(state_str)
        except ValueError:
            return FeatureState.OFF

# Singleton instance
registry = CapabilityRegistry()

def get_feature_state(capability_id: str) -> FeatureState:
    return registry.get_feature_state(capability_id)

def get_capability(capability_id: str) -> Optional[Dict]:
    return registry.get_capability(capability_id)