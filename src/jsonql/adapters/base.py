"""Framework-agnostic base handler for the JSONQL request pipeline.

Subclasses only need to provide framework-specific input extraction
and error creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..driver import DatabaseDriver
from ..hydrator import ResultHydrator
from ..logger import ConsoleLogger, Logger, NoOpLogger
from ..parser import Parser
from ..transpiler import SQLTranspiler
from ..types import JsonQLMutation, JsonQLQuery, JsonQLSchema, is_mutation
from ..validator import Validator

# Type aliases for lifecycle hooks
Hook = Callable[..., Any]


@dataclass
class AdapterOptions:
    """Configuration for a JSONQL adapter."""

    schema: JsonQLSchema | None = None
    schema_resolver: Callable[..., JsonQLSchema | None] | None = None
    driver: DatabaseDriver | None = None
    execute: Callable[[str, list[Any]], Awaitable[list[dict[str, Any]]]] | None = None
    dialect: str = "sqlite"

    debug: bool = False
    logger: Logger | None = None

    tables: list[str] | dict[str, str] | None = None

    # Lifecycle hooks
    before_parse: Hook | None = None
    after_parse: Hook | None = None
    before_query: Hook | None = None
    before_validate: Hook | None = None
    after_validate: Hook | None = None
    before_hydrate: Hook | None = None
    after_hydrate: Hook | None = None
    after_query: Hook | None = None

    # Mutation hooks
    before_create: Hook | None = None
    after_create: Hook | None = None
    before_update: Hook | None = None
    after_update: Hook | None = None
    before_delete: Hook | None = None
    after_delete: Hook | None = None


def _infer_mutation(http_method: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Inject ``op`` into the raw query based on the HTTP method."""
    if "op" in raw:
        return raw

    if "create" in raw:
        raw["op"] = "create"
        if "data" not in raw:
            raw["data"] = raw.get("create")
        return raw
    if "update" in raw:
        raw["op"] = "update"
        if "patch" not in raw:
            raw["patch"] = raw.get("update")
        return raw
    if "delete" in raw:
        raw["op"] = "delete"
        return raw

    upsert = raw.get("upsert")
    if isinstance(upsert, dict):
        if "where" in upsert and "update" in upsert:
            raw["op"] = "update"
            raw["where"] = upsert["where"]
            raw["patch"] = upsert["update"]
            return raw
        if "create" in upsert:
            raw["op"] = "create"
            raw["data"] = upsert["create"]
            return raw

    method = http_method.upper()
    if method == "POST" and "data" in raw:
        raw["op"] = "create"
    elif method in ("PUT", "PATCH") and ("patch" in raw or "where" in raw):
        raw["op"] = "update"
    elif method == "DELETE" and "where" in raw:
        raw["op"] = "delete"
    return raw


class BaseHandler:
    """Core pipeline: parse → validate → transpile → execute → hydrate."""

    def __init__(self, options: AdapterOptions) -> None:
        self.options = options
        self.parser = Parser()
        self.can_execute = bool(options.execute or options.driver)

        dialect = options.dialect
        if options.driver:
            dialect = options.driver.dialect

        self.transpiler = SQLTranspiler(dialect) if self.can_execute else None
        self.hydrator = ResultHydrator() if self.can_execute else None

        if options.logger:
            self.logger: Logger = options.logger
        elif options.debug:
            self.logger = ConsoleLogger()
        else:
            self.logger = NoOpLogger()

    async def process_request(
        self,
        raw_input: Any,
        context: Any,
        http_method: str,
        path_name: str,
    ) -> Any:
        """Run the full JSONQL pipeline and return the result dict."""
        raw_query = raw_input

        # 1. beforeParse
        if self.options.before_parse:
            raw_query = await _await_maybe(
                self.options.before_parse(raw_query, context)
            )

        # 2. Infer mutation
        if isinstance(raw_query, dict):
            raw_query = _infer_mutation(http_method, raw_query)

        # 3. Parse
        statement = self.parser.parse(raw_query)

        if self.options.after_parse:
            statement = await _await_maybe(
                self.options.after_parse(statement, context)
            )

        # 4. Resolve table name
        table_name: str | None = None
        if isinstance(statement, JsonQLQuery):
            table_name = statement.from_table or None
        elif isinstance(statement, JsonQLMutation):
            table_name = None  # mutations don't carry from_table

        table_name = self._resolve_table(statement, table_name, path_name)

        if isinstance(statement, JsonQLQuery) and table_name and not statement.from_table:
            statement.from_table = table_name

        # 5. beforeQuery
        if self.options.before_query:
            statement = await _await_maybe(
                self.options.before_query(statement, context)
            )

        # 6. beforeValidate
        if self.options.before_validate:
            statement = await _await_maybe(
                self.options.before_validate(statement, context)
            )

        # 7. Resolve schema
        schema: JsonQLSchema | None = None
        if self.options.schema_resolver:
            schema = await _await_maybe(
                self.options.schema_resolver(context)
            )
        else:
            schema = self.options.schema

        # 8. Validate
        if schema and table_name and isinstance(statement, JsonQLQuery):
            table_def = schema.tables.get(table_name)
            if table_def and table_def.fields:
                validator = Validator(schema, table_name)
                validation = validator.validate(statement)

                if self.options.after_validate:
                    await _await_maybe(
                        self.options.after_validate(validation, context)
                    )

                if not validation.valid:
                    return {"error": "Validation Error", "details": [
                        {"code": e.code, "message": e.message, "path": e.path}
                        for e in validation.errors
                    ]}, 400

        # 9. Execute
        if self.can_execute and self.transpiler and table_name:
            is_mut = is_mutation(statement)

            # Mutation before-hooks
            if is_mut and isinstance(statement, JsonQLMutation):
                if statement.op == "create" and self.options.before_create:
                    statement = await _await_maybe(
                        self.options.before_create(statement, context)
                    )
                elif statement.op == "update" and self.options.before_update:
                    statement = await _await_maybe(
                        self.options.before_update(statement, context)
                    )
                elif statement.op == "delete" and self.options.before_delete:
                    statement = await _await_maybe(
                        self.options.before_delete(statement, context)
                    )

            # Transpile
            result = self.transpiler.transpile(statement, table_name, schema)
            self.logger.debug(f"[JSONQL] SQL: {result.sql}")
            self.logger.debug(f"[JSONQL] Params: {result.args}")

            # Execute
            flat_rows: list[dict[str, Any]] = []
            try:
                if self.options.driver:
                    flat_rows = await self.options.driver.query(result.sql, result.args)
                elif self.options.execute:
                    flat_rows = await self.options.execute(result.sql, result.args)
            except Exception as exc:
                self.logger.error(f"[JSONQL] Execution error: {exc}")
                return {"error": "Execution Error", "details": str(exc)}, 400

            # Mutation after-hooks
            if is_mut and isinstance(statement, JsonQLMutation):
                data: Any = {"meta": {"query": raw_input}, "data": flat_rows}
                if statement.op == "create" and self.options.after_create:
                    data = await _await_maybe(self.options.after_create(data, context))
                elif statement.op == "update" and self.options.after_update:
                    data = await _await_maybe(self.options.after_update(data, context))
                elif statement.op == "delete" and self.options.after_delete:
                    data = await _await_maybe(self.options.after_delete(data, context))
                if self.options.after_query:
                    data = await _await_maybe(self.options.after_query(data, context))
                return data, 200

            # Hydrate
            if self.hydrator:
                if self.options.before_hydrate:
                    flat_rows = await _await_maybe(
                        self.options.before_hydrate(flat_rows, context)
                    )

                hydrated = self.hydrator.hydrate(flat_rows, schema, table_name)

                if self.options.after_hydrate:
                    hydrated = await _await_maybe(
                        self.options.after_hydrate(hydrated, context)
                    )

                result_data: Any = {"meta": {"query": raw_input}, "data": hydrated}
                if self.options.after_query:
                    result_data = await _await_maybe(
                        self.options.after_query(result_data, context)
                    )
                return result_data, 200

        return None, 200

    def _resolve_table(
        self,
        statement: Any,
        table_name: str | None,
        path_name: str,
    ) -> str | None:
        tables = self.options.tables

        if tables is None:
            return table_name or path_name or None

        if isinstance(tables, list):
            if not table_name:
                table_name = path_name
            if table_name not in tables:
                raise ValueError(f"Table '{table_name}' is not allowed")
            return table_name

        # dict mapping
        mapped = tables.get(path_name)
        if mapped:
            return mapped
        if not path_name and table_name:
            if table_name not in tables.values():
                raise ValueError(f"Table '{table_name}' is not allowed")
        return table_name


async def _await_maybe(value: Any) -> Any:
    """Await a value if it is a coroutine, otherwise return it directly."""
    import asyncio

    if asyncio.iscoroutine(value) or asyncio.isfuture(value):
        return await value
    return value
