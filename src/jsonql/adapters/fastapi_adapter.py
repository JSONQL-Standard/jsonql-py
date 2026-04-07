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

import datetime
import json as _json
from typing import Any, Optional

from ..errors import AdapterError, JsonQLError
from .base import AdapterOptions, BaseHandler


async def _extract_raw_input(request: Any) -> Any:
    """Extract the JSONQL query from a FastAPI request.

    - GET with ``?q=<json>`` → parse the JSON string
    - GET without ``q``      → use query params as dict
    - POST/PUT/PATCH/DELETE  → use the JSON body
    """
    if request.method == "GET":
        q = request.query_params.get("q")
        if q:
            try:
                return _json.loads(q)
            except (ValueError, _json.JSONDecodeError):
                return q
        if request.query_params:
            return dict(request.query_params)
        return {}
    try:
        return await request.json()
    except Exception:
        return {}


class _JSONEncoder(_json.JSONEncoder):
    """JSON encoder that handles datetime, date, Decimal."""

    def default(self, o: Any) -> Any:
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        return super().default(o)


def _json_response(content: Any, status_code: int = 200) -> Any:
    """Create a JSON response with datetime-aware serialisation."""
    from starlette.responses import Response

    body = _json.dumps(content, cls=_JSONEncoder)
    return Response(content=body, status_code=status_code, media_type="application/json")


def create_fastapi_router(
    options: AdapterOptions,
    *,
    prefix: str = "",
    tags: Optional[list[str]] = None,
) -> Any:
    """Create a FastAPI ``APIRouter`` wired to JSONQL."""
    from fastapi import APIRouter, Request

    router = APIRouter(prefix=prefix, tags=tags or ["jsonql"])
    handler = BaseHandler(options)

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
