from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import settings


class Reranker(ABC):
    @abstractmethod
    def score(self, query: str, documents: list[str]) -> list[float]:
        raise NotImplementedError


class NoopReranker(Reranker):
    def score(self, query: str, documents: list[str]) -> list[float]:
        return [0.0 for _ in documents]


class FastEmbedReranker(Reranker):
    def __init__(self, model_name: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model = TextCrossEncoder(model_name=model_name)

    def score(self, query: str, documents: list[str]) -> list[float]:
        return [float(score) for score in self.model.rerank(query, documents)]


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    if settings.rerank_backend == "none":
        return NoopReranker()
    return FastEmbedReranker(settings.rerank_model)
