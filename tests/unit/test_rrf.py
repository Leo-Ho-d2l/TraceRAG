import uuid

from app.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_rewards_items_present_in_multiple_rankings():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, b], [c, a]], k=60)
    assert scores[a] > scores[b]
    assert scores[a] > scores[c]


def test_rrf_uses_one_based_ranks():
    """The first item of a single list must score exactly 1/(k+1)."""
    a, b = uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, b]], k=60)
    assert scores[a] == 1 / 61
    assert scores[b] == 1 / 62
    assert scores[a] > scores[b], "rank direction must be higher-is-better"


def test_rrf_accumulates_across_lists():
    """A document both branches rank first must outrank a single-branch first."""
    a, b = uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a], [a, b]], k=60)
    assert scores[a] == 2 / 61
    assert scores[a] > scores[b]


def test_rrf_ignores_duplicate_ids_within_one_list():
    """A list is a ranking, so a repeated id must not contribute twice."""
    a = uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, a]], k=60)
    assert scores[a] == 1 / 61 + 1 / 62


def test_rrf_handles_empty_and_missing_lists():
    a = uuid.uuid4()
    assert reciprocal_rank_fusion([], k=60) == {}
    assert reciprocal_rank_fusion([[], []], k=60) == {}
    assert reciprocal_rank_fusion([[], [a]], k=60) == {a: 1 / 61}


def test_rrf_k_dampens_top_rank_dominance():
    a, b = uuid.uuid4(), uuid.uuid4()
    small_k = reciprocal_rank_fusion([[a, b]], k=1)
    large_k = reciprocal_rank_fusion([[a, b]], k=1000)
    assert small_k[a] / small_k[b] > large_k[a] / large_k[b]
