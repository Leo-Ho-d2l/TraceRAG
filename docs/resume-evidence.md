# Resume evidence checklist

Do not treat a library name as a resume claim. For every claim below, keep a concrete artifact that can be opened during interview preparation.

| Potential claim | Evidence in repo | Numerical evidence to generate |
|---|---|---|
| Hybrid RAG | `app/retrieval/hybrid.py`, `fusion.py` | dense vs sparse vs hybrid Recall@K / MRR |
| Cross-encoder reranking | `app/retrieval/reranker.py` | hybrid vs hybrid+rerank delta |
| pgvector HNSW | Alembic migration + `Chunk.embedding` | query latency after realistic corpus scaling |
| Section-aware ingestion | `parser.py`, `chunker.py` | document/chunk count, failure cases |
| Async ingestion | `worker.py`, upload route | ingestion duration and API non-blocking behavior |
| Agent workflow | `app/agent/graph.py` | task success, route distribution, avg steps |
| Tool Calling | `tools.py`, `llm/client.py` | tool selection/argument failure cases |
| Grounded citations | graph finalizer + `ChatService` | citation rate / judge citation score |
| Redis caching | `services/cache.py` | warm vs cold P50/P95 if measured |
| Observability | `observability/tracing.py` | traces/screenshots from chosen OTLP backend |
| Evaluation | `eval/` | committed benchmark report from final run |

## Metrics to freeze before resume submission

Run the final configuration at least twice and store the exact config with results.

1. Dense-only Recall@5 and MRR.
2. Hybrid without reranker Recall@5 and MRR.
3. Hybrid + reranker Recall@5 and MRR.
4. Agent citation rate and expected-fact coverage.
5. For research cases: average tool calls and task latency.
6. Optional: warm-cache vs cold-cache P95 latency.

Only write a percentage improvement when both baseline and final values come from the same dataset, corpus and model configuration.
