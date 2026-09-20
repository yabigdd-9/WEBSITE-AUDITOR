"""Connector interfaces and safe local connector."""
from .base import Connector, ConnectorResult
from .local import LocalConnector

__all__ = ["Connector", "ConnectorResult", "LocalConnector"]
