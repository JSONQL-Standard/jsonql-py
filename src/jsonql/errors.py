"""Custom exception hierarchy for JSONQL Python SDK."""

from __future__ import annotations

from .types import ValidationError


class JsonQLError(Exception):
    """Base class for all JSONQL errors."""

    def __init__(self, message: str, code: str = "JSONQL_ERROR") -> None:
        super().__init__(message)
        self.code = code


class JsonQLValidationError(JsonQLError):
    """Thrown when a query or mutation fails schema validation."""

    def __init__(self, message: str, errors: list[ValidationError] | None = None) -> None:
        super().__init__(message, "VALIDATION_ERROR")
        self.errors: list[ValidationError] = errors or []

    @property
    def first_error(self) -> ValidationError | None:
        """The first validation error, for fail-fast callers."""
        return self.errors[0] if self.errors else None


class JsonQLTranspileError(JsonQLError):
    """Thrown when JSONQL-to-SQL transpilation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, "TRANSPILE_ERROR")


class JsonQLExecutionError(JsonQLError):
    """Thrown when database execution fails."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message, "EXECUTION_ERROR")
        self.__cause__ = cause


class AdapterError(JsonQLError):
    """HTTP-aware error for adapter pipelines.

    Raise this from lifecycle hooks to abort the request and return a
    specific HTTP status code.  Framework adapters (Flask, FastAPI, Django)
    catch this automatically and produce a ``{"error": "…"}`` JSON response.

    Example::

        from jsonql.errors import AdapterError

        def before_create(statement, ctx):
            if not ctx.user.is_admin:
                raise AdapterError(403, "Admin access required")
            return statement
    """

    def __init__(self, status: int, message: str, code: str = "ADAPTER_ERROR") -> None:
        super().__init__(message, code)
        self.status = status
