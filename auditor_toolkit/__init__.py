"""Local Website Auditor toolkit."""

# Import builtin plugins to register them
from . import builtin_plugins  # noqa: F401
from .pipeline import AuditOptions, run_audit

__all__ = [
    "AuditOptions",
    "run_audit",
    "Settings",
    "get_settings",
    "validate_startup",
]


def __getattr__(name: str):
    if name in {"Settings", "get_settings", "validate_startup"}:
        from . import config

        return getattr(config, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
