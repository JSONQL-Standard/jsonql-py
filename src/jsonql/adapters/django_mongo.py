"""Django adapter for MongoDB — a class-based view for JSONQL.

Usage::

    # urls.py
    from jsonql.adapters import JsonQLDjangoMongoView, MongoAdapterOptions
    from jsonql import must_connect_mongo, must_load_schema

    client, db = must_connect_mongo("mongodb://localhost:27017", "mydb")
    schema = must_load_schema("schema.json")

    options = MongoAdapterOptions(database=db, schema=schema)

    urlpatterns = [
        path("jsonql/", JsonQLDjangoMongoView.as_view(options=options)),
        path("jsonql/<path:path>/", JsonQLDjangoMongoView.as_view(options=options)),
    ]
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, ClassVar

from .mongo_base import MongoAdapterOptions, MongoBaseHandler


class JsonQLDjangoMongoView:
    """Django class-based view for JSONQL with MongoDB."""

    options: ClassVar[MongoAdapterOptions]

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def as_view(cls, *, options: MongoAdapterOptions | None = None, **initkwargs: Any) -> Any:
        """Return a Django view function."""
        from django.http import JsonResponse

        handler = MongoBaseHandler(options or cls.options)

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
