"""JSONQL → SQL transpiler for the Python SDK.

Mirrors the Go / TypeScript transpiler logic:
SELECT, WHERE, JOIN, GROUP BY, ORDER BY, LIMIT/OFFSET, DISTINCT,
INSERT, UPDATE, DELETE.
"""

from __future__ import annotations

import re
from typing import Any

from .dialect import SQLDialect, new_dialect
from .errors import JsonQLTranspileError
from .types import (
    JsonQLMutation,
    JsonQLQuery,
    JsonQLSchema,
    TranspileResult,
    is_mutation,
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_valid_identifier(name: str) -> bool:
    return bool(_IDENT_RE.match(name))


class SQLTranspiler:
    """Convert a ``JsonQLQuery`` or ``JsonQLMutation`` into SQL."""

    def __init__(self, dialect: SQLDialect | str = "sqlite") -> None:
        if isinstance(dialect, str):
            dialect = new_dialect(dialect)
        self.dialect: SQLDialect = dialect

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transpile(
        self,
        statement: JsonQLQuery | JsonQLMutation,
        table_name: str,
        schema: JsonQLSchema | None = None,
    ) -> TranspileResult:
        """Transpile a statement (query *or* mutation) into SQL."""
        if is_mutation(statement):
            mut = statement  # type: ignore[assignment]
            assert isinstance(mut, JsonQLMutation)
            if mut.op == "create":
                return self.transpile_insert(table_name, mut.data)
            if mut.op == "update":
                return self.transpile_update(table_name, mut.patch, mut.where)
            if mut.op == "delete":
                return self.transpile_delete(table_name, mut.where)
            raise JsonQLTranspileError(f"Unknown mutation op: {mut.op}")
        assert isinstance(statement, JsonQLQuery)
        return self._transpile_select(statement, table_name, schema)

    # ------------------------------------------------------------------
    # SELECT
    # ------------------------------------------------------------------

    def _transpile_select(
        self,
        query: JsonQLQuery,
        table_name: str,
        schema: JsonQLSchema | None,
    ) -> TranspileResult:
        q = self._qi  # shorthand
        args: list[Any] = []
        select_parts: list[str] = []
        join_parts: list[str] = []
        where_conditions: list[str] = []

        # 1. Fields
        if query.fields:
            for f in query.fields:
                if f == "*":
                    select_parts.append(f"{q(table_name)}.*")
                    continue
                if not _is_valid_identifier(f):
                    raise JsonQLTranspileError(f"Invalid field name: {f}")
                select_parts.append(f"{q(table_name)}.{q(f)}")
        elif not query.aggregate:
            select_parts.append(f"{q(table_name)}.*")

        # 2. Aggregates
        if query.aggregate:
            # When aggregating with GROUP BY, include group columns in SELECT
            if query.group_by and not query.fields:
                for g in query.group_by:
                    if _is_valid_identifier(g):
                        select_parts.append(f"{q(table_name)}.{q(g)}")

            for alias, agg_def in query.aggregate.items():
                if not isinstance(agg_def, dict):
                    continue
                for func_name, field_name in agg_def.items():
                    if not isinstance(field_name, str):
                        continue
                    fn = func_name.upper()
                    if field_name == "*" and func_name == "count":
                        select_parts.append(f"COUNT(*) AS {q(alias)}")
                    else:
                        if not _is_valid_identifier(field_name):
                            raise JsonQLTranspileError(
                                f"Invalid aggregate field: {field_name}"
                            )
                        select_parts.append(
                            f"{fn}({q(table_name)}.{q(field_name)}) AS {q(alias)}"
                        )

        # 3. Includes / JOINs
        if query.include and schema:
            self._process_join(
                query.include,
                table_name,
                table_name,
                "",
                schema,
                select_parts,
                join_parts,
                where_conditions,
                args,
            )

        # DISTINCT keyword
        distinct_kw = ""
        if query.distinct:
            if query.distinct.all:
                distinct_kw = "DISTINCT "
            elif query.distinct.fields:
                # DISTINCT ON is Postgres-specific; for others fall back to plain DISTINCT
                if self.dialect.name() == "postgres":
                    cols = ", ".join(
                        f"{q(table_name)}.{q(f)}" for f in query.distinct.fields
                    )
                    distinct_kw = f"DISTINCT ON ({cols}) "
                else:
                    distinct_kw = "DISTINCT "

        # Build FROM clause
        from_clause = q(table_name)
        if join_parts:
            from_clause += " " + " ".join(join_parts)

        sql = f"SELECT {distinct_kw}{', '.join(select_parts)} FROM {from_clause}"

        # 4. WHERE
        if query.where:
            conds, w_args = self._process_where(query.where, table_name)
            where_conditions.extend(conds)
            args.extend(w_args)

        if where_conditions:
            sql += " WHERE " + " AND ".join(where_conditions)

        # 5. GROUP BY
        if query.group_by:
            groups: list[str] = []
            for g in query.group_by:
                if not _is_valid_identifier(g):
                    raise JsonQLTranspileError(f"Invalid group by field: {g}")
                groups.append(f"{q(table_name)}.{q(g)}")
            sql += " GROUP BY " + ", ".join(groups)

        # 6. ORDER BY
        if query.sort:
            sort_parts: list[str] = []
            for s in query.sort:
                desc = s.startswith("-")
                field_name = s[1:] if desc else s
                if not _is_valid_identifier(field_name):
                    raise JsonQLTranspileError(f"Invalid sort field: {field_name}")
                order = "DESC" if desc else "ASC"
                sort_parts.append(f"{q(table_name)}.{q(field_name)} {order}")
            sql += " ORDER BY " + ", ".join(sort_parts)

        # 7. LIMIT / OFFSET
        if self.dialect.name() == "mssql":
            if query.limit is not None and query.limit > 0:
                # MSSQL requires ORDER BY for OFFSET/FETCH; add default if missing
                if not query.sort:
                    sql += " ORDER BY (SELECT NULL)"
                offset = query.offset if query.offset and query.offset > 0 else 0
                sql += f" OFFSET {offset} ROWS FETCH NEXT {query.limit} ROWS ONLY"
            elif query.offset is not None and query.offset > 0:
                if not query.sort:
                    sql += " ORDER BY (SELECT NULL)"
                sql += f" OFFSET {query.offset} ROWS"
        else:
            limit_val = query.limit if query.limit is not None else -1
            offset_val = query.offset if query.offset is not None else 0
            clause = self.dialect.get_limit_offset(limit_val, offset_val)
            if clause:
                sql += f" {clause}"

        return TranspileResult(
            sql=self._replace_placeholders(sql),
            args=args,
        )

    # ------------------------------------------------------------------
    # JOINs (recursive)
    # ------------------------------------------------------------------

    def _process_join(
        self,
        include: dict[str, Any],
        parent_table: str,
        parent_alias: str,
        hydrator_path: str,
        schema: JsonQLSchema,
        select_parts: list[str],
        join_parts: list[str],
        where_conditions: list[str],
        args: list[Any],
    ) -> None:
        q = self._qi
        table_def = schema.tables.get(parent_table)
        if table_def is None:
            raise JsonQLTranspileError(
                f"Table definition not found for {parent_table}"
            )

        for rel_name, rel_config in include.items():
            relation = table_def.relations.get(rel_name)
            if relation is None:
                raise JsonQLTranspileError(
                    f"Relation {rel_name} not found on table {parent_table}"
                )

            target_table = relation.target or rel_name

            if hydrator_path == "":
                current_alias = rel_name
                current_hydrator = rel_name
            else:
                current_alias = f"{parent_alias}_{rel_name}"
                current_hydrator = f"{hydrator_path}__{rel_name}"

            if not isinstance(rel_config, dict):
                raise JsonQLTranspileError(
                    f"Invalid include configuration for {rel_name}"
                )

            # Pagination
            limit_val: int | None = None
            offset_val: int | None = None
            if "limit" in rel_config:
                limit_val = int(rel_config["limit"])
            if "skip" in rel_config:
                offset_val = int(rel_config["skip"])

            # Sort
            sort_parts: list[str] = []
            if "sort" in rel_config:
                sort_raw = rel_config["sort"]
                if isinstance(sort_raw, str):
                    sort_raw = [sort_raw]
                for s_item in sort_raw:
                    if isinstance(s_item, str):
                        desc = s_item.startswith("-")
                        fname = s_item[1:] if desc else s_item
                        order = "DESC" if desc else "ASC"
                        sort_parts.append(f"{q(fname)} {order}")

            # Fields
            if "fields" in rel_config and isinstance(rel_config["fields"], list):
                for f in rel_config["fields"]:
                    if isinstance(f, str):
                        alias = f"{current_hydrator}__{f}"
                        select_parts.append(
                            f"{q(current_alias)}.{q(f)} AS {q(alias)}"
                        )
            else:
                # No explicit fields — select all columns from the target table schema
                target_def = schema.tables.get(target_table)
                if target_def and target_def.fields:
                    for f in target_def.fields:
                        alias = f"{current_hydrator}__{f}"
                        select_parts.append(
                            f"{q(current_alias)}.{q(f)} AS {q(alias)}"
                        )
                else:
                    select_parts.append(f"{q(current_alias)}.*")

            # Aggregates (subqueries)
            if "aggregate" in rel_config and isinstance(rel_config["aggregate"], dict):
                for alias, agg_def in rel_config["aggregate"].items():
                    if not isinstance(agg_def, dict):
                        continue
                    for func_name, field_name in agg_def.items():
                        if not isinstance(field_name, str):
                            continue
                        sub_alias = f"{current_alias}_agg_{alias}"
                        if field_name == "*" and func_name == "count":
                            sub_select = "COUNT(*)"
                        else:
                            sub_select = (
                                f"{func_name.upper()}"
                                f"({q(sub_alias)}.{q(field_name)})"
                            )
                        # Join condition for subquery
                        if relation.type == "hasOne":
                            sub_on = (
                                f"{q(parent_alias)}.{q(relation.foreign_key)}"
                                f" = {q(sub_alias)}.id"
                            )
                        else:
                            sub_on = (
                                f"{q(sub_alias)}.{q(relation.foreign_key)}"
                                f" = {q(parent_alias)}.id"
                            )
                        sub_where = [sub_on]
                        if "where" in rel_config and isinstance(
                            rel_config["where"], dict
                        ):
                            conds, new_args = self._process_where(
                                rel_config["where"], sub_alias
                            )
                            sub_where.extend(conds)
                            args.extend(new_args)

                        full_sub = (
                            f"(SELECT {sub_select} FROM {q(target_table)}"
                            f" AS {q(sub_alias)}"
                            f" WHERE {' AND '.join(sub_where)})"
                        )
                        final_alias = f"{current_hydrator}__{alias}"
                        select_parts.append(f"{full_sub} AS {q(final_alias)}")

            # ON clause
            if relation.type == "hasOne":
                on_clause = (
                    f"{q(parent_alias)}.{q(relation.foreign_key)}"
                    f" = {q(current_alias)}.id"
                )
            elif relation.type == "hasMany":
                on_clause = (
                    f"{q(current_alias)}.{q(relation.foreign_key)}"
                    f" = {q(parent_alias)}.id"
                )
            else:  # belongsTo
                on_clause = (
                    f"{q(parent_alias)}.{q(relation.foreign_key)}"
                    f" = {q(current_alias)}.id"
                )

            # Include-level where → ON clause
            if "where" in rel_config and isinstance(rel_config["where"], dict):
                conds, new_args = self._process_where(
                    rel_config["where"], current_alias
                )
                if conds:
                    on_clause += " AND " + " AND ".join(conds)
                    args.extend(new_args)

            # Pagination (window function subquery)
            target_sql = q(target_table)
            has_pagination = limit_val is not None or offset_val is not None
            if has_pagination:
                total_limit = (limit_val or 0) + (offset_val or 0)
                if limit_val is not None:
                    on_clause += f" AND {q(current_alias)}.rn <= {total_limit}"
                if offset_val is not None:
                    on_clause += f" AND {q(current_alias)}.rn > {offset_val}"

                order_by = "id ASC"
                if sort_parts:
                    order_by = ", ".join(sort_parts)

                partition_key = (
                    relation.foreign_key
                    if relation.type in ("hasMany", "hasOne")
                    else "id"
                )
                target_sql = (
                    f"(SELECT *, ROW_NUMBER() OVER"
                    f" (PARTITION BY {q(partition_key)} ORDER BY {order_by})"
                    f" as rn FROM {q(target_table)})"
                )

            join_parts.append(
                f"LEFT JOIN {target_sql} AS {q(current_alias)} ON {on_clause}"
            )

            # Recursive nested includes
            if "include" in rel_config and isinstance(rel_config["include"], dict):
                self._process_join(
                    rel_config["include"],
                    target_table,
                    current_alias,
                    current_hydrator,
                    schema,
                    select_parts,
                    join_parts,
                    where_conditions,
                    args,
                )

    # ------------------------------------------------------------------
    # WHERE
    # ------------------------------------------------------------------

    def _process_where(
        self,
        where: dict[str, Any],
        table_alias: str,
    ) -> tuple[list[str], list[Any]]:
        q = self._qi
        conditions: list[str] = []
        args: list[Any] = []

        for field_name, cond in where.items():
            # OR clause — recursively process each sub-where
            if field_name in ("or", "OR"):
                if isinstance(cond, list):
                    or_conds: list[str] = []
                    for item in cond:
                        if isinstance(item, dict):
                            sub_conds, sub_args = self._process_where(
                                item, table_alias
                            )
                            if sub_conds:
                                or_conds.append(
                                    "(" + " AND ".join(sub_conds) + ")"
                                )
                                args.extend(sub_args)
                    if or_conds:
                        conditions.append("(" + " OR ".join(or_conds) + ")")
                continue

            # AND clause — recursively process each sub-where
            if field_name in ("and", "AND"):
                if isinstance(cond, list):
                    for item in cond:
                        if isinstance(item, dict):
                            sub_conds, sub_args = self._process_where(
                                item, table_alias
                            )
                            if sub_conds:
                                conditions.append(
                                    "(" + " AND ".join(sub_conds) + ")"
                                )
                                args.extend(sub_args)
                continue

            # NOT clause — recursively process the sub-where and negate
            if field_name in ("not", "NOT"):
                if isinstance(cond, dict):
                    sub_conds, sub_args = self._process_where(
                        cond, table_alias
                    )
                    if sub_conds:
                        conditions.append(
                            "NOT (" + " AND ".join(sub_conds) + ")"
                        )
                        args.extend(sub_args)
                continue

            if not _is_valid_identifier(field_name):
                raise JsonQLTranspileError(
                    f"Invalid field name in where clause: {field_name}"
                )

            if isinstance(cond, dict):
                known_ops = {
                    "eq",
                    "neq",
                    "ne",
                    "gt",
                    "gte",
                    "lt",
                    "lte",
                    "like",
                    "in",
                    "nin",
                    "contains",
                    "starts",
                    "ends",
                }
                for op_name in cond.keys():
                    if op_name not in known_ops:
                        raise JsonQLTranspileError(f"Unknown operator {op_name}")

                def field_ref_expr(value: Any) -> str | None:
                    if not isinstance(value, dict):
                        return None
                    ref = value.get("field")
                    if not isinstance(ref, str):
                        return None
                    if "." in ref:
                        rel, col = ref.split(".", 1)
                        if not _is_valid_identifier(rel) or not _is_valid_identifier(col):
                            raise JsonQLTranspileError(
                                f"Invalid field reference: {ref}"
                            )
                        return f"{q(rel)}.{q(col)}"
                    if not _is_valid_identifier(ref):
                        raise JsonQLTranspileError(
                            f"Invalid field reference: {ref}"
                        )
                    return f"{q(table_alias)}.{q(ref)}"

                if "eq" in cond:
                    v = cond["eq"]
                    ref_expr = field_ref_expr(v)
                    if ref_expr is not None:
                        conditions.append(
                            f"{q(table_alias)}.{q(field_name)} = {ref_expr}"
                        )
                    elif v is None:
                        conditions.append(
                            f"{q(table_alias)}.{q(field_name)} IS NULL"
                        )
                    else:
                        conditions.append(
                            f"{q(table_alias)}.{q(field_name)} = ?"
                        )
                        args.append(v)
                if "neq" in cond or "ne" in cond:
                    v = cond.get("neq", cond.get("ne"))
                    ref_expr = field_ref_expr(v)
                    if ref_expr is not None:
                        conditions.append(
                            f"{q(table_alias)}.{q(field_name)} != {ref_expr}"
                        )
                    elif v is None:
                        conditions.append(
                            f"{q(table_alias)}.{q(field_name)} IS NOT NULL"
                        )
                    else:
                        conditions.append(
                            f"{q(table_alias)}.{q(field_name)} != ?"
                        )
                        args.append(v)
                if "gt" in cond:
                    ref_expr = field_ref_expr(cond["gt"])
                    if ref_expr is not None:
                        conditions.append(f"{q(table_alias)}.{q(field_name)} > {ref_expr}")
                    else:
                        conditions.append(f"{q(table_alias)}.{q(field_name)} > ?")
                        args.append(cond["gt"])
                if "gte" in cond:
                    ref_expr = field_ref_expr(cond["gte"])
                    if ref_expr is not None:
                        conditions.append(f"{q(table_alias)}.{q(field_name)} >= {ref_expr}")
                    else:
                        conditions.append(f"{q(table_alias)}.{q(field_name)} >= ?")
                        args.append(cond["gte"])
                if "lt" in cond:
                    ref_expr = field_ref_expr(cond["lt"])
                    if ref_expr is not None:
                        conditions.append(f"{q(table_alias)}.{q(field_name)} < {ref_expr}")
                    else:
                        conditions.append(f"{q(table_alias)}.{q(field_name)} < ?")
                        args.append(cond["lt"])
                if "lte" in cond:
                    ref_expr = field_ref_expr(cond["lte"])
                    if ref_expr is not None:
                        conditions.append(f"{q(table_alias)}.{q(field_name)} <= {ref_expr}")
                    else:
                        conditions.append(f"{q(table_alias)}.{q(field_name)} <= ?")
                        args.append(cond["lte"])
                if "like" in cond:
                    conditions.append(
                        f"{q(table_alias)}.{q(field_name)} LIKE ?"
                    )
                    args.append(cond["like"])
                if "in" in cond:
                    vals = cond["in"]
                    if isinstance(vals, list) and vals:
                        placeholders = ", ".join(["?"] * len(vals))
                        conditions.append(
                            f"{q(table_alias)}.{q(field_name)} IN ({placeholders})"
                        )
                        args.extend(vals)
                if "nin" in cond:
                    vals = cond["nin"]
                    if isinstance(vals, list) and vals:
                        placeholders = ", ".join(["?"] * len(vals))
                        conditions.append(
                            f"{q(table_alias)}.{q(field_name)} NOT IN ({placeholders})"
                        )
                        args.extend(vals)
                if "contains" in cond:
                    conditions.append(
                        f"{q(table_alias)}.{q(field_name)} LIKE ?"
                    )
                    args.append(f"%{cond['contains']}%")
                if "starts" in cond:
                    conditions.append(
                        f"{q(table_alias)}.{q(field_name)} LIKE ?"
                    )
                    args.append(f"{cond['starts']}%")
                if "ends" in cond:
                    conditions.append(
                        f"{q(table_alias)}.{q(field_name)} LIKE ?"
                    )
                    args.append(f"%{cond['ends']}")
            else:
                # Shorthand: {"field": value} → eq
                if cond is None:
                    conditions.append(
                        f"{q(table_alias)}.{q(field_name)} IS NULL"
                    )
                else:
                    conditions.append(f"{q(table_alias)}.{q(field_name)} = ?")
                    args.append(cond)

        return conditions, args

    # ------------------------------------------------------------------
    # INSERT / UPDATE / DELETE
    # ------------------------------------------------------------------

    def transpile_insert(
        self, table_name: str, data: dict[str, Any]
    ) -> TranspileResult:
        """Generate an INSERT statement."""
        if not data:
            raise JsonQLTranspileError("insert data cannot be empty")
        if not _is_valid_identifier(table_name):
            raise JsonQLTranspileError(f"invalid table name: {table_name}")

        q = self._qi
        keys = sorted(data.keys())
        columns = [q(k) for k in keys]
        placeholders = ["?"] * len(keys)
        args = [data[k] for k in keys]

        sql = (
            f"INSERT INTO {q(table_name)}"
            f" ({', '.join(columns)})"
            f" VALUES ({', '.join(placeholders)})"
        )
        if self.dialect.supports_returning():
            sql += " RETURNING *"

        return TranspileResult(sql=self._replace_placeholders(sql), args=args)

    def transpile_update(
        self,
        table_name: str,
        patch: dict[str, Any],
        where: dict[str, Any] | None = None,
    ) -> TranspileResult:
        """Generate an UPDATE statement."""
        if not patch:
            raise JsonQLTranspileError("update patch cannot be empty")
        if not _is_valid_identifier(table_name):
            raise JsonQLTranspileError(f"invalid table name: {table_name}")

        q = self._qi
        keys = sorted(patch.keys())
        set_parts = [f"{q(k)} = ?" for k in keys]
        args: list[Any] = [patch[k] for k in keys]

        sql = f"UPDATE {q(table_name)} SET {', '.join(set_parts)}"

        if where:
            conds, w_args = self._process_where(where, table_name)
            if conds:
                # Remove table prefix for simple UPDATE (no alias)
                simple = [
                    c.replace(f"{q(table_name)}.", "", 1) for c in conds
                ]
                sql += " WHERE " + " AND ".join(simple)
                args.extend(w_args)

        if self.dialect.supports_returning():
            sql += " RETURNING *"

        return TranspileResult(sql=self._replace_placeholders(sql), args=args)

    def transpile_delete(
        self,
        table_name: str,
        where: dict[str, Any] | None = None,
    ) -> TranspileResult:
        """Generate a DELETE statement."""
        if not _is_valid_identifier(table_name):
            raise JsonQLTranspileError(f"invalid table name: {table_name}")

        q = self._qi
        sql = f"DELETE FROM {q(table_name)}"

        if where:
            conds, w_args = self._process_where(where, table_name)
            if conds:
                simple = [
                    c.replace(f"{q(table_name)}.", "", 1) for c in conds
                ]
                sql += " WHERE " + " AND ".join(simple)
                return TranspileResult(
                    sql=self._replace_placeholders(sql), args=w_args
                )

        return TranspileResult(sql=self._replace_placeholders(sql), args=[])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _qi(self, identifier: str) -> str:
        """Quote an identifier."""
        return self.dialect.quote_identifier(identifier)

    def _replace_placeholders(self, sql: str) -> str:
        """Replace ``?`` markers with dialect-specific placeholders."""
        count = 0
        parts: list[str] = []
        while True:
            idx = sql.find("?")
            if idx == -1:
                parts.append(sql)
                break
            parts.append(sql[:idx])
            parts.append(self.dialect.placeholder(count))
            count += 1
            sql = sql[idx + 1 :]
        return "".join(parts)
