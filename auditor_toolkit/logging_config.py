"""Structured logging configuration for auditor_toolkit.

Provides JSON-formatted logging with correlation IDs for request tracing.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variable for correlation ID propagation
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get() or "N/A"
        return True


class StructuredFormatter(logging.Formatter):
    """JSON formatter with structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "N/A"),
        }

        # Add extra fields if present
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "name", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info", "correlation_id",
            }:
                log_entry[key] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the standard configuration."""
    return logging.getLogger(name)


def setup_logging(
    level: int = logging.INFO,
    json_output: bool = False,
    stream: Any = sys.stdout,
) -> None:
    """Configure root logger with structured formatting.

    Args:
        level: Minimum log level to emit.
        json_output: If True, output JSON lines. If False, human-readable.
        stream: Output stream (default stdout).
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Clear existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream)
    handler.setLevel(level)

    if json_output:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(correlation_id)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    handler.addFilter(CorrelationIdFilter())
    root.addHandler(handler)

    # Reduce noise from third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def set_correlation_id(correlation_id: str | None = None) -> str:
    """Set correlation ID for current context.

    Args:
        correlation_id: Optional correlation ID. If None, generates a new UUID.

    Returns:
        The correlation ID that was set.
    """
    cid = correlation_id or uuid.uuid4().hex[:12]
    correlation_id_var.set(cid)
    return cid


def clear_correlation_id() -> None:
    """Clear correlation ID from current context."""
    correlation_id_var.set(None)


def with_correlation_id(func):
    """Decorator to run a function with a fresh correlation ID."""

    def wrapper(*args, **kwargs):
        set_correlation_id()
        try:
            return func(*args, **kwargs)
        finally:
            clear_correlation_id()

    return wrapper


class LogContext:
    """Context manager for structured logging with extra fields."""

    def __init__(self, logger: logging.Logger, **extra_fields):
        self.logger = logger
        self.extra_fields = extra_fields
        self.old_extra = {}

    def __enter__(self):
        # Store old extra fields and add new ones
        for key, value in self.extra_fields.items():
            self.old_extra[key] = getattr(self.logger, key, None)
            setattr(self.logger, key, value)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore old extra fields
        for key, value in self.old_extra.items():
            if value is None:
                delattr(self.logger, key)
            else:
                setattr(self.logger, key, value)
        return False
