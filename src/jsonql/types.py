"""Core type definitions for JSONQL Python SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DistinctOption:
    """Represents a ``distinct`` clause: ``True`` (all fields) or a list of specific fields."""

    all: bool = False
    fields: list[str] | None = None

    @classmethod
    def from_raw(cls, raw: Any) -> DistinctOption:
        """Parse a raw distinct value (bool or list of strings)."""
        if isinstance(raw, bool):
            return cls(all=raw)
        if isinstance(raw, list) and all(isinstance(f, str) for f in raw):
            return cls(fields=raw)
        raise ValueError("distinct must be a boolean or array of strings")


@dataclass
class JsonQLQuery:
    """Represents the structure of a JSONQL query."""

    version: str = "1.0"
    from_table: str = ""
    fields: list[str] = field(default_factory=list)
    where: dict[str, Any] | None = None
    sort: list[str] = field(default_factory=list)
    limit: int | None = None
    offset: int | None = None
    aggregate: dict[str, Any] = field(default_factory=dict)
    group_by: list[str] = field(default_factory=list)
    include: dict[str, Any] = field(default_factory=dict)
    distinct: DistinctOption | None = None


@dataclass
class JsonQLMutation:
    """Represents a mutation operation (create, update, delete)."""

    op: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    patch: dict[str, Any] = field(default_factory=dict)
    where: dict[str, Any] | None = None


def is_mutation(statement: JsonQLQuery | JsonQLMutation) -> bool:
    """Check whether a statement is a mutation."""
    return isinstance(statement, JsonQLMutation)


# ---------- Schema types ----------


@dataclass
class JsonQLField:
    """Defines a single field in a table schema."""

    type: str = "string"
    allow_select: bool | None = None
    allow_filter: bool | None = None
    allow_sort: bool | None = None
    allow_group: bool | None = None
    allow_aggregate: bool | None = None
    allow_sum: bool | None = None
    allow_avg: bool | None = None
    allow_min: bool | None = None
    allow_max: bool | None = None
    allow_count: bool | None = None


@dataclass
class JsonQLRelation:
    """Defines a relation between tables."""

    type: str = "hasMany"  # hasOne | hasMany | belongsTo
    foreign_key: str = ""
    target: str = ""
    allow_include: bool | None = None


@dataclass
class JsonQLTable:
    """A table definition containing fields and relations."""

    fields: dict[str, JsonQLField] = field(default_factory=dict)
    relations: dict[str, JsonQLRelation] = field(default_factory=dict)


@dataclass
class JsonQLSettings:
    """Global schema settings."""

    allow_aggregate: bool = True
    max_depth: int = 0


@dataclass
class JsonQLSchema:
    """Root schema object containing tables and optional settings."""

    tables: dict[str, JsonQLTable] = field(default_factory=dict)
    settings: JsonQLSettings | None = None


# ---------- Result types ----------


@dataclass
class TranspileResult:
    """The output of a transpilation: SQL text and bound arguments."""

    sql: str = ""
    args: list[Any] = field(default_factory=list)


@dataclass
class ValidationError:
    """A single validation error."""

    code: str = ""
    message: str = ""
    path: str = ""


@dataclass
class ValidationResult:
    """Aggregate validation outcome."""

    valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)


# ---------- Schema parsing helpers ----------


def parse_schema(raw: dict[str, Any]) -> JsonQLSchema:
    """Parse a raw dict (from JSON) into a typed ``JsonQLSchema``."""
    settings = None
    if "settings" in raw:
        s = raw["settings"]
        settings = JsonQLSettings(
            allow_aggregate=s.get("allowAggregate", True),
            max_depth=s.get("maxDepth", 0),
        )

    tables: dict[str, JsonQLTable] = {}
    for table_name, table_raw in raw.get("tables", {}).items():
        fields: dict[str, JsonQLField] = {}
        for fname, fraw in table_raw.get("fields", {}).items():
            fields[fname] = JsonQLField(
                type=fraw.get("type", "string"),
                allow_select=fraw.get("allowSelect"),
                allow_filter=fraw.get("allowFilter"),
                allow_sort=fraw.get("allowSort"),
                allow_group=fraw.get("allowGroup"),
                allow_aggregate=fraw.get("allowAggregate"),
                allow_sum=fraw.get("allowSum"),
                allow_avg=fraw.get("allowAvg"),
                allow_min=fraw.get("allowMin"),
                allow_max=fraw.get("allowMax"),
                allow_count=fraw.get("allowCount"),
            )
        relations: dict[str, JsonQLRelation] = {}
        for rname, rraw in table_raw.get("relations", {}).items():
            relations[rname] = JsonQLRelation(
                type=rraw.get("type", "hasMany"),
                foreign_key=rraw.get("foreignKey", ""),
                target=rraw.get("target", ""),
                allow_include=rraw.get("allowInclude"),
            )
        tables[table_name] = JsonQLTable(fields=fields, relations=relations)

    return JsonQLSchema(tables=tables, settings=settings)
