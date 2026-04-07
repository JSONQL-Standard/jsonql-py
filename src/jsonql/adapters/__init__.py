"""JSONQL framework adapters — Flask, FastAPI, Django REST + MongoDB variants."""

from ..errors import AdapterError
from .base import (
    AdapterOptions,
    BaseHandler,
)
from .base import (
    _infer_mutation as infer_mutation,
)
from .django_adapter import JsonQLDjangoView
from .django_mongo import JsonQLDjangoMongoView
from .fastapi_adapter import create_fastapi_router
from .fastapi_mongo import create_fastapi_mongo_router
from .flask_adapter import create_flask_blueprint
from .flask_mongo import create_flask_mongo_blueprint
from .mongo_base import (
    MongoAdapterOptions,
    MongoBaseHandler,
    build_rest_mutation,
    get_id_from_query,
)

__all__ = [
    # SQL adapters
    "BaseHandler",
    "AdapterOptions",
    "create_flask_blueprint",
    "create_fastapi_router",
    "JsonQLDjangoView",
    # MongoDB adapters
    "MongoBaseHandler",
    "MongoAdapterOptions",
    "create_flask_mongo_blueprint",
    "create_fastapi_mongo_router",
    "JsonQLDjangoMongoView",
    # Shared helpers
    "AdapterError",
    "infer_mutation",
    "get_id_from_query",
    "build_rest_mutation",
]
