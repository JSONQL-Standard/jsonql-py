"""MongoDB driver for JSONQL Python SDK.

Executes MongoResult operations against a MongoDB database using PyMongo.
"""

from __future__ import annotations

from typing import Any

from .mongo_transpiler import MongoResult


class MongoDBDriver:
    """Executes MongoResult operations against MongoDB."""

    def __init__(self, client: Any, db_name: str) -> None:
        self._client = client
        self._db = client[db_name]

    async def execute(self, result: MongoResult) -> Any:
        """Dispatch a MongoResult to the appropriate MongoDB operation."""
        coll = self._db[result.collection]
        op = result.operation

        if op == "find":
            return await self._execute_find(coll, result)
        if op == "aggregate":
            return await self._execute_aggregate(coll, result)
        if op == "insert_one":
            return await self._execute_insert_one(coll, result)
        if op == "insert_many":
            return await self._execute_insert_many(coll, result)
        if op == "update_many":
            return await self._execute_update(coll, result)
        if op == "delete_many":
            return await self._execute_delete(coll, result)
        raise ValueError(f"Unsupported operation: {op}")

    async def _execute_find(self, coll: Any, result: MongoResult) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {}
        if result.projection:
            kwargs["projection"] = result.projection
        if result.sort:
            kwargs["sort"] = result.sort
        if result.skip:
            kwargs["skip"] = result.skip
        if result.limit:
            kwargs["limit"] = result.limit

        cursor = coll.find(result.filter, **kwargs)
        return [doc async for doc in cursor]

    async def _execute_aggregate(self, coll: Any, result: MongoResult) -> list[dict[str, Any]]:
        if not result.pipeline:
            return []
        cursor = coll.aggregate(result.pipeline)
        return [doc async for doc in cursor]

    async def _execute_insert_one(self, coll: Any, result: MongoResult) -> dict[str, Any]:
        res = await coll.insert_one(result.document)
        doc = dict(result.document) if isinstance(result.document, dict) else {}
        doc["_id"] = res.inserted_id
        return doc

    async def _execute_insert_many(self, coll: Any, result: MongoResult) -> dict[str, Any]:
        docs = result.document if isinstance(result.document, list) else [result.document]
        res = await coll.insert_many(docs)
        return {"inserted_count": len(res.inserted_ids)}

    async def _execute_update(self, coll: Any, result: MongoResult) -> dict[str, Any]:
        res = await coll.update_many(result.filter, result.update)
        return {"modified_count": res.modified_count}

    async def _execute_delete(self, coll: Any, result: MongoResult) -> dict[str, Any]:
        res = await coll.delete_many(result.filter)
        return {"deleted_count": res.deleted_count}

    async def close(self) -> None:
        """Close the MongoDB connection."""
        self._client.close()
