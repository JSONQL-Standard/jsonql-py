"""Schema-aware validator for JSONQL queries."""

from __future__ import annotations

from .errors import JsonQLValidationError
from .types import (
    JsonQLQuery,
    JsonQLSchema,
    ValidationError,
    ValidationResult,
)


class Validator:
    """Validate a ``JsonQLQuery`` against a ``JsonQLSchema``."""

    def __init__(self, schema: JsonQLSchema, table: str) -> None:
        self.schema = schema
        self.table = table

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, query: JsonQLQuery) -> ValidationResult:
        """Return a ``ValidationResult`` with all detected errors."""
        result = ValidationResult(valid=True)

        # Global settings
        if self.schema.settings:
            if not self.schema.settings.allow_aggregate and (query.aggregate or query.group_by):
                result.valid = False
                result.errors.append(
                    ValidationError(
                        code="AGGREGATION_DISABLED",
                        message="aggregations are disabled in this schema",
                    )
                )
            if self.schema.settings.max_depth > 0:
                depth = self._calculate_depth(query.include)
                if depth > self.schema.settings.max_depth:
                    result.valid = False
                    result.errors.append(
                        ValidationError(
                            code="MAX_DEPTH_EXCEEDED",
                            message=(
                                f"query depth {depth} exceeds maximum "
                                f"allowed depth of {self.schema.settings.max_depth}"
                            ),
                        )
                    )

        table_def = self.schema.tables.get(self.table)
        if table_def is None:
            result.valid = False
            result.errors.append(
                ValidationError(
                    code="TABLE_NOT_FOUND",
                    message=f"table '{self.table}' not found in schema",
                )
            )
            return result

        # Fields (allowSelect)
        for f in query.fields:
            fld = table_def.fields.get(f)
            if fld is None or (fld.allow_select is not None and not fld.allow_select):
                result.valid = False
                result.errors.append(
                    ValidationError(
                        code="FIELD_NOT_ALLOWED",
                        message=f"field '{f}' not allowed on table '{self.table}'",
                        path="fields",
                    )
                )

        # Where (allowFilter)
        if query.where:
            for fld_name in query.where:
                if fld_name in ("or", "and", "not"):
                    continue
                fld = table_def.fields.get(fld_name)
                if fld is None or (fld.allow_filter is not None and not fld.allow_filter):
                    result.valid = False
                    result.errors.append(
                        ValidationError(
                            code="FIELD_NOT_FILTERABLE",
                            message=(f"field '{fld_name}' not filterable on table '{self.table}'"),
                            path="where",
                        )
                    )

        # Sort (allowSort)
        for s in query.sort:
            fld_name = s.lstrip("-")
            fld = table_def.fields.get(fld_name)
            if fld is None or (fld.allow_sort is not None and not fld.allow_sort):
                result.valid = False
                result.errors.append(
                    ValidationError(
                        code="FIELD_NOT_SORTABLE",
                        message=f"field '{fld_name}' not sortable on table '{self.table}'",
                        path="sort",
                    )
                )

        # Group By (allowGroup)
        for g in query.group_by:
            fld = table_def.fields.get(g)
            if fld is None or (fld.allow_group is not None and not fld.allow_group):
                result.valid = False
                result.errors.append(
                    ValidationError(
                        code="FIELD_NOT_GROUPABLE",
                        message=f"field '{g}' not groupable on table '{self.table}'",
                        path="groupBy",
                    )
                )

        # Aggregates
        for alias, agg_def in query.aggregate.items():
            if isinstance(agg_def, dict):
                for func_name, f_raw in agg_def.items():
                    if not isinstance(f_raw, str):
                        continue
                    if f_raw == "*" and func_name == "count":
                        continue
                    fld = table_def.fields.get(f_raw)
                    if fld is None:
                        result.valid = False
                        result.errors.append(
                            ValidationError(
                                code="FIELD_NOT_FOUND",
                                message=f"field '{f_raw}' not found on table '{self.table}'",
                                path=f"aggregate.{alias}",
                            )
                        )
                        continue
                    allowed = self._check_aggregate_permission(fld, func_name)
                    if not allowed:
                        result.valid = False
                        result.errors.append(
                            ValidationError(
                                code="AGGREGATION_NOT_ALLOWED",
                                message=(
                                    f"aggregation '{func_name}' not allowed on field '{f_raw}'"
                                ),
                                path=f"aggregate.{alias}",
                            )
                        )

        # Relations (allowInclude)
        for rel_name in query.include:
            rel = table_def.relations.get(rel_name)
            if rel is None:
                result.valid = False
                result.errors.append(
                    ValidationError(
                        code="RELATION_NOT_FOUND",
                        message=f"relation '{rel_name}' not found on table '{self.table}'",
                        path="include",
                    )
                )
                continue
            if rel.allow_include is not None and not rel.allow_include:
                result.valid = False
                result.errors.append(
                    ValidationError(
                        code="RELATION_NOT_ALLOWED",
                        message=f"relation '{rel_name}' not allowed to be included",
                        path="include",
                    )
                )

        return result

    def validate_first(self, query: JsonQLQuery) -> ValidationError | None:
        """Return the first validation error, or ``None`` if valid."""
        result = self.validate(query)
        return result.errors[0] if result.errors else None

    def validate_or_raise(self, query: JsonQLQuery) -> None:
        """Raise ``JsonQLValidationError`` if the query is invalid."""
        result = self.validate(query)
        if not result.valid:
            raise JsonQLValidationError("Validation failed", result.errors)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_aggregate_permission(fld: object, func_name: str) -> bool:
        """Check per-function and fallback aggregate permission."""
        perm_map = {
            "sum": "allow_sum",
            "avg": "allow_avg",
            "min": "allow_min",
            "max": "allow_max",
            "count": "allow_count",
        }
        attr = perm_map.get(func_name)
        if attr:
            val = getattr(fld, attr, None)
            if val is not None:
                return val
        # Fallback to generic allow_aggregate
        fallback = getattr(fld, "allow_aggregate", None)
        if fallback is not None:
            return fallback
        return True

    @staticmethod
    def _calculate_depth(include: dict) -> int:
        if not include:
            return 0
        max_child = 0
        for _rel_name, rel_config in include.items():
            if isinstance(rel_config, dict) and "include" in rel_config:
                nested = rel_config["include"]
                if isinstance(nested, dict):
                    d = Validator._calculate_depth(nested)
                    max_child = max(max_child, d)
        return 1 + max_child
