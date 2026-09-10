from __future__ import annotations

from collections.abc import Hashable


def reciprocal_rank_fusion(
    ranked_lists: list[list[Hashable]], k: int = 60
) -> dict[Hashable, float]:
    """Fuse ranked lists using RRF; rank starts at one."""
    scores: dict[Hashable, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores
