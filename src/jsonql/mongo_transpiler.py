"""JSONQL -> MongoDB transpiler for the Python SDK.

Converts JSONQL queries into MongoDB operation descriptors
(filter documents, projections, sort specs, aggregation pipelines)
that can be executed directly with PyMongo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .errors import JsonQLTranspileError
from .types import JsonQLMutation, JsonQLQuery, is_mutation

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_valid_identifier(name: str) -> bool:
    return bool(_IDENT_RE.match(name))


@dataclass
class MongoResult:
    """Result of transpiling a JSONQL query to MongoDB operations."""

    collection: str
    operation: str  # "find", "insert_one", "insert_many", "update_many", "delete_many", "aggregate"
    filter: dict[str, Any] = field(default_factory=dict)
    projection: dict[str, Any] | None = None
    sort: list[tuple[str, int]] | None = None
    limit: int | None = None
    skip: int | None = None
    pipeline: list[dict[str, Any]] | None = None
    document: dict[str, Any] | list[dict[str, Any]] | None = None
    update: dict[str, Any] | None = None


class MongoTranspiler:
    """Converts JSONQL queries/mutations to MongoDB operations."""

    def transpile(
        self,
        statement: JsonQLQuery | JsonQLMutation,
        collection: str,
    ) -> MongoResult:
        if is_mutation(statement):
            assert isinstance(statement, JsonQLMutation)
            return self._transpile_mutation(statement, collection)
        assert isinstance(statement, JsonQLQuery)
        return self._transpile_query(statement, collection)

    def _transpile_query(self, query: JsonQLQuery, collection: str) -> MongoResult:
        if not _is_valid_identifier(collection):
            raise JsonQLTranspileError(f"Invalid collection name: {collection}")

        result = MongoResult(collection=collection, operation="find")

        # WHERE -> filter
        if query.where:
            result.filter = self._process_where(query.where)

        # FIELDS -> projection
        if query.fields:
            result.projection = {f: 1 for f in query.fields}

        # SORT
        if query.sort:
            sort_list: list[tuple[str, int]] = []
            for s in query.sort:
                if s.startswith("-"):
                    sort_list.append((s[1:], -1))
                else:
                    sort_list.append((s, 1))
            result.sort = sort_list

        # LIMIT
        if query.limit is not None and query.limit > 0:
            result.limit = query.limit

        # SKIP / OFFSET
        if query.offset is not None and query.offset > 0:
            result.skip = query.offset

        # DISTINCT -> aggregation pipeline
        if query.distinct and (query.distinct.all or query.distinct.fields):
            result.operation = "aggregate"
            pipeline: list[dict[str, Any]] = []

            # $match stage
            if result.filter:
                pipeline.append({"$match": result.filter})

            # Determine distinct fields
            if query.distinct.fields:
                distinct_fields = query.distinct.fields
            elif query.fields:
                distinct_fields = list(query.fields)
            else:
                distinct_fields = []

            if distinct_fields:
                # $group by distinct fields as _id
                group_id = {f: f"${f}" for f in distinct_fields}
                group_stage: dict[str, Any] = {"_id": group_id}
                pipeline.append({"$group": group_stage})

                # $project to flatten _id back into fields
                project_stage = {"_id": 0}
                for f in distinct_fields:
                    project_stage[f] = f"$_id.{f}"
                # Also project non-distinct selected fields
                if query.fields:
                    for f in query.fields:
                        if f not in distinct_fields:
                            project_stage[f] = 1
                pipeline.append({"$project": project_stage})

            # $sort stage
            if result.sort:
                sort_doc = {k: v for k, v in result.sort}
                pipeline.append({"$sort": sort_doc})

            # $skip / $limit stages
            if result.skip:
                pipeline.append({"$skip": result.skip})
            if result.limit:
                pipeline.append({"$limit": result.limit})

            result.pipeline = pipeline
            return result

        # AGGREGATE -> aggregation pipeline
        if query.aggregate:
            result.operation = "aggregate"
            pipeline = []

            # $match stage
            if result.filter:
                pipeline.append({"$match": result.filter})

            # $group stage
            group_stage = {}
            if query.group_by:
                group_id = {g: f"${g}" for g in query.group_by}
                group_stage["_id"] = group_id
                for g in query.group_by:
                    group_stage[g] = {"$first": f"${g}"}
            else:
                group_stage["_id"] = None

            for alias, agg_def in query.aggregate.items():
                if not isinstance(agg_def, dict):
                    continue
                for func_name, field_name in agg_def.items():
                    if not isinstance(field_name, str):
                        continue
                    if func_name == "count":
                        if field_name == "*":
                            group_stage[alias] = {"$sum": 1}
                        else:
                            group_stage[alias] = {
                                "$sum": {
                                    "$cond": [
                                        {"$ne": [f"${field_name}", None]},
                                        1,
                                        0,
                                    ]
                                }
                            }
                    elif func_name == "sum":
                        group_stage[alias] = {"$sum": f"${field_name}"}
                    elif func_name == "avg":
                        group_stage[alias] = {"$avg": f"${field_name}"}
                    elif func_name == "min":
                        group_stage[alias] = {"$min": f"${field_name}"}
                    elif func_name == "max":
                        group_stage[alias] = {"$max": f"${field_name}"}
                    else:
                        raise ValueError(f"Unknown aggregate function: {func_name}")

            pipeline.append({"$group": group_stage})

            # $sort stage
            if result.sort:
                sort_doc = {k: v for k, v in result.sort}
                pipeline.append({"$sort": sort_doc})

            # $skip / $limit stages
            if result.skip:
                pipeline.append({"$skip": result.skip})
            if result.limit:
                pipeline.append({"$limit": result.limit})

            result.pipeline = pipeline

        return result

    def _transpile_mutation(self, mutation: JsonQLMutation, collection: str) -> MongoResult:
        if not _is_valid_identifier(collection):
            raise JsonQLTranspileError(f"Invalid collection name: {collection}")

        if mutation.op == "create":
            data = mutation.data
            if isinstance(data, list):
                return MongoResult(
                    collection=collection,
                    operation="insert_many",
                    document=data,
                )
            return MongoResult(
                collection=collection,
                operation="insert_one",
                document=data,
            )

        if mutation.op == "update":
            filt = self._process_where(mutation.where) if mutation.where else {}
            return MongoResult(
                collection=collection,
                operation="update_many",
                filter=filt,
                update={"$set": mutation.patch},
            )

        if mutation.op == "delete":
            filt = self._process_where(mutation.where) if mutation.where else {}
            return MongoResult(
                collection=collection,
                operation="delete_many",
                filter=filt,
            )

        raise JsonQLTranspileError(f"Unknown mutation op: {mutation.op}")

    _KNOWN_OPS = frozenset(
        {
            "eq",
            "ne",
            "neq",
            "gt",
            "gte",
            "lt",
            "lte",
            "in",
            "nin",
            "like",
            "contains",
            "starts",
            "ends",
        }
    )

    def _process_where(self, where: dict[str, Any]) -> dict[str, Any]:
        filt: dict[str, Any] = {}

        for field_name, cond in where.items():
            # --- logical operators ---
            if field_name in ("or", "OR"):
                if isinstance(cond, list):
                    or_conditions = [
                        self._process_where(item) for item in cond if isinstance(item, dict)
                    ]
                    if or_conditions:
                        filt["$or"] = or_conditions
                continue

            if field_name in ("and", "AND"):
                if isinstance(cond, list):
                    and_conditions = [
                        self._process_where(item) for item in cond if isinstance(item, dict)
                    ]
                    if and_conditions:
                        filt["$and"] = and_conditions
                continue

            if field_name in ("not", "NOT"):
                if isinstance(cond, dict):
                    not_filter = self._process_where(cond)
                    filt["$nor"] = [not_filter]
                continue

            if not _is_valid_identifier(field_name):
                raise JsonQLTranspileError(f"Invalid field name in where clause: {field_name}")

            if isinstance(cond, dict):
                # Validate operators
                for op_key in cond:
                    if op_key not in self._KNOWN_OPS:
                        raise JsonQLTranspileError(
                            f"Unknown operator '{op_key}' for field '{field_name}'"
                        )

                mongo_op: dict[str, Any] = {}
                if "eq" in cond:
                    filt[field_name] = cond["eq"]
                    continue
                if "ne" in cond:
                    mongo_op["$ne"] = cond["ne"]
                if "neq" in cond:
                    mongo_op["$ne"] = cond["neq"]
                if "gt" in cond:
                    mongo_op["$gt"] = cond["gt"]
                if "gte" in cond:
                    mongo_op["$gte"] = cond["gte"]
                if "lt" in cond:
                    mongo_op["$lt"] = cond["lt"]
                if "lte" in cond:
                    mongo_op["$lte"] = cond["lte"]
                if "like" in cond:
                    pattern = str(cond["like"]).replace("%", ".*").replace("_", ".")
                    mongo_op["$regex"] = pattern
                    mongo_op["$options"] = "i"
                if "contains" in cond:
                    mongo_op["$regex"] = re.escape(str(cond["contains"]))
                    mongo_op["$options"] = "i"
                if "starts" in cond:
                    mongo_op["$regex"] = f"^{re.escape(str(cond['starts']))}"
                    mongo_op["$options"] = "i"
                if "ends" in cond:
                    mongo_op["$regex"] = f"{re.escape(str(cond['ends']))}$"
                    mongo_op["$options"] = "i"
                if "in" in cond:
                    vals = cond["in"]
                    if isinstance(vals, list):
                        mongo_op["$in"] = vals
                if "nin" in cond:
                    vals = cond["nin"]
                    if isinstance(vals, list):
                        mongo_op["$nin"] = vals
                if mongo_op:
                    filt[field_name] = mongo_op
            else:
                filt[field_name] = cond

        return filt
