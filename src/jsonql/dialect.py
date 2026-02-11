"""SQL dialect abstraction for JSONQL Python SDK.

Each dialect encapsulates the quoting and placeholder conventions
for a specific database backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SQLDialect(ABC):
    """Abstract base class for SQL dialects."""

    @abstractmethod
    def name(self) -> str:
        """Return the dialect name (e.g. ``postgres``, ``mysql``, ``sqlite``)."""

    @abstractmethod
    def placeholder(self, index: int) -> str:
        """Return the placeholder token for the given 0-based parameter index."""

    @abstractmethod
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier (table / column name) for safe use in SQL."""

    @abstractmethod
    def supports_returning(self) -> bool:
        """Whether the dialect supports ``RETURNING *`` on INSERT/UPDATE."""


class PostgresDialect(SQLDialect):
    """PostgreSQL dialect — ``$1`` placeholders, ``"id"`` quoting, RETURNING."""

    def name(self) -> str:
        return "postgres"

    def placeholder(self, index: int) -> str:
        return f"${index + 1}"

    def quote_identifier(self, identifier: str) -> str:
        return f'"{identifier}"'

    def supports_returning(self) -> bool:
        return True


class MySQLDialect(SQLDialect):
    """MySQL dialect — ``?`` placeholders, backtick quoting, no RETURNING."""

    def name(self) -> str:
        return "mysql"

    def placeholder(self, index: int) -> str:  # noqa: ARG002
        return "?"

    def quote_identifier(self, identifier: str) -> str:
        return f"`{identifier}`"

    def supports_returning(self) -> bool:
        return False


class SQLiteDialect(SQLDialect):
    """SQLite dialect — ``?`` placeholders, ``"id"`` quoting, no RETURNING."""

    def name(self) -> str:
        return "sqlite"

    def placeholder(self, index: int) -> str:  # noqa: ARG002
        return "?"

    def quote_identifier(self, identifier: str) -> str:
        return f'"{identifier}"'

    def supports_returning(self) -> bool:
        return False


_DIALECTS: dict[str, type[SQLDialect]] = {
    "postgres": PostgresDialect,
    "mysql": MySQLDialect,
    "sqlite": SQLiteDialect,
}


def new_dialect(name: str) -> SQLDialect:
    """Create a dialect instance by name.

    Raises ``ValueError`` for unknown dialect names.
    """
    cls = _DIALECTS.get(name)
    if cls is None:
        raise ValueError(f"Unknown dialect: {name}. Supported: {', '.join(_DIALECTS)}")
    return cls()
