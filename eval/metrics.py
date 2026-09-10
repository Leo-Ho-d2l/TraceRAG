from __future__ import annotations

import re
import statistics


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    for index, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    return len(set(ranked[:k]) & relevant) / k


def fact_coverage(answer: str, facts: list[str]) -> float:
    if not facts:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for fact in facts if fact.lower() in answer_lower)
    return hits / len(facts)


CITATION_RE = re.compile(r"\[(S\d+)\]")


def citation_present(answer: str) -> float:
    return 1.0 if CITATION_RE.search(answer) else 0.0


def citation_validity(answer: str, citations: list[dict]) -> float:
    """Fraction of `[Sn]` markers in the answer that resolve to a real source.

    `citation_present` only checks that *some* marker exists. This checks that
    every marker is backed by a citation the API actually returned, which is what
    "source-grounded" is supposed to mean.
    """
    labels = set(CITATION_RE.findall(answer))
    if not labels:
        return 0.0
    available = {citation["label"] for citation in citations}
    return len(labels & available) / len(labels)


def citation_precision(answer: str, citations: list[dict]) -> float:
    """Fraction of returned citations that the answer actually references."""
    if not citations:
        return 0.0
    labels = set(CITATION_RE.findall(answer))
    referenced = sum(1 for citation in citations if citation["label"] in labels)
    return referenced / len(citations)


def latency_stats(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
    ordered = sorted(samples)
    return {
        "mean": statistics.mean(samples),
        "p50": statistics.median(samples),
        "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "min": ordered[0],
        "max": ordered[-1],
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
