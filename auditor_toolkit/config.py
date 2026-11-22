"""Configuration management with Pydantic validation for auditor_toolkit.

Provides validated configuration loading from environment variables and .env files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation.

    All settings can be configured via environment variables.
    Environment variable prefix: WA_
    """

    model_config = SettingsConfigDict(
        env_prefix="WA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core paths
    output_root: Path = Field(
        default=Path("outputs/toolkit"),
        description="Root directory for audit outputs",
    )

    # Network settings
    default_timeout: float = Field(
        default=8.0,
        ge=0.1,
        le=300.0,
        description="Default HTTP request timeout in seconds",
    )
    allow_private: bool = Field(
        default=False,
        description="Allow auditing private/non-global IP addresses",
    )
    max_redirects: int = Field(
        default=6,
        ge=0,
        le=20,
        description="Maximum redirect hops to follow",
    )

    # Browser settings
    browser_enabled: bool = Field(
        default=False,
        description="Enable browser-based checks (Playwright/Chromium)",
    )
    screenshot_diff: bool = Field(
        default=False,
        description="Generate visual diff screenshots against previous runs",
    )

    # External tools
    external_tools: bool = Field(
        default=False,
        description="Require external tools (Lighthouse, Lychee) to be installed",
    )

    # AI settings
    ai_enabled: bool = Field(
        default=False,
        description="Enable AI-powered draft generation",
    )
    ai_timeout: float = Field(
        default=120.0,
        ge=1.0,
        le=600.0,
        description="AI generation timeout in seconds",
    )
    ai_model_path: Path | None = Field(
        default=None,
        description="Path to local GGUF model file",
    )

    # Rate limiting
    min_request_interval: float = Field(
        default=0.1,
        ge=0.0,
        le=10.0,
        description="Minimum interval between requests to same host (seconds)",
    )
    max_concurrent_audits: int = Field(
        default=2,
        ge=1,
        le=4,
        description="Maximum concurrent audit runs",
    )

    # Cache settings
    cache_enabled: bool = Field(
        default=False,
        description="Enable HTTP response caching",
    )
    cache_ttl_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Cache TTL in hours",
    )

    # Reporting
    brand: str = Field(
        default="Website Auditor",
        description="Brand name for report headers",
    )
    hourly_rate_nzd: float | None = Field(
        default=None,
        ge=0.0,
        description="Hourly rate in NZD for cost estimates",
    )

    # Monitoring & alerts
    alert_webhook_url: str | None = Field(
        default=None,
        description="Webhook URL for regression alerts",
    )
    health_check_enabled: bool = Field(
        default=True,
        description="Enable runtime health checks",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Logging level",
    )
    json_logs: bool = Field(
        default=False,
        description="Output logs as JSON lines",
    )

    # Database
    db_path: Path = Field(
        default=Path("outputs/toolkit/history.sqlite3"),
        description="SQLite database path",
    )

    # External API keys (optional)
    pagespeed_api_key: str | None = Field(
        default=None,
        description="Google PageSpeed Insights API key",
    )
    languagetool_url: str = Field(
        default="https://api.languagetool.org/v2",
        description="LanguageTool API base URL",
    )

    @field_validator("output_root", "db_path", "ai_model_path", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path | None) -> Path | None:
        """Resolve and expand paths."""
        if v is None:
            return None
        path = Path(v).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    @field_validator("alert_webhook_url", mode="before")
    @classmethod
    def validate_webhook_url(cls, v: str | None) -> str | None:
        """Validate webhook URL if provided."""
        if v is None or v == "":
            return None
        from urllib.parse import urlparse

        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Webhook URL must use http or https scheme")
        if not parsed.hostname:
            raise ValueError("Webhook URL must have a hostname")
        return v

    def get_audit_options(self) -> "AuditOptions":
        """Convert settings to AuditOptions for pipeline."""
        from .pipeline import AuditOptions

        return AuditOptions(
            output_root=self.output_root,
            allow_private=self.allow_private,
            browser=self.browser_enabled,
            screenshot_diff=self.screenshot_diff,
            timeout=self.default_timeout,
            external_tools=self.external_tools,
            cache=self.cache_enabled,
            ai=self.ai_enabled,
            ai_timeout=self.ai_timeout,
            brand=self.brand,
            hourly_rate_nzd=self.hourly_rate_nzd,
        )


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global settings instance (singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing)."""
    global _settings
    _settings = Settings()
    return _settings


def validate_startup() -> dict[str, Any]:
    """Validate all settings at startup and return validation results.

    Returns:
        Dict with validation status and any errors.
    """
    try:
        settings = get_settings()

        # Verify output directory is writable
        output_root = settings.output_root
        output_root.mkdir(parents=True, exist_ok=True)
        test_file = output_root / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
        except OSError as e:
            return {
                "valid": False,
                "errors": [f"Output directory not writable: {e}"],
                "settings": settings.model_dump(),
            }

        # Verify database directory
        db_dir = settings.db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Verify AI model if enabled
        if settings.ai_enabled and settings.ai_model_path:
            if not settings.ai_model_path.exists():
                return {
                    "valid": False,
                    "errors": [
                        f"AI model file not found: {settings.ai_model_path}"
                    ],
                    "settings": settings.model_dump(),
                }

        return {
            "valid": True,
            "errors": [],
            "settings": settings.model_dump(),
        }
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"Configuration validation failed: {e}"],
            "settings": {},
        }