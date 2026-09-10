from app.agent.utils import citations_are_valid, heuristic_route


def test_citation_validation_rejects_unknown_sources():
    evidence = [{"label": "S1"}]
    assert citations_are_valid("Answer [S1].", evidence)
    assert not citations_are_valid("Answer [S2].", evidence)
    assert not citations_are_valid("Answer without a source.", evidence)


def test_router_sends_comparison_to_research():
    assert heuristic_route("Compare Business versus Enterprise audit retention") == "research"
    assert heuristic_route("What is the API timeout?") == "retrieve"
    assert heuristic_route("hello") == "direct"
