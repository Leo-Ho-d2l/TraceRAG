# TraceRAG benchmark — final

Generated: 2026-09-10T11:18:35.185477+00:00

## Environment

- `python`: 3.12.14
- `platform`: Windows-11-10.0.26200-SP0
- `llm_backend`: openai_compatible
- `llm_model`: deepseek-flash
- `llm_temperature`: 0.0
- `embedding_model`: BAAI/bge-small-en-v1.5
- `embedding_dim`: 384
- `rerank_model`: Xenova/ms-marco-MiniLM-L-6-v2
- `chunk_target_chars`: 1400
- `chunk_overlap_chars`: 180
- `dense_k`: 20
- `sparse_k`: 20
- `rerank_candidates`: 6
- `default_top_k`: 6
- `rrf_k`: 60
- `max_agent_steps`: 5

## Retrieval ablation (Recall@5, MRR, latency)

| strategy | rerank | Recall@K | Precision@K | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| dense | False | 0.9667 | 0.2667 | 0.9667 | 52.1 | 101.1 |
| sparse | False | 1.0000 | 0.2800 | 0.9167 | 4.2 | 7.1 |
| hybrid | False | 0.9833 | 0.2733 | 0.9833 | 67.0 | 105.0 |
| hybrid | True | 0.9833 | 0.2733 | 0.9833 | 329.0 | 437.0 |

## Agent benchmark

- cases: 30
- LLM backend: `openai_compatible` / `deepseek-flash` (temperature 0.0)
- real LLM: True
- avg expected-fact coverage: 0.9711
- citation rate: 1.0000
- avg citation validity: 1.0000
- avg citation precision: 1.0000
- avg tool calls: 1.03
- avg agent steps: 0.83
- latency p50: 3114 ms, p95: 10491 ms
- judge correctness: 0.978
- judge groundedness: 0.988
- judge citation quality: 0.997
