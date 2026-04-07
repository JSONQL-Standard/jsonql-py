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

- **JSONQL v1.0 Parser** — parse and validate incoming JSON queries and mutations
- **Query Builder** — Pythonic fluent API with `QueryBuilder`
- **Mutation Builder** — fluent API for create / update / delete with `MutationBuilder`
- **SQL Transpiler** — convert parsed queries → parameterized SQL (PostgreSQL, MySQL, SQLite, MSSQL)
- **MongoDB Transpiler** — convert parsed queries → MongoDB aggregation pipelines
- **MongoDB Driver** — `MongoDBDriver` for direct MongoDB execution
- **Schema Validation** — permission checking and field-level validation
- **Result Hydrator** — flatten SQL JOIN rows into nested JSON trees
- **Driver Factory** — `create_driver()` with auto-config for Postgres, MySQL, SQLite, MSSQL
- **Engine** — full pipeline class combining parser → validator → transpiler → execute → hydrate
- **Condition Helpers** — `eq`, `gt`, `contains`, `and_`, `or_`, `not_`, etc.
- **Flask Adapter** — blueprint with parse-only or full-lifecycle execution
- **FastAPI Adapter** — router with parse-only or full-lifecycle execution
- **Django Adapter** — view with parse-only or full-lifecycle execution
- **MongoDB Adapters** — MongoDB variants for all three frameworks
- **Type Hints** — PEP 561 compatible with full type coverage

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

A working JSONQL API in under 15 lines:

```python
# app.py
from flask import Flask
from jsonql import create_driver, must_load_schema
from jsonql.adapters import create_flask_blueprint, AdapterOptions

app = Flask(__name__)
driver = create_driver("postgres")  # reads DB_DSN from env

bp = create_flask_blueprint(AdapterOptions(
    driver=driver,
    schema=must_load_schema("schema.json"),  # or define inline
))
app.register_blueprint(bp, url_prefix="/api")

if __name__ == "__main__":
    app.run(port=5000)
```

<details>
<summary>schema.json</summary>

```json
{
  "tables": {
    "users": {
      "fields": {
        "id":    { "type": "number" },
        "name":  { "type": "string", "allowFilter": true, "allowSort": true },
        "email": { "type": "string", "allowFilter": true },
        "age":   { "type": "number", "allowFilter": true, "allowSort": true }
      }
    }
  }
}
```
</details>

> **Prefer inline?** Replace `must_load_schema(...)` with `JsonQLSchema(tables={...})` — see [Schema Validation](#schema-validation).

```bash
export DB_DSN="postgresql://user:pass@localhost:5432/mydb"
python app.py
# * Running on http://127.0.0.1:5000
```

```bash
curl -s 'http://localhost:5000/api/users?q={"fields":["id","name"],"where":{"age":{"gt":18}},"sort":{"name":"asc"},"limit":10}'
```

```json
[
  { "id": 1, "name": "Alice" },
  { "id": 2, "name": "Bob" }
]
```

## Builders

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

## Transpilers

### SQL Transpiler

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

### MongoDB Transpiler

```python
from jsonql import MongoTranspiler

transpiler = MongoTranspiler()
result = transpiler.transpile(query, "users")
# {"collection": "users", "operation": "find", "filter": {"status": "active"}, ...}
```

## Schema Validation

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

## Result Hydrator

```python
from jsonql import ResultHydrator

hydrator = ResultHydrator()

# Flatten SQL JOIN rows into nested JSON
rows = [
    {"id": 1, "name": "Alice", "posts__id": 10, "posts__title": "Hello"},
    {"id": 1, "name": "Alice", "posts__id": 11, "posts__title": "World"},
]

result = hydrator.hydrate(rows, schema, "users")
# [{"id": 1, "name": "Alice", "posts": [{"id": 10, "title": "Hello"}, {"id": 11, "title": "World"}]}]
```

## Engine (Full Pipeline)

```python
from jsonql import JsonQLEngine, create_driver
from jsonql.types import parse_schema

schema = parse_schema({...})  # or must_load_schema("schema.json")

driver = create_driver("postgres")  # reads DB_DSN from env

engine = (
    JsonQLEngine.builder()
    .driver(driver)
    .schema(schema)
    .build()
)
```

## Framework Adapters

### Flask

See [Quick Start](#quick-start) for a full Flask example with schema.

### FastAPI

```python
from fastapi import FastAPI
from jsonql import create_driver
from jsonql.adapters import create_fastapi_router, AdapterOptions

app = FastAPI()
driver = create_driver("postgres")

router = create_fastapi_router(AdapterOptions(
    driver=driver,
    schema=my_schema,
))
app.include_router(router, prefix="/jsonql")
```

### Django

```python
# urls.py
from django.urls import path
from jsonql import create_driver
from jsonql.adapters import JsonQLDjangoView, AdapterOptions

driver = create_driver("postgres")
options = AdapterOptions(driver=driver, schema=my_schema)

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
| `create_driver` | Factory for database drivers (Postgres, MySQL, SQLite, MSSQL) |
| `load_schema` | Load schema from a JSON file |
| `must_load_schema` | Load schema or raise on failure |
| `env_or` | Read env var with fallback |
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
