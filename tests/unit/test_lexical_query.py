"""The lexical branch must build an OR tsquery, not a conjunction.

Regression guard for the defect where `plainto_tsquery` required every word of a
natural-language question (stopwords included) to appear in one chunk, so sparse
retrieval returned nothing for 29 of 30 benchmark questions.
"""

from __future__ import annotations

from app.retrieval.hybrid import _lexical_tsquery


def _render(query: str) -> str:
    expression = _lexical_tsquery(query)
    return str(expression.compile(compile_kwargs={"literal_binds": False}))


def test_query_is_a_disjunction_not_a_conjunction() -> None:
    rendered = _render("What is the Enterprise audit log retention period?")
    assert "to_tsquery" in rendered
    # The tsquery body is assembled at runtime, so only assert on the shape:
    # it must be built from string_agg over unnest(to_tsvector(...)) and use the
    # english configuration to drop stopwords.
    assert "string_agg" in rendered
    assert "unnest" in rendered
    assert "to_tsvector" in rendered
    assert "plainto_tsquery" not in rendered, "conjunction semantics are the bug"


def test_query_text_is_bound_not_interpolated() -> None:
    """User text must reach the database as a parameter, never as SQL."""
    compiled = _lexical_tsquery("'; DROP TABLE chunks; --").compile()
    assert "DROP TABLE" not in str(compiled)
    assert compiled.params, "the question should be a bound parameter"


def test_empty_query_still_builds_a_usable_expression() -> None:
    # No crash on empty input; the resulting tsquery evaluates to NULL in
    # PostgreSQL, which matches no rows.
    assert "to_tsquery" in _render("")
    assert "to_tsquery" in _render("   ")
