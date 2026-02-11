"""Fluent query and mutation builders for JSONQL Python SDK."""

from __future__ import annotations

from typing import Any

from .types import JsonQLMutation, JsonQLQuery


class QueryBuilder:
    """Fluent API for constructing ``JsonQLQuery`` objects."""

    def __init__(self) -> None:
        self._query = JsonQLQuery()

    # ------------------------------------------------------------------

    def from_table(self, table: str) -> QueryBuilder:
        """Set the source table."""
        self._query.from_table = table
        return self

    def select(self, *fields: str) -> QueryBuilder:
        """Add fields to the selection."""
        self._query.fields.extend(fields)
        return self

    def where(self, condition: dict[str, Any]) -> QueryBuilder:
        """Set the initial WHERE clause."""
        self._query.where = condition
        return self

    def and_where(self, condition: dict[str, Any]) -> QueryBuilder:
        """Add an AND condition to the WHERE clause."""
        if self._query.where is None:
            self._query.where = condition
            return self
        existing = self._query.where
        if "and" in existing and isinstance(existing["and"], list):
            existing["and"].append(condition)
        else:
            self._query.where = {"and": [existing, condition]}
        return self

    def or_where(self, condition: dict[str, Any]) -> QueryBuilder:
        """Add an OR condition to the WHERE clause."""
        if self._query.where is None:
            self._query.where = condition
            return self
        existing = self._query.where
        if "or" in existing and isinstance(existing["or"], list):
            existing["or"].append(condition)
        else:
            self._query.where = {"or": [existing, condition]}
        return self

    def order_by(self, *fields: str) -> QueryBuilder:
        """Add fields to the sort order (prefix with ``-`` for DESC)."""
        self._query.sort.extend(fields)
        return self

    def limit(self, limit: int) -> QueryBuilder:
        """Set the maximum number of records to return."""
        self._query.limit = limit
        return self

    def offset(self, offset: int) -> QueryBuilder:
        """Set the number of records to skip."""
        self._query.offset = offset
        return self

    def group_by(self, *fields: str) -> QueryBuilder:
        """Set GROUP BY fields."""
        self._query.group_by.extend(fields)
        return self

    def aggregate(self, aggregate: dict[str, Any]) -> QueryBuilder:
        """Add aggregate definitions."""
        self._query.aggregate = aggregate
        return self

    def include(self, include: dict[str, Any]) -> QueryBuilder:
        """Add relation includes."""
        self._query.include = include
        return self

    def build(self) -> JsonQLQuery:
        """Return the constructed ``JsonQLQuery``."""
        return self._query

    def reset(self) -> QueryBuilder:
        """Reset the builder to a clean state."""
        self._query = JsonQLQuery()
        return self


# ---------- Mutation Builder ----------


class MutationBuilder:
    """Fluent API for constructing ``JsonQLMutation`` objects."""

    def __init__(self) -> None:
        self._mutation: JsonQLMutation | None = None

    def create(self, data: dict[str, Any]) -> MutationBuilder:
        """Initialise a create (INSERT) mutation."""
        self._mutation = JsonQLMutation(op="create", data=data)
        return self

    def update(self, patch: dict[str, Any]) -> MutationBuilder:
        """Initialise an update mutation."""
        self._mutation = JsonQLMutation(op="update", patch=patch)
        return self

    def delete(self) -> MutationBuilder:
        """Initialise a delete mutation."""
        self._mutation = JsonQLMutation(op="delete")
        return self

    def where(self, where: dict[str, Any]) -> MutationBuilder:
        """Set the WHERE clause for the mutation."""
        if self._mutation is None:
            raise ValueError(
                "Mutation not initialised: call create(), update(), or delete() first"
            )
        self._mutation.where = where
        return self

    def build(self) -> JsonQLMutation:
        """Return the constructed ``JsonQLMutation``."""
        if self._mutation is None:
            raise ValueError(
                "Mutation not initialised: call create(), update(), or delete() first"
            )
        return self._mutation

    def reset(self) -> MutationBuilder:
        """Reset the builder to a clean state."""
        self._mutation = None
        return self
