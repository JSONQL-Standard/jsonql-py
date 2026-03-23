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

from __future__ import annotations

from typing import Any

from .mongo_base import MongoAdapterOptions, MongoBaseHandler


def create_fastapi_mongo_router(
    options: MongoAdapterOptions,
    *,
    prefix: str = "",
    tags: list[str] | None = None,
) -> Any:
    """Create a FastAPI ``APIRouter`` wired to JSONQL with MongoDB."""
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter(prefix=prefix, tags=tags or ["jsonql-mongo"])
    handler = MongoBaseHandler(options)

    @router.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    @router.api_route(
        "/",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def handle(request: Request, path: str = "") -> JSONResponse:
        try:
            raw_input = await request.json()
        except Exception:
            raw_input = {}
        result, status = await handler.process_request(
            raw_input, request, request.method, path
        )
        return JSONResponse(content=result, status_code=status)

    return router
