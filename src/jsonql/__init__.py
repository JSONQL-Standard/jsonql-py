"""JSONQL Python SDK — A JSON-based query language for SQL databases."""

from .builder import MutationBuilder, QueryBuilder
from .conditions import (
    and_,
    contains,
    ends_with,
    eq,
    field,
    gt,
    gte,
    is_in,
    like,
    lt,
    lte,
    neq,
    not_,
    not_in,
    or_,
    starts_with,
)
from .dialect import (
    MySQLDialect,
    PostgresDialect,
    SQLDialect,
    SQLiteDialect,
    new_dialect,
)
from .driver import DatabaseDriver
from .engine import JsonQLEngine
from .errors import (
    JsonQLError,
    JsonQLExecutionError,
    JsonQLTranspileError,
    JsonQLValidationError,
)
from .factory import (
    connect_mongo,
    create_driver,
    create_driver_with_dsn,
    env_or,
    load_schema,
    must_connect_mongo,
    must_load_schema,
)
from .hydrator import ResultHydrator
from .logger import ConsoleLogger, Logger, NoOpLogger
from .mongo_driver import MongoDBDriver
from .mongo_transpiler import MongoResult, MongoTranspiler
from .parser import Parser, ParserOptions
from .transpiler import SQLTranspiler
from .types import (
    DistinctOption,
    JsonQLField,
    JsonQLMutation,
    JsonQLQuery,
    JsonQLRelation,
    JsonQLSchema,
    JsonQLSettings,
    JsonQLTable,
    TranspileResult,
    ValidationError,
    ValidationResult,
    parse_schema,
)
from .validator import Validator

__all__ = [
    # Types
    "JsonQLQuery",
    "JsonQLMutation",
    "DistinctOption",
    "JsonQLSchema",
    "JsonQLSettings",
    "JsonQLTable",
    "JsonQLField",
    "JsonQLRelation",
    "TranspileResult",
    "ValidationError",
    "ValidationResult",
    "parse_schema",
    # Core
    "Parser",
    "ParserOptions",
    "SQLTranspiler",
    "Validator",
    "ResultHydrator",
    # Dialect
    "SQLDialect",
    "PostgresDialect",
    "MySQLDialect",
    "SQLiteDialect",
    "new_dialect",
    # Builder
    "QueryBuilder",
    "MutationBuilder",
    # Conditions
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "is_in",
    "not_in",
    "like",
    "contains",
    "starts_with",
    "ends_with",
    "field",
    "and_",
    "or_",
    "not_",
    # Engine / Driver
    "DatabaseDriver",
    "JsonQLEngine",
    # MongoDB
    "MongoTranspiler",
    "MongoResult",
    "MongoDBDriver",
    # Factory / Helpers
    "env_or",
    "load_schema",
    "must_load_schema",
    "create_driver",
    "create_driver_with_dsn",
    "connect_mongo",
    "must_connect_mongo",
    # Errors
    "JsonQLError",
    "JsonQLValidationError",
    "JsonQLTranspileError",
    "JsonQLExecutionError",
    # Logger
    "Logger",
    "ConsoleLogger",
    "NoOpLogger",
]

__version__ = "0.1.0"
