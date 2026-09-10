from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import settings


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic no-network embedding used by tests and smoke runs."""

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = text.lower().split()
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dim
            sign = 1.0 if digest[8] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class FastEmbedProvider(EmbeddingProvider):
    def __init__(self, model_name: str, expected_dim: int) -> None:
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model_name=model_name)
        self.expected_dim = expected_dim
        probe = list(self.model.query_embed("dimension probe"))[0]
        if len(probe) != expected_dim:
            raise ValueError(
                f"embedding model {model_name} emits {len(probe)} dims; "
                f"EMBEDDING_DIM is {expected_dim}"
            )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [embedding.tolist() for embedding in self.model.passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return list(self.model.query_embed(text))[0].tolist()


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingProvider:
    if settings.embedding_backend == "hash":
        return HashEmbeddingProvider(settings.embedding_dim)
    return FastEmbedProvider(settings.embedding_model, settings.embedding_dim)
