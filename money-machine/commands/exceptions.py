"""Shared exceptions for mm_operator commands."""

from __future__ import annotations


class OperatorError(Exception):
    """Base exception for mm_operator."""
    pass


class ValidationError(OperatorError):
    """Raised for input/data validation failures."""
    pass


class OperationalError(OperatorError):
    """Raised for runtime/operational failures."""
    pass