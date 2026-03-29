"""Django adapter — a class-based view for JSONQL.

Usage::

    # urls.py
    from jsonql.adapters import JsonQLDjangoView, AdapterOptions

    options = AdapterOptions(
        dialect="postgres",
        execute=run_sql,
        schema=my_schema,
    )

    urlpatterns = [
        path("jsonql/", JsonQLDjangoView.as_view(options=options)),
        path("jsonql/<path:path>/", JsonQLDjangoView.as_view(options=options)),
    ]
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, ClassVar

from ..errors import AdapterError, JsonQLError
from .base import AdapterOptions, BaseHandler


def _extract_raw_input(request: Any) -> Any:
    """Extract the JSONQL query from a Django request.

    - GET with ``?q=<json>`` → parse the JSON string
    - GET without ``q``      → use query params as dict
    - POST/PUT/PATCH/DELETE  → use the JSON body
    """
    if request.method == "GET":
        q = request.GET.get("q")
        if q:
            try:
                return json.loads(q)
            except (ValueError, json.JSONDecodeError):
                return q
        if request.GET:
            return dict(request.GET)
        return {}
    try:
        return json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        return {}


class JsonQLDjangoView:
    """Django class-based view for JSONQL.

    Designed to work with or without Django REST Framework.
    """

    options: ClassVar[AdapterOptions]

    def __init__(self, **kwargs: Any) -> None:
        self._handler: BaseHandler | None = None
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def as_view(cls, *, options: AdapterOptions | None = None, **initkwargs: Any) -> Any:
        """Return a Django view function."""
        from django.http import JsonResponse

        handler = BaseHandler(options or cls.options)

        def _run(coro: Any) -> Any:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        def view(request: Any, path: str = "", **kwargs: Any) -> Any:
            try:
                raw_input = _extract_raw_input(request)
                result, status = _run(
                    handler.process_request(
                        raw_input, request, request.method, path
                    )
                )
                return JsonResponse(result, status=status, safe=False)
            except AdapterError as exc:
                return JsonResponse({"error": str(exc)}, status=exc.status)
            except (ValueError, TypeError, JsonQLError) as exc:
                return JsonResponse({"error": str(exc)}, status=400)
            except Exception as exc:
                if handler.logger:
                    handler.logger.error(f"[JSONQL] Unhandled error: {exc}")
                return JsonResponse({"error": str(exc)}, status=500)

        from django.views.decorators.csrf import csrf_exempt
        return csrf_exempt(view)
