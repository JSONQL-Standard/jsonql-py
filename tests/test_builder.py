"""Tests for the JSONQL query and mutation builders."""

from jsonql import JsonQLMutation, JsonQLQuery, MutationBuilder, QueryBuilder
from jsonql.conditions import and_, contains, eq, field, gt, is_in, or_


class TestQueryBuilder:
    def test_basic_build(self) -> None:
        q = QueryBuilder().from_table("users").select("id", "name").build()
        assert isinstance(q, JsonQLQuery)
        assert q.from_table == "users"
        assert q.fields == ["id", "name"]

    def test_where(self) -> None:
        q = QueryBuilder().from_table("users").where(field("status", eq("active"))).build()
        assert q.where == {"status": {"eq": "active"}}

    def test_and_where(self) -> None:
        q = (
            QueryBuilder()
            .from_table("users")
            .where(field("status", eq("active")))
            .and_where(field("age", gt(18)))
            .build()
        )
        assert "and" in q.where

    def test_or_where(self) -> None:
        q = (
            QueryBuilder()
            .from_table("users")
            .where(field("status", eq("active")))
            .or_where(field("status", eq("pending")))
            .build()
        )
        assert "or" in q.where

    def test_order_limit_offset(self) -> None:
        q = QueryBuilder().from_table("users").order_by("name", "-age").limit(10).offset(20).build()
        assert q.sort == ["name", "-age"]
        assert q.limit == 10
        assert q.offset == 20

    def test_group_by_aggregate(self) -> None:
        q = (
            QueryBuilder()
            .from_table("orders")
            .group_by("status")
            .aggregate({"total": {"sum": "amount"}})
            .build()
        )
        assert q.group_by == ["status"]
        assert q.aggregate == {"total": {"sum": "amount"}}

    def test_include(self) -> None:
        q = (
            QueryBuilder()
            .from_table("users")
            .include({"orders": {"fields": ["id", "total"]}})
            .build()
        )
        assert "orders" in q.include

    def test_reset(self) -> None:
        b = QueryBuilder().from_table("users").select("id")
        q1 = b.build()
        b.reset()
        q2 = b.build()
        assert q1.from_table == "users"
        assert q2.from_table == ""
        assert q2.fields == []


class TestMutationBuilder:
    def test_create(self) -> None:
        m = MutationBuilder().create({"name": "Alice", "age": 30}).build()
        assert isinstance(m, JsonQLMutation)
        assert m.op == "create"
        assert m.data == {"name": "Alice", "age": 30}

    def test_update(self) -> None:
        m = MutationBuilder().update({"name": "Bob"}).where({"id": {"eq": 1}}).build()
        assert m.op == "update"
        assert m.patch == {"name": "Bob"}
        assert m.where is not None

    def test_delete(self) -> None:
        m = MutationBuilder().delete().where({"id": {"eq": 1}}).build()
        assert m.op == "delete"

    def test_reset(self) -> None:
        b = MutationBuilder().create({"name": "Alice"})
        b.build()  # consume the mutation
        b.reset()
        import pytest

        with pytest.raises(ValueError, match="not initialised"):
            b.build()


class TestConditions:
    def test_eq(self) -> None:
        assert eq(42) == {"eq": 42}

    def test_gt(self) -> None:
        assert gt(10) == {"gt": 10}

    def test_contains(self) -> None:
        assert contains("alice") == {"like": "%alice%"}

    def test_is_in(self) -> None:
        assert is_in(1, 2, 3) == {"in": [1, 2, 3]}

    def test_field(self) -> None:
        assert field("name", eq("Alice")) == {"name": {"eq": "Alice"}}

    def test_and(self) -> None:
        result = and_(
            field("a", eq(1)),
            field("b", eq(2)),
        )
        assert "and" in result
        assert len(result["and"]) == 2

    def test_or(self) -> None:
        result = or_(
            field("a", eq(1)),
            field("b", eq(2)),
        )
        assert "or" in result
