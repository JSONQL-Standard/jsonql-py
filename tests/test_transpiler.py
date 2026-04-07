"""Tests for the JSONQL SQL transpiler."""

from jsonql import DistinctOption, JsonQLQuery, SQLTranspiler
from jsonql.types import (
    JsonQLField,
    JsonQLRelation,
    JsonQLSchema,
    JsonQLTable,
)


def _schema() -> JsonQLSchema:
    """Fixture schema for tests."""
    return JsonQLSchema(
        tables={
            "users": JsonQLTable(
                fields={
                    "id": JsonQLField(type="integer"),
                    "name": JsonQLField(type="string"),
                    "email": JsonQLField(type="string"),
                    "age": JsonQLField(type="integer"),
                    "status": JsonQLField(type="string"),
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
                    "user_id": JsonQLField(type="integer"),
                    "status": JsonQLField(type="string"),
                },
                relations={
                    "items": JsonQLRelation(
                        type="hasMany", foreign_key="order_id", target="order_items"
                    ),
                },
            ),
            "profiles": JsonQLTable(
                fields={
                    "id": JsonQLField(type="integer"),
                    "bio": JsonQLField(type="string"),
                },
            ),
            "order_items": JsonQLTable(
                fields={
                    "id": JsonQLField(type="integer"),
                    "quantity": JsonQLField(type="integer"),
                    "order_id": JsonQLField(type="integer"),
                },
            ),
        },
    )


class TestSQLiteTranspiler:
    def setup_method(self) -> None:
        self.t = SQLTranspiler("sqlite")

    def test_select_all(self) -> None:
        q = JsonQLQuery()
        r = self.t.transpile(q, "users")
        assert r.sql == 'SELECT "users".* FROM "users"'
        assert r.args == []

    def test_select_fields(self) -> None:
        q = JsonQLQuery(fields=["id", "name"])
        r = self.t.transpile(q, "users")
        assert r.sql == 'SELECT "users"."id", "users"."name" FROM "users"'

    def test_where_eq(self) -> None:
        q = JsonQLQuery(where={"name": {"eq": "Alice"}})
        r = self.t.transpile(q, "users")
        assert "WHERE" in r.sql
        assert '"users"."name" = ?' in r.sql
        assert r.args == ["Alice"]

    def test_where_null(self) -> None:
        q = JsonQLQuery(where={"email": {"eq": None}})
        r = self.t.transpile(q, "users")
        assert '"users"."email" IS NULL' in r.sql
        assert r.args == []

    def test_where_neq_null(self) -> None:
        q = JsonQLQuery(where={"email": {"neq": None}})
        r = self.t.transpile(q, "users")
        assert '"users"."email" IS NOT NULL' in r.sql

    def test_where_comparison(self) -> None:
        q = JsonQLQuery(where={"age": {"gt": 18, "lte": 65}})
        r = self.t.transpile(q, "users")
        assert '"users"."age" > ?' in r.sql
        assert '"users"."age" <= ?' in r.sql
        assert 18 in r.args
        assert 65 in r.args

    def test_where_like(self) -> None:
        q = JsonQLQuery(where={"name": {"like": "%alice%"}})
        r = self.t.transpile(q, "users")
        assert '"users"."name" LIKE ?' in r.sql
        assert r.args == ["%alice%"]

    def test_where_in(self) -> None:
        q = JsonQLQuery(where={"status": {"in": ["active", "pending"]}})
        r = self.t.transpile(q, "users")
        assert '"users"."status" IN (?, ?)' in r.sql
        assert r.args == ["active", "pending"]

    def test_sort_asc(self) -> None:
        q = JsonQLQuery(sort=["name"])
        r = self.t.transpile(q, "users")
        assert 'ORDER BY "users"."name" ASC' in r.sql

    def test_sort_desc(self) -> None:
        q = JsonQLQuery(sort=["-name"])
        r = self.t.transpile(q, "users")
        assert 'ORDER BY "users"."name" DESC' in r.sql

    def test_multi_sort(self) -> None:
        q = JsonQLQuery(sort=["name", "-age"])
        r = self.t.transpile(q, "users")
        assert '"users"."name" ASC' in r.sql
        assert '"users"."age" DESC' in r.sql

    def test_limit_offset(self) -> None:
        q = JsonQLQuery(limit=10, offset=20)
        r = self.t.transpile(q, "users")
        assert "LIMIT 10" in r.sql
        assert "OFFSET 20" in r.sql

    def test_group_by(self) -> None:
        q = JsonQLQuery(group_by=["status"])
        r = self.t.transpile(q, "users")
        assert 'GROUP BY "users"."status"' in r.sql

    def test_aggregate_count(self) -> None:
        q = JsonQLQuery(aggregate={"total": {"count": "*"}})
        r = self.t.transpile(q, "users")
        assert 'COUNT(*) AS "total"' in r.sql

    def test_aggregate_sum(self) -> None:
        q = JsonQLQuery(
            aggregate={"totalAge": {"sum": "age"}},
            fields=[],
        )
        r = self.t.transpile(q, "users")
        assert 'SUM("users"."age") AS "totalAge"' in r.sql

    def test_distinct_all(self) -> None:
        q = JsonQLQuery(distinct=DistinctOption(all=True))
        r = self.t.transpile(q, "users")
        assert r.sql.startswith('SELECT DISTINCT "users"')

    def test_include_has_many(self) -> None:
        q = JsonQLQuery(
            fields=["id", "name"],
            include={"orders": {"fields": ["id", "total"]}},
        )
        schema = _schema()
        r = self.t.transpile(q, "users", schema)
        assert "LEFT JOIN" in r.sql
        assert '"orders"."id" AS "orders__id"' in r.sql
        assert '"orders"."total" AS "orders__total"' in r.sql

    def test_include_has_one(self) -> None:
        q = JsonQLQuery(
            fields=["id", "name"],
            include={"profile": {"fields": ["id", "bio"]}},
        )
        schema = _schema()
        r = self.t.transpile(q, "users", schema)
        assert "LEFT JOIN" in r.sql
        assert '"profile"."bio" AS "profile__bio"' in r.sql


class TestPostgresTranspiler:
    def setup_method(self) -> None:
        self.t = SQLTranspiler("postgres")

    def test_placeholder_style(self) -> None:
        q = JsonQLQuery(where={"name": {"eq": "Alice"}})
        r = self.t.transpile(q, "users")
        assert "$1" in r.sql
        assert "?" not in r.sql

    def test_distinct_on(self) -> None:
        q = JsonQLQuery(
            distinct=DistinctOption(fields=["name"]),
            fields=["id", "name"],
        )
        r = self.t.transpile(q, "users")
        assert 'DISTINCT ON ("users"."name")' in r.sql


class TestMySQLTranspiler:
    def setup_method(self) -> None:
        self.t = SQLTranspiler("mysql")

    def test_backtick_quoting(self) -> None:
        q = JsonQLQuery(fields=["id", "name"])
        r = self.t.transpile(q, "users")
        assert "`users`.`id`" in r.sql
        assert "`users`.`name`" in r.sql

    def test_placeholder_style(self) -> None:
        q = JsonQLQuery(where={"id": {"eq": 1}})
        r = self.t.transpile(q, "users")
        assert "?" in r.sql


class TestInsertTranspiler:
    def setup_method(self) -> None:
        self.t = SQLTranspiler("sqlite")

    def test_insert(self) -> None:
        r = self.t.transpile_insert("users", {"name": "Alice", "age": 30})
        assert 'INSERT INTO "users"' in r.sql
        assert '"age"' in r.sql
        assert '"name"' in r.sql
        assert r.args == [30, "Alice"]  # sorted keys

    def test_insert_postgres_returning(self) -> None:
        t = SQLTranspiler("postgres")
        r = t.transpile_insert("users", {"name": "Alice"})
        assert "RETURNING *" in r.sql


class TestUpdateTranspiler:
    def setup_method(self) -> None:
        self.t = SQLTranspiler("sqlite")

    def test_update(self) -> None:
        r = self.t.transpile_update("users", {"name": "Bob"}, {"id": {"eq": 1}})
        assert 'UPDATE "users" SET' in r.sql
        assert '"name" = ?' in r.sql
        assert "WHERE" in r.sql
        assert r.args == ["Bob", 1]


class TestDeleteTranspiler:
    def setup_method(self) -> None:
        self.t = SQLTranspiler("sqlite")

    def test_delete(self) -> None:
        r = self.t.transpile_delete("users", {"id": {"eq": 1}})
        assert 'DELETE FROM "users"' in r.sql
        assert "WHERE" in r.sql
        assert r.args == [1]

    def test_delete_all(self) -> None:
        r = self.t.transpile_delete("users")
        assert 'DELETE FROM "users"' in r.sql
        assert r.args == []
