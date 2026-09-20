"""Executable audit check plugin registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import bs4


@dataclass
class AuditCheckContext:
    url: str
    html: str
    soup: bs4.BeautifulSoup
    body_text: str
    headers: dict[str, Any]
    final_url: str


@dataclass(frozen=True)
class CheckPlugin:
    plugin_id: str
    runner: Callable[[AuditCheckContext], tuple[list[dict], dict[str, Any]]]
    description: str = ""


_PLUGINS: dict[str, CheckPlugin] = {}


def register_plugin(
    plugin_id: str,
    *,
    description: str = "",
):
    def decorator(runner: Callable[[AuditCheckContext], tuple[list[dict], dict[str, Any]]]):
        if plugin_id in _PLUGINS:
            raise ValueError(f"duplicate audit check plugin id: {plugin_id}")
        _PLUGINS[plugin_id] = CheckPlugin(plugin_id, runner, description)
        return runner

    return decorator


def list_plugins() -> list[dict[str, str]]:
    return [
        {"plugin_id": item.plugin_id, "description": item.description}
        for item in sorted(_PLUGINS.values(), key=lambda item: item.plugin_id)
    ]


def run_plugins(context: AuditCheckContext) -> tuple[list[dict], dict[str, Any]]:
    defects: list[dict] = []
    evidence: dict[str, Any] = {}
    for plugin_id in sorted(_PLUGINS):
        plugin = _PLUGINS[plugin_id]
        plugin_defects, plugin_evidence = plugin.runner(context)
        defects.extend(plugin_defects)
        evidence[plugin_id] = plugin_evidence
    return defects, evidence
