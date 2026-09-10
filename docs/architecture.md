# Architecture notes

## 1. Request boundaries

TraceRAG separates three workloads:

1. **Ingestion** is write-heavy, bursty and tolerant of seconds of delay. It may run in Celery workers.
2. **Retrieval** is latency-sensitive and performs dense + lexical candidate generation followed by optional reranking.
3. **Agent execution** is model-latency dominated and bounded by `MAX_AGENT_STEPS`.

This split prevents document parsing and embedding from occupying the API process during normal Docker operation.

## 2. Data model

`documents` stores the upload lifecycle and SHA-256 de-duplication key. `chunks` stores source metadata, generated search vector and pgvector embedding. `chat_threads` and `chat_messages` retain short conversation history independently of LangGraph runtime state.

A chunk is the citation unit. That is why `chunk_id`, document identity, section title and page number remain available all the way through retrieval and final API serialization.

## 3. Retrieval

Dense retrieval uses cosine distance against a pgvector HNSW index. Lexical retrieval uses PostgreSQL full-text rank. The two candidate lists are fused with Reciprocal Rank Fusion:

`RRF(d) = Σ 1 / (k + rank_i(d))`

The default `k=60` reduces sensitivity to one list's top rank. Reranking is performed only on a small fused candidate set because a cross-encoder is more expensive than bi-encoder retrieval.

The `strategy` parameter intentionally preserves dense-only, sparse-only and hybrid modes so retrieval changes can be evaluated rather than assumed to be improvements.

## 4. Cache invalidation

A query cache key contains a monotonically increasing `corpus_version`. Any successful ingestion or deletion increments the version. Old keys can expire naturally; no `SCAN`/bulk delete is required on the request path.

If Redis is unavailable, retrieval continues without cache. Redis is therefore an optimization, not a correctness dependency.

## 5. Agent state

The graph state contains the question, route, bounded step counter, LLM messages, pending tool calls, accumulated evidence and structured tool trace.

The research path follows a model → tools → model loop. All tool arguments pass Pydantic validation before execution. Evidence is de-duplicated by `chunk_id` and assigned stable labels in encounter order.

The finalizer validates that model citation labels exist in evidence. If a research-model final answer lacks valid citations, it runs a grounded synthesis over the accumulated evidence instead of silently attaching a source.

## 6. Failure semantics

- Unsupported or over-size uploads fail before a document row is created.
- Parsing/embedding failure moves a document to `failed` and stores an error message.
- Celery tasks retry failures with backoff, while ingestion itself is idempotent because existing chunks for the document are replaced.
- Redis failures do not fail retrieval.
- Tool errors become structured observations, allowing the model to choose another action.
- Agent execution has a hard max-step bound.

## 7. Security scope

V1 provides optional static API-key authentication, upload extension/size limits, safe filename handling and no execution of uploaded content. It does not claim enterprise RBAC or per-document authorization. A production multi-tenant version must apply authorization filters **inside retrieval**, not only at the API layer.
