"""
Canonical audit registry.
Registers all audit checks and provides lookup.
"""

from typing import Dict, List, Type
from .checks.base import BaseCheck

class AuditRegistry:
    def __init__(self):
        self._checks: Dict[str, Type[BaseCheck]] = {}

    def register(self, check_id: str, check_class: Type[BaseCheck]):
        self._checks[check_id] = check_class

    def get(self, check_id: str) -> Type[BaseCheck]:
        return self._checks.get(check_id)

    def list(self) -> List[str]:
        return list(self._checks.keys())

# Global registry instance
registry = AuditRegistry()

def register_check(check_id: str, check_class: Type[BaseCheck]):
    registry.register(check_id, check_class)

def get_check(check_id: str):
    return registry.get(check_id)

def list_checks():
    return registry.list()