"""Tests for the JSONQL error types."""

import pytest
from jsonql.errors import (
    JsonQLError,
    JsonQLValidationError,
    JsonQLTranspileError,
    JsonQLExecutionError,
    AdapterError,
)
from jsonql.types import ValidationError as ValidationErrorItem


class TestJsonQLError:
    """Tests for the base error class."""

    def test_basic_error(self):
        err = JsonQLError("Something went wrong")
        assert str(err) == "Something went wrong"
        assert err.code == "JSONQL_ERROR"

    def test_with_custom_code(self):
        err = JsonQLError("Custom error", code="CUSTOM_CODE")
        assert str(err) == "Custom error"
        assert err.code == "CUSTOM_CODE"


class TestJsonQLValidationError:
    """Tests for validation-specific errors."""

    def test_without_child_errors(self):
        err = JsonQLValidationError("Invalid query")
        assert err.code == "VALIDATION_ERROR"
        assert err.errors == []

    def test_with_child_errors(self):
        children = [
            ValidationErrorItem(code="MISSING_FIELD", message="age is required", path="where.age"),
            ValidationErrorItem(code="INVALID_TYPE", message="must be int", path="where.age"),
        ]
        err = JsonQLValidationError("Validation failed", errors=children)
        assert err.code == "VALIDATION_ERROR"
        assert len(err.errors) == 2
        assert err.errors[0].code == "MISSING_FIELD"

    def test_first_error_property(self):
        children = [
            ValidationErrorItem(code="MISSING_FIELD", message="age is required", path="where.age"),
        ]
        err = JsonQLValidationError("Validation failed", errors=children)
        assert err.first_error is not None
        assert err.first_error.code == "MISSING_FIELD"

    def test_first_error_empty(self):
        err = JsonQLValidationError("Validation failed")
        assert err.first_error is None


class TestJsonQLTranspileError:
    """Tests for transpile errors."""

    def test_basic(self):
        err = JsonQLTranspileError("Cannot transpile aggregation without group_by")
        assert str(err) == "Cannot transpile aggregation without group_by"
        assert err.code == "TRANSPILE_ERROR"


class TestJsonQLExecutionError:
    """Tests for execution errors."""

    def test_basic(self):
        err = JsonQLExecutionError("Database connection failed")
        assert str(err) == "Database connection failed"
        assert err.code == "EXECUTION_ERROR"

    def test_with_cause(self):
        cause = RuntimeError("Connection refused")
        err = JsonQLExecutionError("Database connection failed", cause=cause)
        assert err.code == "EXECUTION_ERROR"
        assert err.__cause__ is cause


class TestAdapterError:
    """Tests for the adapter error class."""

    def test_with_status(self):
        err = AdapterError(403, "Forbidden")
        assert err.status == 403
        assert str(err) == "Forbidden"
        assert err.code == "ADAPTER_ERROR"

    def test_with_custom_code(self):
        err = AdapterError(404, "Not found", code="NOT_FOUND")
        assert err.status == 404
        assert err.code == "NOT_FOUND"


class TestErrorInheritance:
    """Verify the error class hierarchy."""

    def test_types(self):
        assert issubclass(JsonQLValidationError, JsonQLError)
        assert issubclass(JsonQLTranspileError, JsonQLError)
        assert issubclass(JsonQLExecutionError, JsonQLError)
        assert issubclass(AdapterError, JsonQLError)

    def test_catch_all(self):
        """All subclasses can be caught as JsonQLError."""
        exceptions = [
            JsonQLValidationError("a"),
            JsonQLTranspileError("b"),
            JsonQLExecutionError("c"),
            AdapterError(500, "d"),
        ]
        for exc in exceptions:
            try:
                raise exc
            except JsonQLError as caught:
                assert isinstance(caught, type(exc))