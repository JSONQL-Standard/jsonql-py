"""Factory functions and helpers for the JSONQL Python SDK.

Provides one-liner setup utilities matching the Go SDK's DX:

- ``env_or(key, fallback)`` — read env vars with defaults
- ``load_schema(path)`` — load a schema JSON file
- ``must_load_schema(path)`` — load a schema or raise on error
- ``create_driver(dialect)`` — create a driver from env vars
- ``create_driver_with_dsn(dialect, dsn)`` — create a driver with explicit DSN
- ``connect_mongo(uri, db_name)`` — connect to MongoDB
- ``must_connect_mongo(uri, db_name)`` — connect to MongoDB or raise

Usage::

    from jsonql import create_driver, must_load_schema, env_or

    schema = must_load_schema(env_or("SCHEMA_PATH", "schema.json"))
    driver = create_driver("postgres")
"""

from __future__ import annotations

import json
import os
from typing import Any

from .types import JsonQLSchema, parse_schema


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def env_or(key: str, fallback: str) -> str:
    """Return the environment variable *key*, or *fallback* if unset/empty.

    Mirrors Go's ``jsonql.EnvOr(key, fallback)``.
    """
    return os.environ.get(key) or fallback


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------


def load_schema(path: str) -> JsonQLSchema:
    """Read and parse a JSONQL schema from a JSON file.

    Raises ``FileNotFoundError`` if *path* does not exist, or
    ``ValueError`` if the JSON is malformed.

    Usage::

        schema = load_schema("path/to/schema.json")
    """
    with open(path) as fh:
        raw = json.load(fh)
    return parse_schema(raw)


def must_load_schema(path: str) -> JsonQLSchema:
    """Like :func:`load_schema` but raises ``SystemExit`` on failure.

    Intended for startup code where a missing schema is fatal::

        schema = must_load_schema(os.getenv("SCHEMA_PATH", "schema.json"))
    """
    try:
        return load_schema(path)
    except Exception as exc:
        raise SystemExit(f"Failed to load schema from {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Driver factory
# ---------------------------------------------------------------------------

# Default DSN values per dialect (matching Go SDK defaults)
_DEFAULT_DSN: dict[str, str] = {
    "postgres": "postgresql://jsonql:password@localhost:5432/jsonql_test?sslmode=disable",
    "mysql": "jsonql:password@tcp(localhost:3306)/jsonql_test",
    "mssql": "mssql+pymssql://sa:Password@localhost:1433/jsonql_test",
    "sqlite": ":memory:",
}


def create_driver(dialect: str) -> Any:
    """Create a database driver for *dialect* using environment variables.

    Reads ``DB_DSN`` (or ``DB_FILENAME`` for sqlite) to configure the
    connection.  Falls back to sensible defaults for local development.

    Supported dialects: ``postgres``, ``mysql``, ``sqlite``, ``mssql``

    Returns a :class:`DatabaseDriver` subclass ready for use with
    :class:`JsonQLEngine`.

    Usage::

        driver = create_driver("postgres")
        engine = JsonQLEngine.builder().driver(driver).schema(schema).build()
    """
    if dialect == "sqlite":
        filename = env_or("DB_FILENAME", _DEFAULT_DSN["sqlite"])
        return create_driver_with_dsn("sqlite", filename)
    else:
        dsn = env_or("DB_DSN", _DEFAULT_DSN.get(dialect, ""))
        if not dsn:
            raise ValueError(f"Unsupported dialect: {dialect}")
        return create_driver_with_dsn(dialect, dsn)


def create_driver_with_dsn(dialect: str, dsn: str) -> Any:
    """Create a database driver for *dialect* with an explicit *dsn*.

    Usage::

        driver = create_driver_with_dsn("postgres", "postgresql://user:pass@host:5432/db")
    """
    if dialect == "postgres":
        return _create_postgres_driver(dsn)
    elif dialect == "mysql":
        return _create_mysql_driver(dsn)
    elif dialect == "sqlite":
        return _create_sqlite_driver(dsn)
    elif dialect == "mssql":
        return _create_mssql_driver(dsn)
    else:
        raise ValueError(f"Unsupported dialect: {dialect}")


# ---------------------------------------------------------------------------
# MongoDB connection helpers
# ---------------------------------------------------------------------------


def connect_mongo(uri: str, db_name: str) -> Any:
    """Connect to MongoDB and return a ``(client, database)`` tuple.

    Requires ``pymongo`` to be installed.

    Usage::

        client, db = connect_mongo("mongodb://localhost:27017", "mydb")
    """
    from pymongo import MongoClient

    client = MongoClient(uri)
    # Verify connectivity
    client.admin.command("ping")
    return client, client[db_name]


def must_connect_mongo(uri: str, db_name: str) -> Any:
    """Like :func:`connect_mongo` but raises ``SystemExit`` on failure.

    Returns ``(client, database)``.

    Usage::

        client, db = must_connect_mongo("mongodb://localhost:27017", "mydb")
    """
    try:
        return connect_mongo(uri, db_name)
    except Exception as exc:
        raise SystemExit(f"Failed to connect to MongoDB at {uri}: {exc}") from exc


# ---------------------------------------------------------------------------
# Internal driver implementations
# ---------------------------------------------------------------------------


def _normalize_numeric_rows(rows: list[dict[str, Any]]) -> None:
    """In-place normalise numeric types so results are JSON-safe.

    * ``Decimal`` → ``int`` (if whole) or ``float``  (psycopg2, mysql-connector)
    * ``float``   → ``int`` (if whole)               (sqlite3)

    Recurses into nested dicts and lists for hydrated / joined results.
    """
    from decimal import Decimal

    for row in rows:
        for key, val in row.items():
            if isinstance(val, Decimal):
                row[key] = int(val) if val == int(val) else float(val)
            elif isinstance(val, float) and val == int(val):
                row[key] = int(val)
            elif isinstance(val, dict):
                _normalize_numeric_rows([val])
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        _normalize_numeric_rows([item])


class _SyncDatabaseDriver:
    """Synchronous database driver that wraps stdlib/third-party DB drivers.

    Adapts synchronous database APIs to the async ``DatabaseDriver`` interface
    used by the JSONQL engine.
    """

    def __init__(self, conn: Any, dialect_name: str) -> None:
        self._conn = conn
        self._dialect_name = dialect_name

    @property
    def dialect(self) -> str:
        return self._dialect_name

    async def query(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        rows = self._query_sync(sql, params)
        _normalize_numeric_rows(rows)
        return rows

    def _query_sync(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def close(self) -> None:
        if hasattr(self._conn, "close"):
            self._conn.close()


class _PostgresDriver(_SyncDatabaseDriver):
    def __init__(self, conn: Any) -> None:
        super().__init__(conn, "postgres")

    def _query_sync(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        import re

        import psycopg2.extras

        # Convert $1, $2 placeholders to %s
        sql = re.sub(r"\$\d+", "%s", sql)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(sql, params or None)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            return []
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()


class _MySQLDriver(_SyncDatabaseDriver):
    def __init__(self, conn: Any) -> None:
        super().__init__(conn, "mysql")

    def _query_sync(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        # Convert ? placeholders to %s
        sql = sql.replace("?", "%s")
        cur = self._conn.cursor()
        try:
            cur.execute(sql, params or None)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            return []
        finally:
            cur.close()


class _SQLiteDriver(_SyncDatabaseDriver):
    def __init__(self, conn: Any) -> None:
        super().__init__(conn, "sqlite")

    def _query_sync(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        try:
            cur.execute(sql, params)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            self._conn.commit()
            return []
        finally:
            cur.close()


class _MSSQLDriver(_SyncDatabaseDriver):
    def __init__(self, conn: Any) -> None:
        super().__init__(conn, "mssql")

    def _query_sync(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        import re

        # Convert @p1, @p2 placeholders to %s
        sql = re.sub(r"@p\d+", "%s", sql)
        cur = self._conn.cursor()
        try:
            cur.execute(sql, params or None)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            return []
        finally:
            cur.close()


def _create_postgres_driver(dsn: str) -> _PostgresDriver:
    import psycopg2

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return _PostgresDriver(conn)


def _create_mysql_driver(dsn: str) -> _MySQLDriver:
    import pymysql
    from urllib.parse import urlparse, unquote

    # Parse mysql://user:pass@host:port/db format
    parsed = urlparse(dsn)
    conn = pymysql.connect(
        host=parsed.hostname or "localhost",
        user=unquote(parsed.username) if parsed.username else "jsonql",
        password=unquote(parsed.password) if parsed.password else "password",
        database=(parsed.path or "/jsonql_test").lstrip("/"),
        port=parsed.port or 3306,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    return _MySQLDriver(conn)


def _create_sqlite_driver(filename: str) -> _SQLiteDriver:
    import sqlite3

    conn = sqlite3.connect(filename, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return _SQLiteDriver(conn)


def _create_mssql_driver(dsn: str) -> _MSSQLDriver:
    import pymssql
    from urllib.parse import urlparse, unquote

    # Parse mssql+pymssql://user:pass@host:port/db format
    clean_dsn = dsn.replace("mssql+pymssql://", "mssql://")
    parsed = urlparse(clean_dsn)
    conn = pymssql.connect(
        server=parsed.hostname or "localhost",
        user=unquote(parsed.username) if parsed.username else "sa",
        password=unquote(parsed.password) if parsed.password else "password",
        database=(parsed.path or "/jsonql_test").lstrip("/"),
        port=parsed.port or 1433,
        autocommit=True,
        as_dict=True,
        tds_version="7.0",
        conn_properties="",
    )
    return _MSSQLDriver(conn)
