"""Flask adapter for MongoDB — creates a Blueprint with JSONQL routes.

Usage::

    from flask import Flask
    from jsonql.adapters import create_flask_mongo_blueprint, MongoAdapterOptions
    from jsonql import must_connect_mongo, must_load_schema

    client, db = must_connect_mongo("mongodb://localhost:27017", "mydb")
    schema = must_load_schema("schema.json")

    app = Flask(__name__)
    bp = create_flask_mongo_blueprint(MongoAdapterOptions(
        database=db,
        schema=schema,
    ))
    app.register_blueprint(bp, url_prefix="/jsonql")
"""

from __future__ import annotations

import asyncio
from typing import Any

from .flask_adapter import _extract_raw_input
from .mongo_base import MongoAdapterOptions, MongoBaseHandler


def create_flask_mongo_blueprint(
    options: MongoAdapterOptions,
    *,
    url_prefix: str = "",
    name: str = "jsonql_mongo",
) -> Any:
    """Create a Flask ``Blueprint`` wired to JSONQL with MongoDB."""
    from flask import Blueprint, jsonify, request

    bp = Blueprint(name, __name__, url_prefix=url_prefix)
    handler = MongoBaseHandler(options)

    def _run(coro: Any) -> Any:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    @bp.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    @bp.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def handle(path: str) -> Any:
        raw_input = _extract_raw_input(request)
        result, status = _run(
            handler.process_request(raw_input, request, request.method, path)
        )
        if result is None:
            return jsonify(None), 200
        return jsonify(result), status

    return bp
