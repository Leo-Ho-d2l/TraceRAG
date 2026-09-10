import uuid

from app.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_rewards_items_present_in_multiple_rankings():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, b], [c, a]], k=60)
    assert scores[a] > scores[b]
    assert scores[a] > scores[c]
