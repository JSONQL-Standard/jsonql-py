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
import json as _json
from typing import Any

from ..errors import AdapterError, JsonQLError
from .base import AdapterOptions, BaseHandler


def _extract_raw_input(request: Any) -> Any:
    """Extract the JSONQL query from a Flask request.

    - GET with ``?q=<json>`` → parse the JSON string
    - GET without ``q``      → use query params as dict
    - POST/PUT/PATCH/DELETE  → use the JSON body
    """
    if request.method == "GET":
        q = request.args.get("q")
        if q:
            try:
                return _json.loads(q)
            except (ValueError, _json.JSONDecodeError):
                return q  # let the parser deal with invalid JSON
        if request.args:
            return dict(request.args)
        return {}
    return request.get_json(silent=True) or {}


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
        try:
            raw_input = _extract_raw_input(request)
            result, status = _run(
                handler.process_request(raw_input, request, request.method, path)
            )
            if result is None:
                return jsonify(None), 200
            return jsonify(result), status
        except AdapterError as exc:
            return jsonify({"error": str(exc)}), exc.status
        except (ValueError, TypeError, JsonQLError) as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            if handler.logger:
                handler.logger.error(f"[JSONQL] Unhandled error: {exc}")
            return jsonify({"error": str(exc)}), 500

    return bp
