"""Result hydrator — converts flat SQL rows into nested JSON-friendly structures.

Uses the ``__`` (double-underscore) separator convention to reconstruct
nested objects from aliased column names produced by the transpiler's
JOIN logic.
"""

from __future__ import annotations

from typing import Any

from .types import JsonQLSchema


class ResultHydrator:
    """Convert flat SQL result rows into nested dictionaries."""

    SEPARATOR = "__"

    def hydrate(
        self,
        rows: list[dict[str, Any]],
        schema: JsonQLSchema | None = None,
        root_table: str = "",
    ) -> list[dict[str, Any]]:
        """Hydrate flat rows, optionally merging via *schema*."""
        raw_rows = [self._expand_row(row) for row in rows]

        if schema and root_table:
            return self._merge_rows(raw_rows, schema, root_table)
        return raw_rows

    # ------------------------------------------------------------------
    # Expand __ aliases into nested dicts
    # ------------------------------------------------------------------

    @classmethod
    def _expand_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for col_name, value in row.items():
            if cls.SEPARATOR in col_name:
                parts = col_name.split(cls.SEPARATOR)
                current = result
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    target = current[part]
                    if isinstance(target, dict):
                        current = target
                    elif isinstance(target, list) and target:
                        current = target[-1]
                    else:
                        break
                current[parts[-1]] = value
            else:
                result[col_name] = value
        return result

    # ------------------------------------------------------------------
    # Merge rows by ID (group hasMany / deduplicate hasOne)
    # ------------------------------------------------------------------

    def _merge_rows(
        self,
        rows: list[dict[str, Any]],
        schema: JsonQLSchema,
        table_name: str,
    ) -> list[dict[str, Any]]:
        if not rows:
            return []

        # Determine primary key from schema (default to "id")
        table_def = schema.tables.get(table_name)
        pk = table_def.primary_key if table_def else "id"

        # Group by primary key
        groups: dict[Any, list[dict[str, Any]]] = {}
        order: list[Any] = []

        for row in rows:
            row_id = row.get(pk, id(row))
            if row_id not in groups:
                order.append(row_id)
                groups[row_id] = []
            groups[row_id].append(row)

        table_def = schema.tables.get(table_name)
        results: list[dict[str, Any]] = []

        for row_id in order:
            group_rows = groups[row_id]
            base = group_rows[0]
            merged: dict[str, Any] = {}

            # Copy non-relation fields
            for k, v in base.items():
                is_relation = (
                    table_def is not None and k in table_def.relations
                )
                if not is_relation:
                    merged[k] = v

            # Handle relations
            if table_def:
                for rel_name, rel_def in table_def.relations.items():
                    relation_present = any(
                        rel_name in r for r in group_rows
                    )

                    all_columns_selected = table_def.fields and all(
                        fname in base for fname in table_def.fields
                    )

                    if not relation_present and not all_columns_selected:
                        continue

                    sub_rows: list[dict[str, Any]] = []
                    target_table = rel_def.target or rel_name
                    target_def = schema.tables.get(target_table)
                    child_pk = target_def.primary_key if target_def else "id"
                    for r in group_rows:
                        val = r.get(rel_name)
                        if isinstance(val, dict) and self._is_valid_row(val, child_pk):
                            sub_rows.append(val)
                        elif isinstance(val, list):
                            for item in val:
                                if isinstance(item, dict) and self._is_valid_row(item, child_pk):
                                    sub_rows.append(item)

                    merged_sub = self._merge_rows(sub_rows, schema, target_table)

                    if rel_def.type == "hasMany":
                        if not merged_sub:
                            merged[rel_name] = []
                        else:
                            # Check for aggregate result
                            if self._is_aggregate_result(
                                merged_sub, schema, target_table
                            ):
                                merged[rel_name] = merged_sub[0]
                            else:
                                merged[rel_name] = merged_sub
                    else:
                        # hasOne / belongsTo
                        merged[rel_name] = merged_sub[0] if merged_sub else None

            results.append(merged)

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid_row(row: dict[str, Any], pk: str = "id") -> bool:
        if pk in row:
            return row[pk] is not None
        return any(v is not None for v in row.values())

    @staticmethod
    def _is_aggregate_result(
        merged: list[dict[str, Any]],
        schema: JsonQLSchema,
        target_table: str,
    ) -> bool:
        if len(merged) != 1:
            return False
        row = merged[0]
        target_def = schema.tables.get(target_table)
        pk = target_def.primary_key if target_def else "id"
        if pk in row:
            return False
        if target_def is None:
            return False
        return all(k not in target_def.fields for k in row)
