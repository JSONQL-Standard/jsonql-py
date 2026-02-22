"""Tests for the JSONQL validator."""

import pytest

from jsonql import JsonQLQuery, Validator
from jsonql.errors import JsonQLValidationError
from jsonql.types import (
    JsonQLField,
    JsonQLRelation,
    JsonQLSchema,
    JsonQLSettings,
    JsonQLTable,
)


def _schema() -> JsonQLSchema:
    return JsonQLSchema(
        tables={
            "users": JsonQLTable(
                fields={
                    "id": JsonQLField(type="integer"),
                    "name": JsonQLField(type="string"),
                    "email": JsonQLField(type="string", allow_select=False),
                    "secret": JsonQLField(type="string", allow_filter=False),
                    "age": JsonQLField(
                        type="integer", allow_sort=True, allow_aggregate=True
                    ),
                    "status": JsonQLField(type="string", allow_group=True),
                },
                relations={
                    "orders": JsonQLRelation(type="hasMany", foreign_key="user_id"),
                    "hidden": JsonQLRelation(
                        type="hasMany",
                        foreign_key="user_id",
                        allow_include=False,
                    ),
                },
            ),
        },
        settings=JsonQLSettings(allow_aggregate=True, max_depth=2),
    )


class TestValidator:
    def test_valid_query(self) -> None:
        v = Validator(_schema(), "users")
        result = v.validate(
            JsonQLQuery(fields=["id", "name"], sort=["age"])
        )
        assert result.valid is True
        assert result.errors == []

    def test_field_not_allowed(self) -> None:
        v = Validator(_schema(), "users")
        result = v.validate(JsonQLQuery(fields=["id", "email"]))
        assert result.valid is False
        assert any(e.code == "FIELD_NOT_ALLOWED" for e in result.errors)

    def test_field_not_filterable(self) -> None:
        v = Validator(_schema(), "users")
        result = v.validate(
            JsonQLQuery(where={"secret": {"eq": "foo"}})
        )
        assert result.valid is False
        assert any(e.code == "FIELD_NOT_FILTERABLE" for e in result.errors)

    def test_relation_not_found(self) -> None:
        v = Validator(_schema(), "users")
        result = v.validate(
            JsonQLQuery(include={"nonexistent": {"fields": ["id"]}})
        )
        assert result.valid is False
        assert any(e.code == "RELATION_NOT_FOUND" for e in result.errors)

    def test_relation_not_allowed(self) -> None:
        v = Validator(_schema(), "users")
        result = v.validate(
            JsonQLQuery(include={"hidden": {"fields": ["id"]}})
        )
        assert result.valid is False
        assert any(e.code == "RELATION_NOT_ALLOWED" for e in result.errors)

    def test_table_not_found(self) -> None:
        v = Validator(_schema(), "nonexistent")
        result = v.validate(JsonQLQuery())
        assert result.valid is False
        assert any(e.code == "TABLE_NOT_FOUND" for e in result.errors)

    def test_validate_first(self) -> None:
        v = Validator(_schema(), "users")
        err = v.validate_first(JsonQLQuery(fields=["email"]))
        assert err is not None
        assert err.code == "FIELD_NOT_ALLOWED"

    def test_validate_first_valid(self) -> None:
        v = Validator(_schema(), "users")
        err = v.validate_first(JsonQLQuery(fields=["id"]))
        assert err is None

    def test_validate_or_raise(self) -> None:
        v = Validator(_schema(), "users")
        with pytest.raises(JsonQLValidationError) as exc_info:
            v.validate_or_raise(JsonQLQuery(fields=["email"]))
        assert exc_info.value.errors[0].code == "FIELD_NOT_ALLOWED"

    def test_validate_or_raise_valid(self) -> None:
        v = Validator(_schema(), "users")
        # Should not raise
        v.validate_or_raise(JsonQLQuery(fields=["id", "name"]))

    def test_aggregation_disabled(self) -> None:
        schema = JsonQLSchema(
            tables={
                "users": JsonQLTable(
                    fields={"id": JsonQLField(type="integer")},
                ),
            },
            settings=JsonQLSettings(allow_aggregate=False),
        )
        v = Validator(schema, "users")
        result = v.validate(
            JsonQLQuery(aggregate={"total": {"count": "*"}})
        )
        assert result.valid is False
        assert any(e.code == "AGGREGATION_DISABLED" for e in result.errors)

    def test_max_depth_exceeded(self) -> None:
        schema = JsonQLSchema(
            tables={
                "a": JsonQLTable(
                    fields={"id": JsonQLField()},
                    relations={"b": JsonQLRelation(type="hasMany", foreign_key="a_id")},
                ),
                "b": JsonQLTable(
                    fields={"id": JsonQLField()},
                    relations={"c": JsonQLRelation(type="hasMany", foreign_key="b_id")},
                ),
                "c": JsonQLTable(fields={"id": JsonQLField()}),
            },
            settings=JsonQLSettings(max_depth=1),
        )
        v = Validator(schema, "a")
        result = v.validate(
            JsonQLQuery(
                include={
                    "b": {
                        "fields": ["id"],
                        "include": {"c": {"fields": ["id"]}},
                    }
                }
            )
        )
        assert result.valid is False
        assert any(e.code == "MAX_DEPTH_EXCEEDED" for e in result.errors)
