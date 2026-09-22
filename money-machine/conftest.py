"""pytest bootstrap: re-export environment capability probes (P4).

Probes live in mm_test_capabilities.py so test modules and `mm doctor` can
import them directly; this conftest makes them available to pytest.
"""
from mm_test_capabilities import (  # noqa: F401
    HAS_SOCKET,
    HAS_DNS,
    HAS_PLAYWRIGHT,
    HAS_CONTROL_PLANE,
    HAS_EMAIL_CASE_FIXTURES,
    HAS_EMAIL_MIGRATION_SQL,
    HAS_HERMES_SOURCE_DB,
    capabilities,
)
