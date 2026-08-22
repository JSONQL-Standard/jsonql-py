"""Tests for the core JSONQL type definitions."""

import pytest
from jsonql.types import (
    DistinctOption,
    JsonQLQuery,
    JsonQLMutation,
    is_mutation,
    JsonQLField,
    JsonQLRelation,
    JsonQLTable,
    JsonQLSettings,
    JsonQLSchema,
    TranspileResult,
    ValidationError,
    ValidationResult,
    parse_schema,
)


class TestDistinctOption:
    """Tests for DistinctOption."""

    def test_from_raw_bool_true(self):
        d = DistinctOption.from_raw(True)
        assert d.all is True
        assert d.fields is None

    def test_from_raw_bool_false(self):
        d = DistinctOption.from_raw(False)
        assert d.all is False
        assert d.fields is None

    def test_from_raw_field_list(self):
        d = DistinctOption.from_raw(["name", "age"])
        assert d.all is False
        assert d.fields == ["name", "age"]

    def test_from_raw_invalid(self):
        with pytest.raises(ValueError, match="distinct must be a boolean or array"):
            DistinctOption.from_raw(42)


class TestJsonQLQuery:
    """Tests for the query type."""

    def test_default_values(self):
        q = JsonQLQuery()
        assert q.version == "1.0"
        assert q.from_table == ""
        assert q.fields == []
        assert q.where is None
        assert q.sort == []
        assert q.limit is None
        assert q.offset is None

    def test_with_fields(self):
        q = JsonQLQuery(from_table="users", fields=["id", "name"], limit=10)
        assert q.from_table == "users"
        assert q.fields == ["id", "name"]
        assert q.limit == 10

    def test_with_where(self):
        q = JsonQLQuery(from_table="users", where={"age": {"gt": 18}})
        assert q.where == {"age": {"gt": 18}}


class TestJsonQLMutation:
    """Tests for the mutation type."""

    def test_create_mutation(self):
        m = JsonQLMutation(op="create", data={"name": "Alice", "age": 30})
        assert m.op == "create"
        assert m.data == {"name": "Alice", "age": 30}

    def test_update_mutation(self):
        m = JsonQLMutation(op="update", patch={"age": 31}, where={"id": {"eq": 1}})
        assert m.op == "update"
        assert m.patch == {"age": 31}
        assert m.where == {"id": {"eq": 1}}

    def test_delete_mutation(self):
        m = JsonQLMutation(op="delete", where={"id": {"eq": 1}})
        assert m.op == "delete"


class TestIsMutation:
    """Tests for the is_mutation helper."""

    def test_mutation_is_mutation(self):
        assert is_mutation(JsonQLMutation(op="create")) is True

    def test_query_is_not_mutation(self):
        assert is_mutation(JsonQLQuery()) is False


class TestSchemaTypes:
    """Tests for table/field/relation/schema types."""

    def test_jsonql_field_defaults(self):
        f = JsonQLField()
        assert f.type == "string"

    def test_jsonql_field_with_args(self):
        f = JsonQLField(type="integer", allow_select=True, allow_filter=True)
        assert f.type == "integer"
        assert f.allow_select is True

    def test_jsonql_relation_defaults(self):
        r = JsonQLRelation()
        assert r.type == "hasMany"

    def test_jsonql_table_defaults(self):
        t = JsonQLTable()
        assert t.fields == {}
        assert t.primary_key == "id"

    def test_jsonql_table_with_fields(self):
        t = JsonQLTable(
            fields={"name": JsonQLField(type="string")},
            primary_key="uuid",
        )
        assert "name" in t.fields
        assert t.fields["name"].type == "string"
        assert t.primary_key == "uuid"

    def test_jsonql_schema_defaults(self):
        s = JsonQLSchema()
        assert s.tables == {}
        assert s.settings is None

    def test_jsonql_schema_with_data(self):
        settings = JsonQLSettings(allow_aggregate=False, max_depth=3)
        table = JsonQLTable(fields={"id": JsonQLField(type="integer")})
        s = JsonQLSchema(tables={"users": table}, settings=settings)
        assert "users" in s.tables
        assert s.settings is not None
        assert s.settings.allow_aggregate is False


class TestResultTypes:
    """Tests for TranspileResult and ValidationValue types."""

    def test_transpile_result_defaults(self):
        r = TranspileResult()
        assert r.sql == ""
        assert r.args == []

    def test_transpile_result_with_data(self):
        r = TranspileResult(sql="SELECT * FROM users", args=[1, 2])
        assert r.sql == "SELECT * FROM users"
        assert r.args == [1, 2]

    def test_validation_error_dataclass(self):
        e = ValidationError(code="MISSING", message="Field required", path="where.id")
        assert e.code == "MISSING"
        assert e.message == "Field required"
        assert e.path == "where.id"

    def test_validation_result_valid(self):
        r = ValidationResult(valid=True)
        assert r.valid is True
        assert r.errors == []

    def test_validation_result_invalid(self):
        errors = [ValidationError(code="MISSING", message="id required", path="where.id")]
        r = ValidationResult(valid=False, errors=errors)
        assert r.valid is False
        assert len(r.errors) == 1


class TestParseSchema:
    """Tests for parse_schema — raw dict → typed schema conversion."""

    def test_empty_schema(self):
        s = parse_schema({})
        assert s.tables == {}
        assert s.settings is None

    def test_schema_with_settings(self):
        raw = {"settings": {"allowAggregate": False, "maxDepth": 5}}
        s = parse_schema(raw)
        assert s.settings is not None
        assert s.settings.allow_aggregate is False
        assert s.settings.max_depth == 5

    def test_schema_with_table(self):
        raw = {
            "tables": {
                "users": {
                    "primaryKey": "user_id",
                    "fields": {
                        "name": {"type": "string", "allowFilter": True},
                        "age": {"type": "integer", "allowFilter": True, "allowSort": True},
                    },
                    "relations": {
                        "posts": {"type": "hasMany", "foreignKey": "user_id", "target": "posts"},
                    },
                },
            },
        }
        s = parse_schema(raw)
        assert "users" in s.tables
        table = s.tables["users"]
        assert table.primary_key == "user_id"
        assert "name" in table.fields
        assert table.fields["name"].type == "string"
        assert table.fields["name"].allow_filter is True
        assert "posts" in table.relations
        assert table.relations["posts"].type == "hasMany"
        assert table.relations["posts"].foreign_key == "user_id"

    def test_multiple_tables(self):
        raw = {
            "tables": {
                "users": {
                    "fields": {"id": {"type": "integer"}},
                },
                "posts": {
                    "fields": {"title": {"type": "string"}},
                },
            },
        }
        s = parse_schema(raw)
        assert len(s.tables) == 2
        assert "users" in s.tables
        assert "posts" in s.tables