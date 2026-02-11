"""JSONQL framework adapters — Flask, FastAPI, Django REST."""

from .base import AdapterOptions, BaseHandler
from .django_adapter import JsonQLDjangoView
from .fastapi_adapter import create_fastapi_router
from .flask_adapter import create_flask_blueprint

__all__ = [
    "BaseHandler",
    "AdapterOptions",
    "create_flask_blueprint",
    "create_fastapi_router",
    "JsonQLDjangoView",
]
