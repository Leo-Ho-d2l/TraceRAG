import math

from app.retrieval.embeddings import HashEmbeddingProvider


def test_hash_embedding_is_deterministic_and_normalized():
    provider = HashEmbeddingProvider(32)
    a = provider.embed_query("retry with exponential backoff")
    b = provider.embed_query("retry with exponential backoff")
    assert a == b
    assert len(a) == 32
    assert math.isclose(math.sqrt(sum(v * v for v in a)), 1.0, rel_tol=1e-6)
