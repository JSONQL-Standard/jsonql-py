"""Tests for jsonql.factory module."""

from __future__ import annotations

import json
import os

import pytest

from jsonql.factory import (
    env_or,
    load_schema,
    must_load_schema,
)

# ---------------------------------------------------------------------------
# env_or
# ---------------------------------------------------------------------------


class TestEnvOr:
    """Tests for env_or()."""

    def test_returns_env_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_JSONQL_VAR", "hello")
        assert env_or("TEST_JSONQL_VAR", "fallback") == "hello"

    def test_returns_fallback_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_JSONQL_VAR_MISSING", raising=False)
        assert env_or("TEST_JSONQL_VAR_MISSING", "default") == "default"

    def test_returns_fallback_when_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_JSONQL_VAR_EMPTY", "")
        assert env_or("TEST_JSONQL_VAR_EMPTY", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# load_schema / must_load_schema
# ---------------------------------------------------------------------------


_SAMPLE_SCHEMA = {
    "tables": {
        "users": {
            "fields": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
            }
        }
    }
}


class TestLoadSchema:
    """Tests for load_schema() and must_load_schema()."""

    def test_load_valid_schema(self, tmp_path: str) -> None:
        path = os.path.join(str(tmp_path), "schema.json")
        with open(path, "w") as fh:
            json.dump(_SAMPLE_SCHEMA, fh)

        schema = load_schema(path)
        assert "users" in schema.tables
        assert "id" in schema.tables["users"].fields

    def test_load_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_schema("/nonexistent/schema.json")

    def test_load_invalid_json(self, tmp_path: str) -> None:
        path = os.path.join(str(tmp_path), "bad.json")
        with open(path, "w") as fh:
            fh.write("not json")

        with pytest.raises(json.JSONDecodeError):
            load_schema(path)

    def test_must_load_schema_success(self, tmp_path: str) -> None:
        path = os.path.join(str(tmp_path), "schema.json")
        with open(path, "w") as fh:
            json.dump(_SAMPLE_SCHEMA, fh)

        schema = must_load_schema(path)
        assert "users" in schema.tables

    def test_must_load_schema_failure(self) -> None:
        with pytest.raises(SystemExit, match="Failed to load schema"):
            must_load_schema("/nonexistent/schema.json")


# ---------------------------------------------------------------------------
# infer_mutation / get_id_from_query / build_rest_mutation
# ---------------------------------------------------------------------------


class TestInferMutation:
    """Tests for the public infer_mutation helper."""

    def test_post_with_data_creates(self) -> None:
        from jsonql.adapters.mongo_base import infer_mutation

        raw = {"data": {"name": "Alice"}}
        result = infer_mutation("POST", raw)
        assert result["op"] == "create"

    def test_post_without_data_is_query(self) -> None:
        from jsonql.adapters.mongo_base import infer_mutation

        raw = {"fields": ["id", "name"]}
        result = infer_mutation("POST", raw)
        assert "op" not in result

    def test_patch_with_patch_updates(self) -> None:
        from jsonql.adapters.mongo_base import infer_mutation

        raw = {"patch": {"name": "Bob"}, "where": {"id": 1}}
        result = infer_mutation("PATCH", raw)
        assert result["op"] == "update"

    def test_delete_with_where_deletes(self) -> None:
        from jsonql.adapters.mongo_base import infer_mutation

        raw = {"where": {"id": 1}}
        result = infer_mutation("DELETE", raw)
        assert result["op"] == "delete"

    def test_explicit_op_preserved(self) -> None:
        from jsonql.adapters.mongo_base import infer_mutation

        raw = {"op": "create", "data": {"x": 1}}
        result = infer_mutation("DELETE", raw)
        assert result["op"] == "create"


class TestGetIdFromQuery:
    """Tests for get_id_from_query()."""

    def test_numeric_id(self) -> None:
        from jsonql.adapters.mongo_base import get_id_from_query

        assert get_id_from_query({"id": "42"}) == 42

    def test_string_id(self) -> None:
        from jsonql.adapters.mongo_base import get_id_from_query

        assert get_id_from_query({"id": "abc"}) == "abc"

    def test_missing_id(self) -> None:
        from jsonql.adapters.mongo_base import get_id_from_query

        assert get_id_from_query({}) is None

    def test_none_params(self) -> None:
        from jsonql.adapters.mongo_base import get_id_from_query

        assert get_id_from_query(None) is None


class TestBuildRestMutation:
    """Tests for build_rest_mutation()."""

    def test_post_create(self) -> None:
        from jsonql.adapters.mongo_base import build_rest_mutation

        result = build_rest_mutation("POST", {}, {"data": {"name": "Alice"}})
        assert result is not None
        assert result["op"] == "create"
        assert result["data"] == {"name": "Alice"}

    def test_patch_update_with_id(self) -> None:
        from jsonql.adapters.mongo_base import build_rest_mutation

        result = build_rest_mutation("PATCH", {"id": "5"}, {"data": {"name": "Bob"}})
        assert result is not None
        assert result["op"] == "update"
        assert result["where"] == {"id": 5}

    def test_delete_with_id(self) -> None:
        from jsonql.adapters.mongo_base import build_rest_mutation

        result = build_rest_mutation("DELETE", {"id": "3"}, None)
        assert result is not None
        assert result["op"] == "delete"
        assert result["where"] == {"id": 3}

    def test_get_returns_none(self) -> None:
        from jsonql.adapters.mongo_base import build_rest_mutation

        assert build_rest_mutation("GET", {}, {}) is None
