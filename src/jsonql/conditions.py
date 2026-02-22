"""Condition helper functions for JSONQL Python SDK.

These create WHERE condition dicts compatible with the JSONQL query
syntax, providing a more Pythonic API than raw dicts.

Example::

    from jsonql.conditions import eq, gt, field, and_

    query = (
        QueryBuilder()
        .from_table("users")
        .where(and_(
            field("age", gt(18)),
            field("status", eq("active")),
        ))
        .build()
    )
"""

from __future__ import annotations

from typing import Any


def eq(value: Any) -> dict[str, Any]:
    """Equality condition: ``{"eq": value}``."""
    return {"eq": value}


def neq(value: Any) -> dict[str, Any]:
    """Not-equal condition: ``{"neq": value}``."""
    return {"neq": value}


def gt(value: Any) -> dict[str, Any]:
    """Greater-than condition: ``{"gt": value}``."""
    return {"gt": value}


def gte(value: Any) -> dict[str, Any]:
    """Greater-than-or-equal condition: ``{"gte": value}``."""
    return {"gte": value}


def lt(value: Any) -> dict[str, Any]:
    """Less-than condition: ``{"lt": value}``."""
    return {"lt": value}


def lte(value: Any) -> dict[str, Any]:
    """Less-than-or-equal condition: ``{"lte": value}``."""
    return {"lte": value}


def is_in(*values: Any) -> dict[str, Any]:
    """IN condition: ``{"in": [values...]}``."""
    return {"in": list(values)}


def not_in(*values: Any) -> dict[str, Any]:
    """NOT IN condition: ``{"nin": [values...]}``."""
    return {"nin": list(values)}


def like(pattern: str) -> dict[str, Any]:
    """LIKE condition: ``{"like": pattern}``."""
    return {"like": pattern}


def contains(value: str) -> dict[str, Any]:
    """Contains condition: ``{"like": "%value%"}``."""
    return {"like": f"%{value}%"}


def starts_with(value: str) -> dict[str, Any]:
    """Starts-with condition: ``{"like": "value%"}``."""
    return {"like": f"{value}%"}


def ends_with(value: str) -> dict[str, Any]:
    """Ends-with condition: ``{"like": "%value"}``."""
    return {"like": f"%{value}"}


def field(name: str, condition: dict[str, Any]) -> dict[str, Any]:
    """Create a field condition: ``{name: condition}``."""
    return {name: condition}


def and_(*conditions: dict[str, Any]) -> dict[str, Any]:
    """AND logical condition."""
    return {"and": list(conditions)}


def or_(*conditions: dict[str, Any]) -> dict[str, Any]:
    """OR logical condition."""
    return {"or": list(conditions)}


def not_(condition: dict[str, Any]) -> dict[str, Any]:
    """NOT logical condition."""
    return {"not": condition}
