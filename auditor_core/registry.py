"""Versioned check registry backed by checks.yaml."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from .models import CheckDefinition


class CheckRegistry:
    def __init__(self, definitions: list[CheckDefinition], taxonomy_version: str):
        self.definitions = definitions
        self.taxonomy_version = taxonomy_version
        self._by_id = {item.id: item for item in definitions}

    def get(self, check_id: str) -> CheckDefinition | None:
        return self._by_id.get(check_id)

    def match(self, message: str) -> CheckDefinition | None:
        for item in self.definitions:
            for pattern in item.patterns:
                if re.search(pattern, message, flags=re.IGNORECASE):
                    return item
        return None


@lru_cache(maxsize=1)
def get_registry() -> CheckRegistry:
    path = Path(__file__).with_name("checks.yaml")
    payload = yaml.safe_load(path.read_text()) or {}
    definitions = [CheckDefinition.model_validate(item) for item in payload.get("checks", [])]
    return CheckRegistry(definitions, str(payload.get("taxonomy_version", "unknown")))
