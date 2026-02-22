"""FastAPI adapter — creates an APIRouter with JSONQL routes.

Usage::

    from fastapi import FastAPI
    from jsonql.adapters import create_fastapi_router, AdapterOptions

    app = FastAPI()
    router = create_fastapi_router(AdapterOptions(
        dialect="postgres",
        execute=run_sql,
        schema=my_schema,
    ))
    app.include_router(router, prefix="/jsonql")
"""

from __future__ import annotations

from typing import Any

from .base import AdapterOptions, BaseHandler


def create_fastapi_router(
    options: AdapterOptions,
    *,
    prefix: str = "",
    tags: list[str] | None = None,
) -> Any:
    """Create a FastAPI ``APIRouter`` wired to JSONQL."""
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter(prefix=prefix, tags=tags or ["jsonql"])
    handler = BaseHandler(options)

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
