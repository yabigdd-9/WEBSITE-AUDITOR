"""Plugin architecture for auditor_toolkit checks.

Provides a plugin system for extending audit checks without modifying core code.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .checks import Finding
from .models import CheckDefinition, Evidence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckPluginMetadata:
    """Metadata for a check plugin.

    Attributes:
        id: Unique plugin identifier.
        name: Human-readable name.
        version: Plugin version.
        category: Check category (e.g., "technical", "seo", "security").
        mode: Execution mode ("static" or "rendered").
        description: Brief description of what the check does.
        limitation: Known limitations of this check.
        requires_external: Whether check requires external services.
        author: Plugin author.
    """

    id: str
    name: str
    version: str = "1.0.0"
    category: str = "general"
    mode: str = "static"
    description: str = ""
    limitation: str = ""
    requires_external: bool = False
    author: str = ""


class CheckPlugin(ABC):
    """Abstract base class for check plugins.

    All check plugins must implement the execute method.
    Plugins are automatically registered via the PluginRegistry.
    """

    # Class-level metadata (can be overridden in subclasses)
    metadata: CheckPluginMetadata = CheckPluginMetadata(
        id="base_plugin",
        name="Base Check Plugin",
    )

    @abstractmethod
    def execute(self, context: "CheckContext") -> tuple[list[Finding], Evidence]:
        """Execute the check and return findings and evidence.

        Args:
            context: CheckContext with URL, fetcher, response, options, etc.

        Returns:
            Tuple of (findings_list, evidence_dict).
        """
        pass

    def validate_dependencies(self) -> tuple[bool, str]:
        """Validate that all required dependencies are available.

        Returns:
            Tuple of (is_valid, error_message).
        """
        return True, ""

    def get_definition(self) -> CheckDefinition:
        """Get the CheckDefinition for this plugin."""
        return CheckDefinition(
            id=self.metadata.id,
            category=self.metadata.category,
            mode=self.metadata.mode,
            version=self.metadata.version,
            evidence_required=True,
            limitation=self.metadata.limitation,
        )


@dataclass
class CheckContext:
    """Context passed to check plugins during execution.

    Attributes:
        url: Target URL being audited.
        fetcher: Fetcher instance for HTTP requests.
        response: HTTP response from initial fetch (if available).
        html: HTML content of the page (if available).
        headers: Response headers (if available).
        options: AuditOptions for configuration.
        run_dir: Directory for this audit run's artifacts.
        timestamp: ISO timestamp of audit start.
    """

    url: str
    fetcher: Any = None
    response: Any = None
    html: str = ""
    headers: dict = field(default_factory=dict)
    options: Any = None
    run_dir: Any = None
    timestamp: str = ""

    def get(self, key: str, default: Any = None) -> Any:
        """Get arbitrary context data."""
        return getattr(self, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set arbitrary context data."""
        setattr(self, key, value)


class PluginRegistry:
    """Registry for check plugins.

    Manages plugin discovery, registration, and execution.
    """

    def __init__(self):
        self._plugins: dict[str, CheckPlugin] = {}
        self._enabled: set[str] = set()
        self._categories: dict[str, list[str]] = {}

    def register(self, plugin: CheckPlugin) -> None:
        """Register a plugin.

        Args:
            plugin: CheckPlugin instance to register.

        Raises:
            ValueError: If plugin ID already registered.
        """
        plugin_id = plugin.metadata.id
        if plugin_id in self._plugins:
            raise ValueError(f"Plugin already registered: {plugin_id}")

        # Validate dependencies
        valid, error = plugin.validate_dependencies()
        if not valid:
            logger.warning(f"Plugin {plugin_id} dependency check failed: {error}")

        self._plugins[plugin_id] = plugin
        self._enabled.add(plugin_id)

        # Index by category
        category = plugin.metadata.category
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(plugin_id)

        logger.info(f"Registered check plugin: {plugin_id} ({category})")

    def unregister(self, plugin_id: str) -> bool:
        """Unregister a plugin.

        Args:
            plugin_id: ID of plugin to unregister.

        Returns:
            True if plugin was found and removed.
        """
        if plugin_id in self._plugins:
            plugin = self._plugins.pop(plugin_id)
            self._enabled.discard(plugin_id)
            category = plugin.metadata.category
            if category in self._categories:
                self._categories[category].remove(plugin_id)
            logger.info(f"Unregistered check plugin: {plugin_id}")
            return True
        return False

    def get(self, plugin_id: str) -> CheckPlugin | None:
        """Get a plugin by ID."""
        return self._plugins.get(plugin_id)

    def get_enabled(self) -> list[CheckPlugin]:
        """Get all enabled plugins."""
        return [self._plugins[pid] for pid in self._enabled if pid in self._plugins]

    def get_by_category(self, category: str) -> list[CheckPlugin]:
        """Get enabled plugins by category."""
        return [
            self._plugins[pid]
            for pid in self._categories.get(category, [])
            if pid in self._enabled
        ]

    def enable(self, plugin_id: str) -> bool:
        """Enable a plugin."""
        if plugin_id in self._plugins:
            self._enabled.add(plugin_id)
            return True
        return False

    def disable(self, plugin_id: str) -> bool:
        """Disable a plugin."""
        if plugin_id in self._enabled:
            self._enabled.discard(plugin_id)
            return True
        return False

    def list_all(self) -> list[dict[str, Any]]:
        """List all plugins with their metadata."""
        return [
            {
                "id": plugin.metadata.id,
                "name": plugin.metadata.name,
                "version": plugin.metadata.version,
                "category": plugin.metadata.category,
                "mode": plugin.metadata.mode,
                "description": plugin.metadata.description,
                "enabled": pid in self._enabled,
            }
            for pid, plugin in self._plugins.items()
        ]

    def execute_all(
        self,
        context: CheckContext,
        categories: list[str] | None = None,
        parallel: bool = False,
    ) -> dict[str, tuple[list[Finding], Evidence]]:
        """Execute all enabled plugins (or filtered by category).

        Args:
            context: CheckContext for execution.
            categories: Optional list of categories to filter by.
            parallel: Whether to run plugins in parallel (future).

        Returns:
            Dict mapping plugin_id to (findings, evidence).
        """
        if categories:
            plugins = []
            for cat in categories:
                plugins.extend(self.get_by_category(cat))
        else:
            plugins = self.get_enabled()

        results = {}
        for plugin in plugins:
            try:
                logger.debug(f"Executing plugin: {plugin.metadata.id}")
                findings, evidence = plugin.execute(context)
                results[plugin.metadata.id] = (findings, evidence)
            except Exception as e:
                logger.error(f"Plugin {plugin.metadata.id} failed: {e}", exc_info=True)
                results[plugin.metadata.id] = ([], Evidence(
                    url=context.url,
                    observed_at=context.timestamp,
                    mode=plugin.metadata.mode,
                    data={"error": str(e)},
                ))

        return results


# Global registry instance
_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get the global plugin registry (singleton)."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def register_plugin(plugin: CheckPlugin) -> None:
    """Register a plugin with the global registry."""
    get_registry().register(plugin)


# Decorator for easy plugin registration
def check_plugin(metadata: CheckPluginMetadata):
    """Decorator to register a check plugin class.

    Usage:
        @check_plugin(CheckPluginMetadata(
            id="my_check",
            name="My Check",
            category="seo",
        ))
        class MyCheck(CheckPlugin):
            def execute(self, context):
                ...
    """

    def decorator(cls: type[CheckPlugin]):
        cls.metadata = metadata
        # Auto-register on import
        register_plugin(cls())
        return cls

    return decorator
