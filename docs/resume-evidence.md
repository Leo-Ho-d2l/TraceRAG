# Resume evidence checklist

Do not treat a library name as a resume claim. Every claim below has a concrete
artifact that can be opened during interview preparation. Numbers quoted in the
README come from `artifacts/benchmark/baseline.json` and
`artifacts/benchmark/final.json` — the raw per-case records, not a summary typed
by hand.

| Potential claim | Code | Measured evidence |
|---|---|---|
| Hybrid RAG | `app/retrieval/hybrid.py`, `fusion.py` | 4-way ablation in `artifacts/benchmark/*_retrieval.csv` |
| Cross-encoder reranking | `app/retrieval/reranker.py` | hybrid vs hybrid+rerank delta; rerank p50 latency |
| pgvector HNSW | `alembic/versions/0001_init.py`, `Chunk.embedding` | dense p50/p95 from the ablation |
| PostgreSQL lexical search | `_lexical_tsquery` in `hybrid.py` | sparse p50 3.5 ms; the dead-branch fix in `DEBUG_REPORT.md` |
| Section-aware ingestion | `parser.py`, `chunker.py` | 7 documents → 31 chunks; PDF page numbers preserved |
| Async ingestion | `worker.py`, upload route | SHA-256 de-duplication; failed document keeps its error |
| Agent workflow | `app/agent/graph.py` | route distribution 21 retrieve / 9 research; steps and tool calls per case |
| Tool Calling | `tools.py`, `llm/client.py` | tool-call counts per case; structured argument-validation errors |
| Grounded citations | graph finalizer, `ChatService` | citation validity 1.00 (every `[Sn]` resolves to a real chunk) |
| Redis caching | `services/cache.py` | cold/warm and corpus-version invalidation tests; graceful Redis outage |
| Observability | `observability/tracing.py` | OTLP spans on API, retrieval, ingestion and agent nodes |
| Evaluation | `eval/` | `artifacts/benchmark/` committed with JSON + CSV + summary |

## Metrics to freeze before resume submission

Run the final configuration at least twice and store the exact config with the
results; `artifacts/benchmark/*.json` records the model names, temperature,
chunking parameters, `top_k` values and RRF constant for each run.

1. Dense-only Recall@5 and MRR.
2. Sparse-only Recall@5 and MRR.
3. Hybrid without reranker Recall@5 and MRR.
4. Hybrid + reranker Recall@5 and MRR, and the rerank latency cost.
5. Agent expected-fact coverage, citation rate/validity and judge scores.
6. For research cases: average tool calls and p50/p95 latency.

## Claims that are deliberately *not* made

- No claim that reranking improves document-level MRR on this corpus: measured, it
  does not (see `DEBUG_REPORT.md`). It is kept because it is part of the
  architecture and is expected to matter on a larger corpus.
- No claim based on the mock LLM. Mock mode only proves the code paths execute.
- No claim of improvement without a same-dataset, same-model before/after pair.
