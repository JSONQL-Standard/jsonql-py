"""FastAPI adapter for MongoDB — creates an APIRouter with JSONQL routes.

Usage::

    from fastapi import FastAPI
    from jsonql.adapters import create_fastapi_mongo_router, MongoAdapterOptions
    from jsonql import must_connect_mongo, must_load_schema

    client, db = must_connect_mongo("mongodb://localhost:27017", "mydb")
    schema = must_load_schema("schema.json")

    app = FastAPI()
    router = create_fastapi_mongo_router(MongoAdapterOptions(
        database=db,
        schema=schema,
    ))
    app.include_router(router, prefix="/jsonql")
"""

from typing import Any, Optional

from ..errors import AdapterError, JsonQLError
from .fastapi_adapter import _extract_raw_input
from .mongo_base import MongoAdapterOptions, MongoBaseHandler


def create_fastapi_mongo_router(
    options: MongoAdapterOptions,
    *,
    prefix: str = "",
    tags: Optional[list[str]] = None,
) -> Any:
    """Create a FastAPI ``APIRouter`` wired to JSONQL with MongoDB."""
    from fastapi import APIRouter, Request

    from .fastapi_adapter import _json_response

    router = APIRouter(prefix=prefix, tags=tags or ["jsonql-mongo"])
    handler = MongoBaseHandler(options)

    async def _handle(request: Request, path: str = "") -> Any:
        try:
            raw_input = await _extract_raw_input(request)
            result, status = await handler.process_request(raw_input, request, request.method, path)
            return _json_response(result, status)
        except AdapterError as exc:
            return _json_response({"error": str(exc)}, exc.status)
        except (ValueError, TypeError, JsonQLError) as exc:
            return _json_response({"error": str(exc)}, 400)
        except Exception as exc:
            if handler.logger:
                handler.logger.error(f"[JSONQL] Unhandled error: {exc}")
            return _json_response({"error": str(exc)}, 500)

    router.add_api_route(
        "/{path:path}",
        _handle,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    router.add_api_route(
        "/",
        _handle,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )

    return router
