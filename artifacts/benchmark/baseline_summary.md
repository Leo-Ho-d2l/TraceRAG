# TraceRAG benchmark — baseline

Generated: 2026-09-10T11:09:32.901085+00:00

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
- `rerank_candidates`: 12
- `default_top_k`: 6
- `rrf_k`: 60
- `max_agent_steps`: 5

## Retrieval ablation (Recall@5, MRR, latency)

| strategy | rerank | Recall@K | Precision@K | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| dense | False | 0.9667 | 0.2667 | 0.9667 | 60.8 | 109.3 |
| sparse | False | 1.0000 | 0.2800 | 0.9167 | 3.5 | 6.0 |
| hybrid | False | 0.9833 | 0.2733 | 0.9833 | 58.3 | 103.5 |
| hybrid | True | 0.9722 | 0.2667 | 0.9833 | 417.4 | 512.8 |

## Agent benchmark

- cases: 30
- LLM backend: `openai_compatible` / `deepseek-flash` (temperature 0.0)
- real LLM: True
- avg expected-fact coverage: 0.9656
- citation rate: 1.0000
- avg citation validity: 1.0000
- avg citation precision: 1.0000
- avg tool calls: 1.00
- avg agent steps: 0.87
- latency p50: 2946 ms, p95: 10329 ms
- judge correctness: 1.000
- judge groundedness: 0.990
- judge citation quality: 0.992
