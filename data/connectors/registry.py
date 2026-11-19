"""Connector registry: provider adapters are replaceable independently."""
from __future__ import annotations

from .base import BaseConnector
from .bse_connector import BSEConnector
from .nse_connector import NSEConnector
from .rss_news_connector import RSSNewsConnector
from .yfinance_connector import YFinanceConnector


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        self._connectors[connector.name] = connector

    def get(self, name: str) -> BaseConnector:
        return self._connectors[name]

    def all(self) -> list[BaseConnector]:
        return list(self._connectors.values())

    def health_check_all(self) -> dict[str, dict]:
        report: dict[str, dict] = {}
        for name, connector in self._connectors.items():
            try:
                result = connector.health_check()
                report[name] = {
                    "ok": result.ok,
                    "error": result.error,
                    "checked_at": str(result.retrieved_at),
                }
            except Exception as exc:
                report[name] = {"ok": False, "error": str(exc), "checked_at": None}
        return report


def default_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(YFinanceConnector())
    registry.register(NSEConnector())
    registry.register(BSEConnector())
    registry.register(RSSNewsConnector())
    return registry
