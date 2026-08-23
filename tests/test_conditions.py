"""Tests for the JSONQL condition helper functions."""

from jsonql.conditions import (
    and_,
    contains,
    ends_with,
    eq,
    field,
    gt,
    gte,
    is_in,
    like,
    lt,
    lte,
    neq,
    not_,
    not_in,
    or_,
    starts_with,
)


class TestComparisonConditions:
    """Tests for comparison condition helpers."""

    def test_eq(self):
        assert eq(42) == {"eq": 42}
        assert eq("hello") == {"eq": "hello"}
        assert eq(None) == {"eq": None}

    def test_neq(self):
        assert neq(42) == {"neq": 42}
        assert neq("hello") == {"neq": "hello"}

    def test_gt(self):
        assert gt(18) == {"gt": 18}
        assert gt(3.14) == {"gt": 3.14}

    def test_gte(self):
        assert gte(18) == {"gte": 18}
        assert gte(0) == {"gte": 0}

    def test_lt(self):
        assert lt(100) == {"lt": 100}
        assert lt(-5) == {"lt": -5}

    def test_lte(self):
        assert lte(18) == {"lte": 18}
        assert lte(0) == {"lte": 0}


class TestSetConditions:
    """Tests for set-based condition helpers (IN, NOT IN)."""

    def test_is_in(self):
        assert is_in(1, 2, 3) == {"in": [1, 2, 3]}
        assert is_in("a") == {"in": ["a"]}
        assert is_in() == {"in": []}

    def test_is_in_with_single_value(self):
        result = is_in(42)
        assert result == {"in": [42]}

    def test_not_in(self):
        assert not_in(1, 2, 3) == {"nin": [1, 2, 3]}
        assert not_in("a") == {"nin": ["a"]}
        assert not_in() == {"nin": []}


class TestStringPatternConditions:
    """Tests for string pattern matching helpers."""

    def test_like(self):
        assert like("hello%") == {"like": "hello%"}
        assert like("%world%") == {"like": "%world%"}

    def test_contains(self):
        assert contains("hello") == {"like": "%hello%"}
        assert contains("") == {"like": "%%"}

    def test_starts_with(self):
        assert starts_with("hello") == {"like": "hello%"}
        assert starts_with("") == {"like": "%"}

    def test_ends_with(self):
        assert ends_with("world") == {"like": "%world"}
        assert ends_with("") == {"like": "%"}


class TestFieldCondition:
    """Tests for the field() helper."""

    def test_field_with_eq(self):
        assert field("age", eq(42)) == {"age": {"eq": 42}}

    def test_field_with_gt(self):
        assert field("price", gt(100)) == {"price": {"gt": 100}}

    def test_field_with_is_in(self):
        assert field("status", is_in("a", "b")) == {"status": {"in": ["a", "b"]}}

    def test_field_with_like(self):
        assert field("name", like("john%")) == {"name": {"like": "john%"}}


class TestLogicalConditions:
    """Tests for logical combinators (AND, OR, NOT)."""

    def test_and_with_two_conditions(self):
        c1 = field("age", gt(18))
        c2 = field("status", eq("active"))
        result = and_(c1, c2)
        assert result == {"and": [{"age": {"gt": 18}}, {"status": {"eq": "active"}}]}

    def test_and_with_single_condition(self):
        c = field("age", gt(18))
        assert and_(c) == {"and": [{"age": {"gt": 18}}]}

    def test_and_with_no_conditions(self):
        assert and_() == {"and": []}

    def test_and_nested_with_or(self):
        """AND containing an OR — realistic nested query."""
        result = and_(
            field("age", gt(18)),
            or_(
                field("status", eq("active")),
                field("role", eq("admin")),
            ),
        )
        assert result == {
            "and": [
                {"age": {"gt": 18}},
                {"or": [
                    {"status": {"eq": "active"}},
                    {"role": {"eq": "admin"}},
                ]},
            ],
        }

    def test_or_with_two_conditions(self):
        c1 = field("role", eq("admin"))
        c2 = field("role", eq("moderator"))
        result = or_(c1, c2)
        assert result == {"or": [{"role": {"eq": "admin"}}, {"role": {"eq": "moderator"}}]}

    def test_or_with_no_conditions(self):
        assert or_() == {"or": []}

    def test_not_single_condition(self):
        c = field("status", eq("banned"))
        assert not_(c) == {"not": {"status": {"eq": "banned"}}}

    def test_not_nested_with_and(self):
        """NOT wrapping an AND group."""
        result = not_(
            and_(
                field("age", lt(13)),
                field("status", eq("active")),
            ),
        )
        assert result == {
            "not": {
                "and": [
                    {"age": {"lt": 13}},
                    {"status": {"eq": "active"}},
                ],
            },
        }


class TestIntegrationBuilderWithConditions:
    """Integration: conditions with QueryBuilder produce expected dict structures.

    These test that conditions created via ``jsonql.conditions`` are
    compatible with the QueryBuilder.
    """

    def test_simple_where(self):
        from jsonql import QueryBuilder

        query = (
            QueryBuilder()
            .from_table("users")
            .where(field("age", gt(18)))
            .build()
        )
        assert query.from_table == "users"
        assert query.where == {"age": {"gt": 18}}

    def test_complex_where(self):
        from jsonql import QueryBuilder

        query = (
            QueryBuilder()
            .from_table("users")
            .where(
                and_(
                    field("age", gte(18)),
                    field("country", is_in("US", "CA")),
                    or_(
                        field("status", eq("active")),
                        field("role", eq("admin")),
                    ),
                )
            )
            .build()
        )
        assert query.from_table == "users"
        assert query.where["and"][0] == {"age": {"gte": 18}}
        assert query.where["and"][1] == {"country": {"in": ["US", "CA"]}}
        assert query.where["and"][2]["or"][0] == {"status": {"eq": "active"}}

    def test_select_with_conditions(self):
        from jsonql import QueryBuilder

        query = (
            QueryBuilder()
            .from_table("products")
            .select("name", "price")
            .where(and_(
                field("price", gt(10)),
                field("price", lt(100)),
            ))
            .build()
        )
        assert query.fields == ["name", "price"]
        assert query.where == {
            "and": [
                {"price": {"gt": 10}},
                {"price": {"lt": 100}},
            ],
        }
