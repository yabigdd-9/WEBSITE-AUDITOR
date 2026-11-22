import json
import logging
from io import StringIO

import httpx
import pytest

from auditor_toolkit.logging_config import (
    CorrelationIdFilter,
    StructuredFormatter,
    correlation_id_var,
    with_correlation_id,
)
from auditor_toolkit.models import Evidence
from auditor_toolkit.pipeline import AuditOptions
from auditor_toolkit.plugins import CheckContext, CheckPlugin, CheckPluginMetadata, PluginRegistry


def test_structured_logging_correlates_exceptions():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(CorrelationIdFilter())
    handler.setFormatter(StructuredFormatter())
    logger = logging.Logger("fixture")
    logger.addHandler(handler)

    @with_correlation_id
    def record_error():
        try:
            raise ValueError("fixture failure")
        except ValueError:
            logger.exception("Check failed", extra={"check": "title"})

    record_error()
    entry = json.loads(stream.getvalue())
    assert entry["level"] == "ERROR"
    assert entry["check"] == "title"
    assert len(entry["correlation_id"]) == 12
    assert "ValueError: fixture failure" in entry["exception"]
    assert correlation_id_var.get() is None


class FixturePlugin(CheckPlugin):
    metadata = CheckPluginMetadata(id="title-fixture", name="Title fixture", category="seo")

    def execute(self, context):
        if not context.html:
            raise ValueError("No HTML")
        return [], Evidence(
            url=context.url, observed_at=context.timestamp, mode="static",
            data={"html": context.html},
        )


def test_registry_filters_and_disables_checks():
    registry = PluginRegistry()
    plugin = FixturePlugin()
    context = CheckContext(url="https://example.test", html="<title>Fixture</title>")
    registry.register(plugin)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(plugin)
    assert plugin.get_definition().id == "title-fixture"
    assert registry.list_all()[0]["id"] == "title-fixture"
    assert not registry.execute_all(context, categories=["unrelated"])
    findings, evidence = registry.execute_all(context, categories=["seo"])["title-fixture"]
    assert not findings
    assert evidence.data["html"] == context.html
    assert registry.disable("title-fixture")
    assert not registry.execute_all(context)
    assert registry.enable("title-fixture")
    context.html = ""
    assert registry.execute_all(context)["title-fixture"][1].data == {"error": "No HTML"}
    assert registry.unregister("title-fixture")
    assert not registry.unregister("title-fixture")


def test_builtin_plugins_report_static_page_evidence():
    from auditor_toolkit.common import Fetcher
    from auditor_toolkit.plugins import get_registry

    def serve(request):
        return httpx.Response(
            200,
            text='<html><head><title>Fixture</title></head><body>'
                 '<a href="tel:+6435550100">Call us</a></body></html>',
            headers={"Content-Type": "text/html"},
        )

    url = "https://example.test/"
    fetcher = Fetcher(allow_private=True, transport=httpx.MockTransport(serve))
    try:
        response = fetcher.get(url)
        context = CheckContext(
            url=url, fetcher=fetcher, response=response,
            options=AuditOptions(allow_private=True), timestamp="2026-11-22T00:00:00Z",
        )
        registry = get_registry()
        _, fetch_evidence = registry.get("fetch").execute(context)
        assert fetch_evidence.data["status_code"] == 200
        _, ux_evidence = registry.get("ux").execute(context)
        assert ux_evidence.data["signals"]["phone"]
        for plugin_id in ("page", "schema", "headers"):
            _, evidence = registry.get(plugin_id).execute(context)
            assert evidence.url == url
            assert evidence.observed_at == context.timestamp
            assert evidence.data
    finally:
        fetcher.close()
