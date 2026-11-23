"""Tests for the plugin architecture."""


import pytest

from auditor_toolkit.checks import Finding
from auditor_toolkit.models import Evidence
from auditor_toolkit.plugins import (
    CheckContext,
    CheckPlugin,
    CheckPluginMetadata,
    PluginRegistry,
    get_registry,
)


class DummyPlugin(CheckPlugin):
    """Dummy plugin for testing."""

    metadata = CheckPluginMetadata(
        id="dummy",
        name="Dummy Check",
        category="test",
        description="A dummy plugin for testing",
        mode="static",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        return [], Evidence(
            url=context.url,
            observed_at=context.timestamp,
            mode="static",
            data={"dummy": True},
        )


class AnotherDummyPlugin(CheckPlugin):
    """Another dummy plugin for testing."""

    metadata = CheckPluginMetadata(
        id="another_dummy",
        name="Another Dummy Check",
        category="test",
        description="Another dummy plugin",
        mode="rendered",
    )

    def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
        return [Finding("test-finding", "Test finding", "Test", "low", context.url)], Evidence(
            url=context.url,
            observed_at=context.timestamp,
            mode="rendered",
            data={"another": True},
        )


def test_plugin_registry_basic():
    """Test basic registry operations."""
    registry = PluginRegistry()

    # Register a plugin
    plugin = DummyPlugin()
    registry.register(plugin)

    assert "dummy" in registry._plugins
    assert "dummy" in registry._enabled
    assert registry.get("dummy") is plugin
    assert registry.get("nonexistent") is None


def test_plugin_registry_duplicate():
    """Test that duplicate registration raises error."""
    registry = PluginRegistry()
    plugin = DummyPlugin()
    registry.register(plugin)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(DummyPlugin())


def test_plugin_registry_unregister():
    """Test unregistering a plugin."""
    registry = PluginRegistry()
    plugin = DummyPlugin()
    registry.register(plugin)

    assert registry.unregister("dummy") is True
    assert "dummy" not in registry._plugins
    assert "dummy" not in registry._enabled
    assert registry.unregister("nonexistent") is False


def test_plugin_registry_enable_disable():
    """Test enabling and disabling plugins."""
    registry = PluginRegistry()
    plugin = DummyPlugin()
    registry.register(plugin)

    # Initially enabled
    assert "dummy" in registry._enabled
    assert len(registry.get_enabled()) == 1

    # Disable
    assert registry.disable("dummy") is True
    assert "dummy" not in registry._enabled
    assert len(registry.get_enabled()) == 0

    # Re-enable
    assert registry.enable("dummy") is True
    assert "dummy" in registry._enabled
    assert len(registry.get_enabled()) == 1


def test_plugin_registry_categories():
    """Test category indexing."""
    registry = PluginRegistry()

    plugin1 = DummyPlugin()  # category "test"
    plugin2 = AnotherDummyPlugin()  # category "test"
    registry.register(plugin1)
    registry.register(plugin2)

    test_plugins = registry.get_by_category("test")
    assert len(test_plugins) == 2
    plugin_ids = {p.metadata.id for p in test_plugins}
    assert plugin_ids == {"dummy", "another_dummy"}

    # Non-existent category
    assert registry.get_by_category("nonexistent") == []


def test_plugin_registry_list_all():
    """Test listing all plugins."""
    registry = PluginRegistry()
    registry.register(DummyPlugin())
    registry.register(AnotherDummyPlugin())

    all_plugins = registry.list_all()
    assert len(all_plugins) == 2

    # Check structure
    for p in all_plugins:
        assert "id" in p
        assert "name" in p
        assert "version" in p
        assert "category" in p
        assert "mode" in p
        assert "description" in p
        assert "enabled" in p


def test_plugin_registry_execute_all():
    """Test executing all plugins."""
    registry = PluginRegistry()
    registry.register(DummyPlugin())
    registry.register(AnotherDummyPlugin())

    context = CheckContext(
        url="https://example.com",
        timestamp="2024-01-01T00:00:00",
    )

    results = registry.execute_all(context)
    assert len(results) == 2

    # Check results
    dummy_findings, dummy_evidence = results["dummy"]
    assert dummy_findings == []
    assert dummy_evidence.data["dummy"] is True

    another_findings, another_evidence = results["another_dummy"]
    assert len(another_findings) == 1
    assert another_findings[0].defect_key == "test-finding"
    assert another_evidence.data["another"] is True


def test_plugin_registry_execute_by_category():
    """Test executing plugins filtered by category."""
    registry = PluginRegistry()
    registry.register(DummyPlugin())  # test category
    registry.register(AnotherDummyPlugin())  # test category

    context = CheckContext(
        url="https://example.com",
        timestamp="2024-01-01T00:00:00",
    )

    # Execute only "test" category
    results = registry.execute_all(context, categories=["test"])
    assert len(results) == 2

    # Execute non-existent category
    results = registry.execute_all(context, categories=["nonexistent"])
    assert len(results) == 0


def test_plugin_decorator():
    """Test the @check_plugin decorator."""

    @pytest.mark.usefixtures("reset_registry")
    def inner():
        from auditor_toolkit.plugins import CheckPluginMetadata, check_plugin

        @check_plugin(CheckPluginMetadata(
            id="decorated_plugin",
            name="Decorated Plugin",
            category="test",
        ))
        class DecoratedPlugin(CheckPlugin):
            def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
                return [], Evidence(
                    url=context.url,
                    observed_at=context.timestamp,
                    mode="static",
                    data={"decorated": True},
                )

        registry = get_registry()
        plugin = registry.get("decorated_plugin")
        assert plugin is not None
        assert plugin.metadata.id == "decorated_plugin"

    inner()


def test_load_plugins_from_directory(tmp_path):
    """Test loading plugins from a directory."""
    # Create a plugin module
    plugin_file = tmp_path / "my_plugin.py"
    plugin_file.write_text("""
from auditor_toolkit.plugins import CheckPlugin, CheckPluginMetadata, register_plugin
from auditor_toolkit.models import Evidence
from auditor_toolkit.checks import Finding

class MyPlugin(CheckPlugin):
    metadata = CheckPluginMetadata(
        id="my_plugin",
        name="My Plugin",
        category="test",
        description="A test plugin loaded from directory",
        mode="static",
    )

    def execute(self, context):
        return [], Evidence(
            url=context.url,
            observed_at=context.timestamp,
            mode="static",
            data={"loaded": True},
        )

register_plugin(MyPlugin())
""")

    from auditor_toolkit.plugins import load_plugins_from_directory

    count = load_plugins_from_directory(tmp_path)
    assert count == 1

    registry = get_registry()
    plugin = registry.get("my_plugin")
    assert plugin is not None


def test_load_plugins_from_directory_invalid(tmp_path):
    """Test loading from directory with invalid Python."""
    # Create an invalid plugin file
    plugin_file = tmp_path / "bad_plugin.py"
    plugin_file.write_text("this is not valid python")

    from auditor_toolkit.plugins import load_plugins_from_directory

    # Should not raise, just log error
    count = load_plugins_from_directory(tmp_path)
    assert count == 0


def test_global_registry_singleton():
    """Test that get_registry returns singleton."""

    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_plugin_validation():
    """Test plugin dependency validation."""
    class ValidatingPlugin(CheckPlugin):
        metadata = CheckPluginMetadata(
            id="validating",
            name="Validating Plugin",
            category="test",
        )

        def validate_dependencies(self) -> tuple[bool, str]:
            return False, "missing dependency"

        def execute(self, context: CheckContext) -> tuple[list[Finding], Evidence]:
            return [], Evidence(
                url=context.url,
                observed_at=context.timestamp,
                mode="static",
                data={},
            )

    registry = PluginRegistry()
    # Should register but log warning
    plugin = ValidatingPlugin()
    registry.register(plugin)

    assert "validating" in registry._plugins
    assert "validating" in registry._enabled


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
