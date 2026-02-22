"""JSONQL Parser — converts raw dicts/JSON into typed query objects."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .types import DistinctOption, JsonQLMutation, JsonQLQuery, JsonQLSchema


@dataclass
class ParserOptions:
    """Constraints applied during parsing."""

    max_nesting_depth: int = 0
    max_limit: int = 0
    allowed_fields: list[str] = field(default_factory=list)
    allowed_includes: list[str] = field(default_factory=list)


class Parser:
    """Parse raw dicts or JSON bytes into typed ``JsonQLQuery`` / ``JsonQLMutation`` objects."""

    def __init__(self, options: ParserOptions | None = None) -> None:
        self.options = options or ParserOptions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(
        self,
        raw: dict[str, Any],
        schema: JsonQLSchema | None = None,
        table: str = "",
    ) -> JsonQLQuery | JsonQLMutation:
        """Parse a raw dict into a query or mutation."""
        if "op" in raw:
            return self._parse_mutation(raw)
        return self._parse_query(raw, schema, table)

    def parse_json(
        self,
        data: str | bytes,
        schema: JsonQLSchema | None = None,
        table: str = "",
    ) -> JsonQLQuery | JsonQLMutation:
        """Parse a JSON string/bytes into a query or mutation."""
        raw = json.loads(data)
        if not isinstance(raw, dict):
            raise ValueError("JSONQL input must be a JSON object")
        return self.parse(raw, schema, table)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_query(
        self,
        raw: dict[str, Any],
        schema: JsonQLSchema | None,
        table: str,
    ) -> JsonQLQuery:
        # Normalise sort: string → list
        sort_raw = raw.get("sort", [])
        if isinstance(sort_raw, str):
            sort_raw = [sort_raw]

        distinct: DistinctOption | None = None
        if "distinct" in raw:
            distinct = DistinctOption.from_raw(raw["distinct"])

        query = JsonQLQuery(
            version=raw.get("version", "1.0"),
            from_table=raw.get("from", table or ""),
            fields=raw.get("fields", []),
            where=raw.get("where"),
            sort=sort_raw,
            limit=raw.get("limit"),
            offset=raw.get("offset") or raw.get("skip"),
            aggregate=raw.get("aggregate", {}),
            group_by=raw.get("groupBy", []),
            include=raw.get("include", {}),
            distinct=distinct,
        )
        self._validate_options(query)
        return query

    def _parse_mutation(self, raw: dict[str, Any]) -> JsonQLMutation:
        return JsonQLMutation(
            op=raw.get("op", ""),
            data=raw.get("data", {}),
            patch=raw.get("patch", {}),
            where=raw.get("where"),
        )

    def _validate_options(self, query: JsonQLQuery) -> None:
        opts = self.options

        # Max limit
        if opts.max_limit and query.limit is not None and query.limit > opts.max_limit:
            raise ValueError(
                f"Limit {query.limit} exceeds maximum allowed limit of {opts.max_limit}"
            )

        # Max nesting depth
        if opts.max_nesting_depth and query.include:
            depth = self._calculate_depth(query.include)
            if depth > opts.max_nesting_depth:
                raise ValueError(
                    f"Nesting depth {depth} exceeds maximum allowed depth "
                    f"of {opts.max_nesting_depth}"
                )

        # Allowed fields
        if opts.allowed_fields:
            for f in query.fields:
                if f not in opts.allowed_fields:
                    raise ValueError(f"Field '{f}' is not allowed")

        # Allowed includes
        if opts.allowed_includes:
            for inc in query.include:
                if inc not in opts.allowed_includes:
                    raise ValueError(f"Include '{inc}' is not allowed")

    @staticmethod
    def _calculate_depth(include: dict[str, Any]) -> int:
        max_child = 0
        for _rel_name, rel_config in include.items():
            if isinstance(rel_config, dict) and "include" in rel_config:
                nested = rel_config["include"]
                if isinstance(nested, dict):
                    d = Parser._calculate_depth(nested)
                    max_child = max(max_child, d)
        return 1 + max_child
