"""MongoDB base handler for the JSONQL request pipeline.

Mirrors ``base.py`` (SQL) but uses ``MongoTranspiler`` and a PyMongo
database instead of a SQL transpiler and driver.  All framework adapters
for MongoDB (Flask, FastAPI, Django) delegate to this handler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..logger import ConsoleLogger, Logger, NoOpLogger
from ..mongo_transpiler import MongoResult, MongoTranspiler
from ..parser import Parser
from ..types import JsonQLMutation, JsonQLQuery, JsonQLSchema, is_mutation
from ..validator import Validator

Hook = Callable[..., Any]


@dataclass
class MongoAdapterOptions:
    """Configuration for a MongoDB JSONQL adapter."""

    database: Any = None  # pymongo Database or motor AsyncIOMotorDatabase
    schema: JsonQLSchema | None = None
    schema_resolver: Callable[..., JsonQLSchema | None] | None = None

    debug: bool = False
    logger: Logger | None = None

    tables: list[str] | dict[str, str] | None = None

    # Lifecycle hooks
    before_parse: Hook | None = None
    after_parse: Hook | None = None
    before_query: Hook | None = None
    before_validate: Hook | None = None
    after_validate: Hook | None = None
    after_query: Hook | None = None

    # Mutation hooks
    before_create: Hook | None = None
    after_create: Hook | None = None
    before_update: Hook | None = None
    after_update: Hook | None = None
    before_delete: Hook | None = None
    after_delete: Hook | None = None


def infer_mutation(http_method: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Inject ``op`` into the raw query based on the HTTP method.

    This is the public API — matches Go's ``BuildRESTMutation``.

    Rules:
    - If ``op`` already present, return as-is
    - Explicit keys (``create``, ``update``, ``delete``) take priority
    - POST with ``data`` key → create
    - PATCH/PUT with ``patch`` or ``where`` → update
    - DELETE with ``where`` → delete
    - POST without ``data`` → treated as a query (not a mutation)
    """
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

    method = http_method.upper()
    if method == "POST" and "data" in raw:
        raw["op"] = "create"
    elif method in ("PUT", "PATCH") and ("patch" in raw or "where" in raw):
        raw["op"] = "update"
    elif method == "DELETE" and "where" in raw:
        raw["op"] = "delete"
    return raw


def get_id_from_query(query_params: dict[str, Any] | Any) -> Any:
    """Extract ``id`` from a query-string dict, with int coercion.

    Mirrors Go's ``GetIDFromQuery``.

    Returns the ID (int if numeric, str otherwise) or ``None``.
    """
    raw = None
    if hasattr(query_params, "get"):
        raw = query_params.get("id")
    elif isinstance(query_params, dict):
        raw = query_params.get("id")

    if raw is None:
        return None

    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return None

    raw = str(raw)
    try:
        return int(raw)
    except (ValueError, TypeError):
        return raw


def build_rest_mutation(
    method: str,
    query_params: Any,
    body: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build a JSONQL mutation from REST semantics.

    Mirrors Go's ``BuildRESTMutation``.

    - POST with ``data`` → create mutation
    - PATCH/PUT → update mutation (needs ``?id=`` or ``where`` in body)
    - DELETE → delete mutation (needs ``?id=`` or ``where`` in body)

    Returns ``None`` if no mutation can be inferred.
    """
    method = method.upper()
    if body is None:
        body = {}

    if method == "POST" and "data" in body:
        return {"op": "create", "data": body["data"]}

    if method in ("PUT", "PATCH"):
        mutation: dict[str, Any] = {"op": "update"}
        if "patch" in body:
            mutation["patch"] = body["patch"]
        elif "data" in body:
            mutation["patch"] = body["data"]
        if "where" in body:
            mutation["where"] = body["where"]
        else:
            id_val = get_id_from_query(query_params)
            if id_val is not None:
                mutation["where"] = {"id": id_val}
        return mutation

    if method == "DELETE":
        mutation = {"op": "delete"}
        if "where" in body:
            mutation["where"] = body["where"]
        else:
            id_val = get_id_from_query(query_params)
            if id_val is not None:
                mutation["where"] = {"id": id_val}
        return mutation

    return None


class MongoBaseHandler:
    """Core MongoDB pipeline: parse → validate → transpile → execute."""

    def __init__(self, options: MongoAdapterOptions) -> None:
        self.options = options
        self.parser = Parser()
        self.transpiler = MongoTranspiler()
        self.db = options.database

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
    ) -> tuple[Any, int]:
        """Run the full MongoDB JSONQL pipeline and return ``(result, status)``."""
        raw_query = raw_input

        # 1. beforeParse
        if self.options.before_parse:
            raw_query = await _await_maybe(self.options.before_parse(raw_query, context))

        # 2. Infer mutation
        if isinstance(raw_query, dict):
            raw_query = infer_mutation(http_method, raw_query)

        # 3. Parse
        statement = self.parser.parse(raw_query)

        if self.options.after_parse:
            statement = await _await_maybe(self.options.after_parse(statement, context))

        # 4. Resolve collection name
        collection_name = self._resolve_table(statement, path_name)

        if isinstance(statement, JsonQLQuery) and collection_name and not statement.from_table:
            statement.from_table = collection_name

        # 5. beforeQuery
        if self.options.before_query:
            statement = await _await_maybe(self.options.before_query(statement, context))

        # 6. beforeValidate
        if self.options.before_validate:
            statement = await _await_maybe(self.options.before_validate(statement, context))

        # 7. Resolve schema
        schema: JsonQLSchema | None = None
        if self.options.schema_resolver:
            schema = await _await_maybe(self.options.schema_resolver(context))
        else:
            schema = self.options.schema

        # 8. Validate
        if schema and collection_name and isinstance(statement, JsonQLQuery):
            table_def = schema.tables.get(collection_name)
            if table_def and table_def.fields:
                validator = Validator(schema, collection_name)
                validation = validator.validate(statement)

                if self.options.after_validate:
                    await _await_maybe(self.options.after_validate(validation, context))

                if not validation.valid:
                    return {
                        "error": "Validation Error",
                        "error_code": "VALIDATION_ERROR",
                        "details": [
                            {"code": e.code, "message": e.message, "path": e.path}
                            for e in validation.errors
                        ],
                    }, 400

        # 9. Transpile
        if not collection_name:
            return None, 200

        is_mut = is_mutation(statement)

        # Mutation before-hooks
        if is_mut and isinstance(statement, JsonQLMutation):
            if statement.op == "create" and self.options.before_create:
                statement = await _await_maybe(self.options.before_create(statement, context))
            elif statement.op == "update" and self.options.before_update:
                statement = await _await_maybe(self.options.before_update(statement, context))
            elif statement.op == "delete" and self.options.before_delete:
                statement = await _await_maybe(self.options.before_delete(statement, context))

        mongo_result = self.transpiler.transpile(statement, collection_name)
        self.logger.debug(f"[JSONQL] Mongo op: {mongo_result.operation}")
        self.logger.debug(f"[JSONQL] Collection: {mongo_result.collection}")

        # 10. Execute
        try:
            rows = self._execute_sync(mongo_result)
        except Exception as exc:
            self.logger.error(f"[JSONQL] Execution error: {exc}")
            error_code = getattr(exc, "code", "EXECUTION_ERROR")
            resp = {"error": "Execution Error", "error_code": error_code}
            resp["details"] = str(exc)
            return resp, 400

        # 11. Mutation after-hooks
        if is_mut and isinstance(statement, JsonQLMutation):
            data: Any = {"meta": {"query": raw_input}, "data": rows}
            if statement.op == "create" and self.options.after_create:
                data = await _await_maybe(self.options.after_create(data, context))
            elif statement.op == "update" and self.options.after_update:
                data = await _await_maybe(self.options.after_update(data, context))
            elif statement.op == "delete" and self.options.after_delete:
                data = await _await_maybe(self.options.after_delete(data, context))
            if self.options.after_query:
                data = await _await_maybe(self.options.after_query(data, context))
            return data, 200

        # 12. Return query result
        result_data: Any = {"meta": {"query": raw_input}, "data": rows}
        if self.options.after_query:
            result_data = await _await_maybe(self.options.after_query(result_data, context))
        return result_data, 200

    def _execute_sync(self, result: MongoResult) -> list[dict[str, Any]]:
        """Execute a MongoResult against the PyMongo database."""
        coll = self.db[result.collection]
        op = result.operation

        if op == "find":
            kwargs: dict[str, Any] = {}
            if result.projection:
                kwargs["projection"] = result.projection
            if result.sort:
                kwargs["sort"] = result.sort
            if result.skip:
                kwargs["skip"] = result.skip
            if result.limit:
                kwargs["limit"] = result.limit
            docs = list(coll.find(result.filter, **kwargs))
            for doc in docs:
                doc.pop("_id", None)
            return docs

        if op == "aggregate":
            docs = list(coll.aggregate(result.pipeline or []))
            for doc in docs:
                doc.pop("_id", None)
            return docs

        if op == "insert_one":
            doc = dict(result.document) if isinstance(result.document, dict) else {}
            coll.insert_one(doc)
            doc.pop("_id", None)
            return [doc]

        if op == "insert_many":
            insert_docs: list[dict[str, Any]] = (
                result.document if isinstance(result.document, list) else [result.document]  # type: ignore[list-item]
            )
            coll.insert_many(insert_docs)
            for doc in insert_docs:
                if isinstance(doc, dict):
                    doc.pop("_id", None)
            return insert_docs

        if op == "update_many":
            coll.update_many(result.filter, result.update)
            updated = list(coll.find(result.filter))
            for doc in updated:
                doc.pop("_id", None)
            return updated

        if op == "delete_many":
            matched = list(coll.find(result.filter))
            for doc in matched:
                doc.pop("_id", None)
            coll.delete_many(result.filter)
            return matched

        raise ValueError(f"Unsupported operation: {op}")

    def _resolve_table(
        self,
        statement: Any,
        path_name: str,
    ) -> str | None:
        tables = self.options.tables
        table_name: str | None = None

        if isinstance(statement, JsonQLQuery):
            table_name = statement.from_table or None

        if tables is None:
            return table_name or path_name or None

        if isinstance(tables, list):
            if not table_name:
                table_name = path_name
            if table_name not in tables:
                raise ValueError(f"Collection '{table_name}' is not allowed")
            return table_name

        # dict mapping
        mapped = tables.get(path_name)
        if mapped:
            return mapped
        if not path_name and table_name:
            if table_name not in tables.values():
                raise ValueError(f"Collection '{table_name}' is not allowed")
        return table_name


async def _await_maybe(value: Any) -> Any:
    """Await if coroutine, return directly otherwise."""
    import asyncio

    if asyncio.iscoroutine(value) or asyncio.isfuture(value):
        return await value
    return value
