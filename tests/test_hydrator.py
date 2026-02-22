"""Tests for the JSONQL hydrator."""

from jsonql import ResultHydrator
from jsonql.types import (
    JsonQLField,
    JsonQLRelation,
    JsonQLSchema,
    JsonQLTable,
)


def _schema() -> JsonQLSchema:
    return JsonQLSchema(
        tables={
            "users": JsonQLTable(
                fields={
                    "id": JsonQLField(type="integer"),
                    "name": JsonQLField(type="string"),
                },
                relations={
                    "orders": JsonQLRelation(
                        type="hasMany", foreign_key="user_id", target="orders"
                    ),
                    "profile": JsonQLRelation(
                        type="hasOne", foreign_key="profile_id", target="profiles"
                    ),
                },
            ),
            "orders": JsonQLTable(
                fields={
                    "id": JsonQLField(type="integer"),
                    "total": JsonQLField(type="number"),
                },
            ),
            "profiles": JsonQLTable(
                fields={
                    "id": JsonQLField(type="integer"),
                    "bio": JsonQLField(type="string"),
                },
            ),
        },
    )


class TestHydrator:
    def test_simple_rows(self) -> None:
        h = ResultHydrator()
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        result = h.hydrate(rows)
        assert len(result) == 2
        assert result[0]["name"] == "Alice"

    def test_expand_double_underscore(self) -> None:
        h = ResultHydrator()
        rows = [
            {"id": 1, "name": "Alice", "orders__id": 10, "orders__total": 99.5},
        ]
        result = h.hydrate(rows)
        assert result[0]["orders"]["id"] == 10
        assert result[0]["orders"]["total"] == 99.5

    def test_merge_has_many(self) -> None:
        h = ResultHydrator()
        schema = _schema()
        rows = [
            {"id": 1, "name": "Alice", "orders__id": 10, "orders__total": 50},
            {"id": 1, "name": "Alice", "orders__id": 11, "orders__total": 75},
        ]
        expanded = [h._expand_row(r) for r in rows]
        result = h._merge_rows(expanded, schema, "users")
        assert len(result) == 1
        assert result[0]["name"] == "Alice"
        assert len(result[0]["orders"]) == 2
        assert result[0]["orders"][0]["id"] == 10
        assert result[0]["orders"][1]["id"] == 11

    def test_merge_has_one(self) -> None:
        h = ResultHydrator()
        schema = _schema()
        rows = [
            {"id": 1, "name": "Alice", "profile__id": 100, "profile__bio": "Hello"},
        ]
        expanded = [h._expand_row(r) for r in rows]
        result = h._merge_rows(expanded, schema, "users")
        assert len(result) == 1
        assert result[0]["profile"]["id"] == 100
        assert result[0]["profile"]["bio"] == "Hello"

    def test_merge_null_relation(self) -> None:
        h = ResultHydrator()
        schema = _schema()
        rows = [
            {"id": 1, "name": "Alice", "profile__id": None, "profile__bio": None},
        ]
        expanded = [h._expand_row(r) for r in rows]
        result = h._merge_rows(expanded, schema, "users")
        assert result[0]["profile"] is None

    def test_empty_rows(self) -> None:
        h = ResultHydrator()
        result = h.hydrate([], _schema(), "users")
        assert result == []

    def test_full_hydrate_pipeline(self) -> None:
        h = ResultHydrator()
        schema = _schema()
        rows = [
            {"id": 1, "name": "Alice", "orders__id": 10, "orders__total": 50},
            {"id": 1, "name": "Alice", "orders__id": 11, "orders__total": 75},
            {"id": 2, "name": "Bob", "orders__id": 20, "orders__total": 100},
        ]
        result = h.hydrate(rows, schema, "users")
        assert len(result) == 2
        assert len(result[0]["orders"]) == 2
        assert len(result[1]["orders"]) == 1
