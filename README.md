# jsonql-py

[![CI](https://github.com/JSONQL-Standard/jsonql-py/actions/workflows/ci.yml/badge.svg)](https://github.com/JSONQL-Standard/jsonql-py/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/jsonql-py)](https://pypi.org/project/jsonql-py/)
[![Python](https://img.shields.io/pypi/pyversions/jsonql-py)](https://pypi.org/project/jsonql-py/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Python SDK** for [JSONQL](https://github.com/JSONQL-Standard/jsonql-spec) — a JSON-based query language for SQL and MongoDB databases.

| | |
|---|---|
| **Package** | [`jsonql-py`](https://pypi.org/project/jsonql-py/) |
| **Import** | `import jsonql` |
| **Version** | 0.1.0 |
| **Python** | 3.10+ |
| **Docs** | [jsonql.org/sdk/python](https://jsonql.org/sdk/python/) |

## Features

- Pythonic `QueryBuilder` and `MutationBuilder` with condition helpers
- `Parser` for JSONQL query validation
- `SQLTranspiler` with dialect support (Postgres, MySQL, SQLite, MSSQL)
- `MongoTranspiler` for MongoDB aggregation pipelines
- `MongoDriver` for MongoDB execution
- `ResultHydrator` for nested JSON reconstruction
- `Validator` for schema-based field permission checking
- `JsonQLEngine` with builder pattern for full pipeline
- Async executor support
- Framework adapters for **Flask**, **FastAPI**, and **Django** (SQL + MongoDB variants)
- Type hints throughout (PEP 561)

## Installation

```bash
pip install jsonql-py
```

> **Note:** The PyPI package name is `jsonql-py`, but the import name is `import jsonql`.

With framework extras:

```bash
pip install jsonql-py[flask]      # Flask adapter
pip install jsonql-py[fastapi]    # FastAPI + uvicorn
pip install jsonql-py[django]     # Django REST Framework
pip install jsonql-py[postgres]   # psycopg2-binary
pip install jsonql-py[mysql]      # mysql-connector-python
```

## Quick Start

### Query Builder

```python
from jsonql import QueryBuilder
from jsonql.conditions import eq, gt, field, and_

query = (
    QueryBuilder()
    .from_table("users")
    .select("id", "name", "email")
    .where(and_(
        field("age", gt(18)),
        field("status", eq("active")),
    ))
    .order_by("name", "-age")
    .limit(10)
    .build()
)
```

### Mutation Builder

```python
from jsonql import MutationBuilder

# Create
mutation = MutationBuilder().create({"name": "Alice", "age": 30}).build()

# Update
mutation = (
    MutationBuilder()
    .update({"name": "Bob"})
    .where({"id": {"eq": 1}})
    .build()
)

# Delete
mutation = MutationBuilder().delete().where({"id": {"eq": 1}}).build()
```

### Transpiler

```python
from jsonql import Parser, SQLTranspiler

parser = Parser()
query = parser.parse({
    "fields": ["id", "name"],
    "where": {"status": {"eq": "active"}},
    "sort": ["-name"],
    "limit": 10,
})

transpiler = SQLTranspiler("postgres")
result = transpiler.transpile(query, "users")
print(result.sql)
# SELECT "users"."id", "users"."name" FROM "users"
#   WHERE "users"."status" = $1 ORDER BY "users"."name" DESC LIMIT 10
print(result.args)  # ['active']
```

### Schema Validation

```python
from jsonql import Validator, JsonQLQuery
from jsonql.types import JsonQLSchema, JsonQLTable, JsonQLField

schema = JsonQLSchema(tables={
    "users": JsonQLTable(fields={
        "id": JsonQLField(type="integer"),
        "name": JsonQLField(type="string"),
        "secret": JsonQLField(type="string", allow_select=False),
    }),
})

validator = Validator(schema, "users")
result = validator.validate(JsonQLQuery(fields=["id", "name"]))
assert result.valid

# Raises JsonQLValidationError
validator.validate_or_raise(JsonQLQuery(fields=["secret"]))
```

### Engine (Full Pipeline)

```python
from jsonql import JsonQLEngine
from jsonql.types import parse_schema

schema = parse_schema({...})  # Your schema JSON

async def run_sql(sql: str, params: list) -> list[dict]:
    # Your database execution logic
    ...

engine = (
    JsonQLEngine.builder()
    .postgres()
    .schema(schema)
    .executor(run_sql)
    .build()
)
```

## Framework Adapters

### Flask

```python
from flask import Flask
from jsonql.adapters import create_flask_blueprint, AdapterOptions

app = Flask(__name__)
bp = create_flask_blueprint(AdapterOptions(
    dialect="postgres",
    execute=run_sql,
    schema=my_schema,
))
app.register_blueprint(bp, url_prefix="/jsonql")
```

### FastAPI

```python
from fastapi import FastAPI
from jsonql.adapters import create_fastapi_router, AdapterOptions

app = FastAPI()
router = create_fastapi_router(AdapterOptions(
    dialect="postgres",
    execute=run_sql,
    schema=my_schema,
))
app.include_router(router, prefix="/jsonql")
```

### Django

```python
# urls.py
from django.urls import path
from jsonql.adapters import JsonQLDjangoView, AdapterOptions

options = AdapterOptions(
    dialect="postgres", execute=run_sql, schema=my_schema
)

urlpatterns = [
    path("jsonql/", JsonQLDjangoView.as_view(options=options)),
    path("jsonql/<path:path>/", JsonQLDjangoView.as_view(options=options)),
]
```

### MongoDB Variants

Each framework adapter has a MongoDB variant:

```python
from jsonql.adapters import (
    create_flask_mongo_blueprint,
    create_fastapi_mongo_router,
    JsonQLDjangoMongoView,
    MongoAdapterOptions,
)
```

## Core API

| Export | Purpose |
|--------|---------|
| `Parser` | Parse & validate incoming JSON |
| `SQLTranspiler` | Convert parsed query → SQL + params |
| `MongoTranspiler` | Convert parsed query → MongoDB pipeline |
| `MongoDriver` | Execute MongoDB pipelines |
| `Validator` | Schema-based permission checking |
| `QueryBuilder` | Fluent query construction |
| `MutationBuilder` | Fluent mutation construction |
| `ResultHydrator` | Flatten SQL joins → nested JSON |
| `JsonQLEngine` | Full pipeline with builder pattern |
| `DatabaseDriver` | Abstract database driver interface |

## Supported Dialects

| Dialect    | Placeholder | Quoting      | RETURNING |
|------------|-------------|--------------|-----------|
| `postgres` | `$1, $2`    | `"col"`      | ✅        |
| `mysql`    | `?, ?`      | `` `col` ``  | ❌        |
| `sqlite`   | `?, ?`      | `"col"`      | ❌        |
| `mssql`    | `@p1, @p2`  | `[col]`      | ❌        |

## Condition Helpers

```python
from jsonql.conditions import (
    eq, neq, gt, gte, lt, lte,
    is_in, not_in, like, contains, starts_with, ends_with,
    field, and_, or_, not_,
)
```

## Error Hierarchy

```
JsonQLError
├── JsonQLValidationError   (code: VALIDATION_ERROR)
├── JsonQLTranspileError    (code: TRANSPILE_ERROR)
├── JsonQLExecutionError    (code: EXECUTION_ERROR)
└── AdapterError
```

## Compliance

All 6 Python integration adapters pass the full compliance test suite:

| Adapter | Type | PostgreSQL |
|---------|------|:----------:|
| **Flask** | simple | ✅ 135/135 |
| **Flask** | lifecycle | ✅ 135/135 |
| **FastAPI** | simple | ✅ 135/135 |
| **FastAPI** | lifecycle | ✅ 135/135 |
| **Django** | simple | ✅ 135/135 |
| **Django** | lifecycle | ✅ 135/135 |

Tests run via [jsonql-tests](https://github.com/JSONQL-Standard/jsonql-tests).

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/jsonql/
```

## Links

- 📖 [Documentation](https://jsonql.org/sdk/python/)
- 📋 [JSONQL Spec](https://github.com/JSONQL-Standard/jsonql-spec)
- 🧪 [Compliance Tests](https://github.com/JSONQL-Standard/jsonql-tests)
- 🐛 [Issues](https://github.com/JSONQL-Standard/jsonql-py/issues)

## License

MIT
