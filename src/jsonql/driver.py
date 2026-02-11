"""Database driver abstraction for JSONQL Python SDK.

Implement this interface to plug in any database backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DatabaseDriver(ABC):
    """Abstract base class for database drivers."""

    @property
    @abstractmethod
    def dialect(self) -> str:
        """Return the dialect name (``postgres``, ``mysql``, ``sqlite``)."""

    @abstractmethod
    async def query(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        """Execute a SQL query and return rows as list of dicts."""

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying connection / pool."""
