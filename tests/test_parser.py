"""Tests for the JSONQL parser."""

import pytest

from jsonql import JsonQLMutation, JsonQLQuery, Parser, ParserOptions


class TestParser:
    def test_parse_basic_query(self) -> None:
        parser = Parser()
        q = parser.parse({"fields": ["id", "name"]})
        assert isinstance(q, JsonQLQuery)
        assert q.fields == ["id", "name"]

    def test_parse_json_string(self) -> None:
        parser = Parser()
        q = parser.parse_json('{"fields": ["id"], "limit": 5}')
        assert isinstance(q, JsonQLQuery)
        assert q.fields == ["id"]
        assert q.limit == 5

    def test_parse_with_table(self) -> None:
        parser = Parser()
        q = parser.parse({"from": "users", "fields": ["id"]})
        assert isinstance(q, JsonQLQuery)
        assert q.from_table == "users"

    def test_parse_sort_string(self) -> None:
        parser = Parser()
        q = parser.parse({"sort": "-name"})
        assert isinstance(q, JsonQLQuery)
        assert q.sort == ["-name"]

    def test_parse_sort_array(self) -> None:
        parser = Parser()
        q = parser.parse({"sort": ["name", "-age"]})
        assert isinstance(q, JsonQLQuery)
        assert q.sort == ["name", "-age"]

    def test_parse_distinct_true(self) -> None:
        parser = Parser()
        q = parser.parse({"distinct": True, "fields": ["id"]})
        assert isinstance(q, JsonQLQuery)
        assert q.distinct is not None
        assert q.distinct.all is True

    def test_parse_distinct_fields(self) -> None:
        parser = Parser()
        q = parser.parse({"distinct": ["name", "email"]})
        assert isinstance(q, JsonQLQuery)
        assert q.distinct is not None
        assert q.distinct.fields == ["name", "email"]

    def test_parse_mutation(self) -> None:
        parser = Parser()
        m = parser.parse({"op": "create", "data": {"name": "Alice"}})
        assert isinstance(m, JsonQLMutation)
        assert m.op == "create"
        assert m.data == {"name": "Alice"}

    def test_parse_update_mutation(self) -> None:
        parser = Parser()
        m = parser.parse({
            "op": "update",
            "patch": {"name": "Bob"},
            "where": {"id": {"eq": 1}},
        })
        assert isinstance(m, JsonQLMutation)
        assert m.op == "update"
        assert m.patch == {"name": "Bob"}
        assert m.where is not None

    def test_parse_delete_mutation(self) -> None:
        parser = Parser()
        m = parser.parse({"op": "delete", "where": {"id": {"eq": 1}}})
        assert isinstance(m, JsonQLMutation)
        assert m.op == "delete"

    def test_max_limit_enforced(self) -> None:
        parser = Parser(ParserOptions(max_limit=10))
        with pytest.raises(ValueError, match="exceeds maximum"):
            parser.parse({"limit": 100})

    def test_max_nesting_depth_enforced(self) -> None:
        parser = Parser(ParserOptions(max_nesting_depth=1))
        with pytest.raises(ValueError, match="Nesting depth"):
            parser.parse({
                "include": {
                    "items": {
                        "fields": ["id"],
                        "include": {
                            "product": {"fields": ["name"]},
                        },
                    }
                }
            })

    def test_allowed_fields_enforced(self) -> None:
        parser = Parser(ParserOptions(allowed_fields=["id", "name"]))
        with pytest.raises(ValueError, match="not allowed"):
            parser.parse({"fields": ["id", "secret"]})

    def test_allowed_includes_enforced(self) -> None:
        parser = Parser(ParserOptions(allowed_includes=["items"]))
        with pytest.raises(ValueError, match="not allowed"):
            parser.parse({"include": {"forbidden_rel": {"fields": ["id"]}}})

    def test_parse_offset_alias_skip(self) -> None:
        parser = Parser()
        q = parser.parse({"skip": 5})
        assert isinstance(q, JsonQLQuery)
        assert q.offset == 5

    def test_parse_full_query(self) -> None:
        parser = Parser()
        q = parser.parse({
            "version": "1.0",
            "from": "orders",
            "fields": ["id", "total"],
            "where": {"status": {"eq": "active"}},
            "sort": ["-total"],
            "limit": 10,
            "offset": 5,
            "groupBy": ["status"],
            "aggregate": {"totalSum": {"sum": "total"}},
            "include": {"items": {"fields": ["id", "quantity"]}},
        })
        assert isinstance(q, JsonQLQuery)
        assert q.from_table == "orders"
        assert q.fields == ["id", "total"]
        assert q.limit == 10
        assert q.offset == 5
        assert q.sort == ["-total"]
        assert q.group_by == ["status"]
        assert q.aggregate == {"totalSum": {"sum": "total"}}
