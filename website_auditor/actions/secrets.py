"""Environment-only secret resolver.

Connector secrets are never stored in repository JSON files.
"""
from __future__ import annotations

import os


class SecretResolver:
    def __init__(self, allowlist: list[str] | None = None):
        self.allowlist = set(allowlist or [])

    def get(self, env_name: str) -> str:
        if env_name not in self.allowlist:
            raise PermissionError(f"secret environment variable is not allowlisted: {env_name}")
        value = os.environ.get(env_name)
        if not value:
            raise KeyError(f"secret environment variable is not set: {env_name}")
        return value
