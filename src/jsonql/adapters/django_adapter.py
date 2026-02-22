"""Django REST Framework adapter — a class-based view for JSONQL.

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

from .base import AdapterOptions, BaseHandler


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

        def view(request: Any, path: str = "", **kwargs: Any) -> Any:
            try:
                raw_input = json.loads(request.body) if request.body else {}
            except (json.JSONDecodeError, ValueError):
                raw_input = {}

            loop = asyncio.new_event_loop()
            try:
                result, status = loop.run_until_complete(
                    handler.process_request(
                        raw_input, request, request.method, path
                    )
                )
            finally:
                loop.close()

            return JsonResponse(result, status=status, safe=False)

        return view
