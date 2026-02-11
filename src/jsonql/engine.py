"""High-level JSONQL engine with a builder-pattern API.

Provides a one-stop facade that wires parser → validator → transpiler
→ execute → hydrator into a single ``execute()`` call.

Example::

    engine = (
        JsonQLEngine.builder()
        .dialect("postgres")
        .schema(my_schema)
        .executor(run_sql)
        .build()
    )
    result = await engine.execute(raw_query, "users")
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from .dialect import SQLDialect, new_dialect
from .driver import DatabaseDriver
from .errors import JsonQLExecutionError
from .hydrator import ResultHydrator
from .logger import ConsoleLogger, Logger, NoOpLogger
from .parser import Parser, ParserOptions
from .transpiler import SQLTranspiler
from .types import JsonQLSchema, is_mutation
from .validator import Validator

# Type alias for the user-supplied executor callback
Executor = Callable[[str, list[Any]], Awaitable[list[dict[str, Any]]]]


class JsonQLEngine:
    """Opinionated engine that runs the full JSONQL pipeline."""

    def __init__(
        self,
        *,
        parser: Parser,
        transpiler: SQLTranspiler,
        hydrator: ResultHydrator,
        schema: JsonQLSchema | None = None,
        executor: Executor | None = None,
        driver: DatabaseDriver | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._parser = parser
        self._transpiler = transpiler
        self._hydrator = hydrator
        self._schema = schema
        self._executor = executor
        self._driver = driver
        self._logger = logger or NoOpLogger()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def execute(
        self,
        raw: dict[str, Any],
        table: str,
    ) -> dict[str, Any]:
        """Run the full pipeline: parse → validate → transpile → execute → hydrate."""
        # 1. Parse
        statement = self._parser.parse(raw, self._schema, table)

        # 2. Validate
        if self._schema:
            from .types import JsonQLQuery

            if isinstance(statement, JsonQLQuery):
                validator = Validator(self._schema, table)
                validator.validate_or_raise(statement)

        # 3. Transpile
        result = self._transpiler.transpile(statement, table, self._schema)
        self._logger.debug(f"[JSONQL] SQL: {result.sql}")
        self._logger.debug(f"[JSONQL] Params: {result.args}")

        # 4. Execute
        rows: list[dict[str, Any]] = []
        try:
            if self._driver:
                rows = await self._driver.query(result.sql, result.args)
            elif self._executor:
                rows = await self._executor(result.sql, result.args)
            else:
                raise JsonQLExecutionError(
                    "No executor or driver configured"
                )
        except JsonQLExecutionError:
            raise
        except Exception as exc:
            self._logger.error(f"[JSONQL] Execution error: {exc}")
            raise JsonQLExecutionError(str(exc), cause=exc) from exc

        # 5. Hydrate (queries only)
        if is_mutation(statement):
            return {"meta": {"query": raw}, "data": rows}

        data = self._hydrator.hydrate(rows, self._schema, table)
        return {"meta": {"query": raw}, "data": data}

    # ------------------------------------------------------------------
    # Builder
    # ------------------------------------------------------------------

    @staticmethod
    def builder() -> _EngineBuilder:
        """Return a new engine builder."""
        return _EngineBuilder()


class _EngineBuilder:
    """Fluent builder for ``JsonQLEngine``."""

    def __init__(self) -> None:
        self._dialect_name: str = "sqlite"
        self._schema: JsonQLSchema | None = None
        self._executor: Executor | None = None
        self._driver: DatabaseDriver | None = None
        self._logger: Logger | None = None
        self._parser_options: ParserOptions | None = None
        self._debug: bool = False

    def dialect(self, name: str) -> _EngineBuilder:
        self._dialect_name = name
        return self

    def postgres(self) -> _EngineBuilder:
        return self.dialect("postgres")

    def mysql(self) -> _EngineBuilder:
        return self.dialect("mysql")

    def sqlite(self) -> _EngineBuilder:
        return self.dialect("sqlite")

    def schema(self, schema: JsonQLSchema) -> _EngineBuilder:
        self._schema = schema
        return self

    def executor(self, fn: Executor) -> _EngineBuilder:
        self._executor = fn
        return self

    def driver(self, drv: DatabaseDriver) -> _EngineBuilder:
        self._driver = drv
        if not self._dialect_name or self._dialect_name == "sqlite":
            self._dialect_name = drv.dialect
        return self

    def parser_options(self, opts: ParserOptions) -> _EngineBuilder:
        self._parser_options = opts
        return self

    def debug(self, enabled: bool = True) -> _EngineBuilder:
        self._debug = enabled
        return self

    def logger(self, log: Logger) -> _EngineBuilder:
        self._logger = log
        return self

    def build(self) -> JsonQLEngine:
        dialect_obj: SQLDialect = new_dialect(self._dialect_name)
        logger: Logger
        if self._logger:
            logger = self._logger
        elif self._debug:
            logger = ConsoleLogger()
        else:
            logger = NoOpLogger()

        return JsonQLEngine(
            parser=Parser(self._parser_options),
            transpiler=SQLTranspiler(dialect_obj),
            hydrator=ResultHydrator(),
            schema=self._schema,
            executor=self._executor,
            driver=self._driver,
            logger=logger,
        )
