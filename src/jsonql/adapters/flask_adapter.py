"""Flask adapter — creates a Blueprint with JSONQL routes.

Usage::

    from flask import Flask
    from jsonql.adapters import create_flask_blueprint, AdapterOptions

    app = Flask(__name__)
    bp = create_flask_blueprint(AdapterOptions(
        dialect="sqlite",
        execute=run_sql,
        schema=my_schema,
    ))
    app.register_blueprint(bp, url_prefix="/jsonql")
"""

from __future__ import annotations

import asyncio
from typing import Any

from .base import AdapterOptions, BaseHandler


def create_flask_blueprint(
    options: AdapterOptions,
    *,
    url_prefix: str = "",
    name: str = "jsonql",
) -> Any:
    """Create a Flask ``Blueprint`` wired to JSONQL."""
    from flask import Blueprint, jsonify, request

    bp = Blueprint(name, __name__, url_prefix=url_prefix)
    handler = BaseHandler(options)

    def _run(coro: Any) -> Any:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    @bp.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    @bp.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def handle(path: str) -> Any:
        raw_input = request.get_json(silent=True) or {}
        result, status = _run(
            handler.process_request(raw_input, request, request.method, path)
        )
        if result is None:
            return jsonify(None), 200
        return jsonify(result), status

    return bp
