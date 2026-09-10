# Post-build learning map

This file is intentionally deferred until after the project exists. The suggested teaching order maps directly to the codebase:

1. **System data flow** — upload → chunks → retrieval → evidence → answer.
2. **Backend foundation** — FastAPI, async SQLAlchemy, PostgreSQL, Redis, Celery, Docker.
3. **RAG mechanics** — embeddings, cosine retrieval, lexical retrieval, RRF and cross-encoder reranking.
4. **Agent mechanics** — LangGraph state, routing, tool schemas, tool loop, termination.
5. **Reliability** — validation, retries, failure states, cache invalidation and citations.
6. **Evaluation** — benchmark construction, Recall@K, MRR, fact coverage, LLM-as-a-Judge limitations.
7. **Interview depth** — tradeoffs, alternatives, bottlenecks and production extensions.

The teaching version should use this repository's actual functions and experiment reports rather than generic framework tutorials.
