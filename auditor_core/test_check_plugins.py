from bs4 import BeautifulSoup

import auditor_core.builtin_plugins  # noqa: F401
from auditor_core.check_plugins import AuditCheckContext, list_plugins, run_plugins


def test_builtin_plugin_registry_has_stable_ids():
    ids = [item["plugin_id"] for item in list_plugins()]
    assert ids == [
        "accessibility.basics",
        "nz.business_signals",
        "security.cookies",
        "technology.stack_images",
    ]


def test_plugin_runner_returns_namespaced_evidence():
    html = '<html><body><input id="x"><img src="/photo.jpg"></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    defects, evidence = run_plugins(
        AuditCheckContext(
            url="https://example.co.nz/",
            final_url="https://example.co.nz/",
            html=html,
            soup=soup,
            body_text="12 High Street Christchurch 8011",
            headers={},
        )
    )
    assert "accessibility.basics" in evidence
    assert "technology.stack_images" in evidence
    assert any(item["defect"] == "Missing HTML lang attribute" for item in defects)
