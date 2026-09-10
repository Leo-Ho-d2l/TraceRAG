from __future__ import annotations


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    for index, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def fact_coverage(answer: str, facts: list[str]) -> float:
    if not facts:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for fact in facts if fact.lower() in answer_lower)
    return hits / len(facts)


def citation_present(answer: str) -> float:
    import re

    return 1.0 if re.search(r"\[S\d+\]", answer) else 0.0
