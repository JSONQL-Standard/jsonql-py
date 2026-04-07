# jsonql-py

**Python SDK** for [JSONQL](https://github.com/jsonql-standard/jsonql-spec) — a JSON-based query language for SQL databases.

## Installation

```bash
pip install jsonql-py
```

With framework extras:

```bash
pip install jsonql-py[flask]      # Flask adapter
pip install jsonql-py[fastapi]    # FastAPI adapter
pip install jsonql-py[django]     # Django REST adapter
pip install jsonql-py[postgres]   # PostgreSQL driver support
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
print(result.sql)   # SELECT "users"."id", "users"."name" FROM "users" WHERE "users"."status" = $1 ORDER BY "users"."name" DESC LIMIT 10
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

# Returns ValidationResult
result = validator.validate(JsonQLQuery(fields=["id", "name"]))
assert result.valid

# Raises JsonQLValidationError
validator.validate_or_raise(JsonQLQuery(fields=["secret"]))
```

### Engine (Full Pipeline)

```python
import asyncio
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
    .debug()
    .build()
)

result = asyncio.run(engine.execute({"fields": ["id", "name"]}, "users"))
print(result["data"])
```

### Flask Adapter

```python
from flask import Flask
from jsonql.adapters import create_flask_blueprint, AdapterOptions

app = Flask(__name__)

bp = create_flask_blueprint(AdapterOptions(
    dialect="sqlite",
    execute=run_sql,
    schema=my_schema,
))
app.register_blueprint(bp, url_prefix="/jsonql")
```

### FastAPI Adapter

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

### Django Adapter

```python
# urls.py
from django.urls import path
from jsonql.adapters import JsonQLDjangoView, AdapterOptions

options = AdapterOptions(dialect="postgres", execute=run_sql, schema=my_schema)

urlpatterns = [
    path("jsonql/", JsonQLDjangoView.as_view(options=options)),
    path("jsonql/<path:path>/", JsonQLDjangoView.as_view(options=options)),
]
```

## Supported Dialects

| Dialect    | Placeholder | Quoting    | RETURNING |
|------------|-------------|------------|-----------|
| `postgres` | `$1, $2`    | `"col"`    | ✅        |
| `mysql`    | `?, ?`      | `` `col` ``| ❌        |
| `sqlite`   | `?, ?`      | `"col"`    | ❌        |

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
└── JsonQLExecutionError    (code: EXECUTION_ERROR)
```

## Development

```bash
pip install -e ".[dev]"  # import name is still 'jsonql'
pytest
ruff check src/ tests/
mypy src/
```

## License

MIT
