# TraceRAG

**Production-oriented Agentic RAG reference project with hybrid retrieval, cross-encoder reranking, tool use, citations, evaluation, async ingestion, caching and tracing.**

TraceRAG is intentionally smaller than full AI platforms such as Onyx or RAGFlow. Its goal is to keep the architecture realistic enough for an AI application / Agent engineering portfolio while remaining small enough for one engineer to understand end to end.

## What it demonstrates

- FastAPI service with versioned REST endpoints and an embedded demo UI.
- Async document ingestion for PDF, Markdown, HTML and text.
- PostgreSQL + pgvector dense retrieval with an HNSW index.
- PostgreSQL lexical retrieval + Reciprocal Rank Fusion (RRF).
- Local FastEmbed embeddings and cross-encoder reranking.
- LangGraph orchestration for routing, iterative research and bounded tool execution.
- Tool argument validation, max-step termination and evidence de-duplication.
- Source-grounded answers with validated `[S1]`-style citations.
- Redis versioned retrieval cache with graceful cache failure.
- Persistent conversation history in PostgreSQL.
- Celery + Redis worker mode for ingestion; inline mode for simpler development.
- OpenTelemetry spans for API, retrieval, ingestion and agent nodes.
- A 30-question benchmark with retrieval, citation, task and optional LLM-judge metrics.
- Docker Compose, Alembic migrations, tests and GitHub Actions CI.

## Architecture

```mermaid
flowchart LR
    U[Browser / API client] --> API[FastAPI]
    API --> PG[(PostgreSQL + pgvector)]
    API --> REDIS[(Redis)]
    API --> AGENT[LangGraph Agent]
    API --> Q[Celery queue]
    Q --> WORKER[Ingestion worker]
    WORKER --> PARSE[Parse + section-aware chunk]
    PARSE --> EMB[FastEmbed]
    EMB --> PG

    AGENT --> ROUTE{Query route}
    ROUTE -->|one-hop| RET[Hybrid Retriever]
    ROUTE -->|multi-step| TOOLS[Research tools]
    TOOLS --> RET
    TOOLS --> PG
    RET --> DENSE[pgvector HNSW]
    RET --> SPARSE[Postgres lexical search]
    DENSE --> RRF[RRF fusion]
    SPARSE --> RRF
    RRF --> RR[Cross-encoder reranker]
    RR --> AGENT
    AGENT --> LLM[OpenAI-compatible chat model]
    AGENT --> CITE[Citation validation]
    CITE --> U
```

The data plane and online serving path are deliberately separated: document parsing and embedding can run in a worker, while retrieval and chat remain latency-sensitive online operations.

## Repository layout

```text
TraceRAG/
├── app/
│   ├── agent/          # LangGraph state, prompts, tools, graph
│   ├── api/            # REST routes and dependencies
│   ├── core/           # settings, auth, JSON logging
│   ├── db/             # SQLAlchemy models and async sessions
│   ├── ingestion/      # parsers, chunker, ingestion service
│   ├── llm/            # OpenAI-compatible + mock chat clients
│   ├── observability/  # OpenTelemetry setup
│   ├── retrieval/      # embeddings, lexical+dense retrieval, RRF, reranking
│   ├── schemas/        # Pydantic API models
│   ├── services/       # chat, upload and cache services
│   └── web/            # zero-framework demo UI
├── alembic/            # database migrations
├── eval/               # 30-case retrieval/agent benchmark
├── sample_data/        # fictional AcmeCloud enterprise corpus
├── scripts/            # seed and CLI demo scripts
├── tests/              # unit + API schema smoke tests
└── docs/               # architecture and resume-evidence notes
```

## Quick start with Docker

Requirements: Docker + Docker Compose. The first run downloads the local embedding and reranker models.

```bash
cp .env.example .env
# For real semantic answers, edit .env and set:
# LLM_BACKEND=openai_compatible
# LLM_BASE_URL=...
# LLM_API_KEY=...
# LLM_MODEL=...

docker compose up --build
```

Open `http://localhost:8000/` for the demo UI and `http://localhost:8000/docs` for OpenAPI docs.

Seed the included fictional enterprise corpus:

```bash
docker compose exec api python scripts/seed_demo.py
```

Then ask:

```bash
docker compose exec api python scripts/ask.py \
  "Compare Business and Enterprise audit-log retention and observability." --mode research
```

### Mock mode vs real LLM mode

`LLM_BACKEND=mock` exists only to exercise the service and tool loop without an API key. It does **not** produce meaningful semantic benchmark results.

For portfolio evaluation, use a chat model endpoint that implements OpenAI-compatible `/chat/completions` and tool calling, then set `LLM_BACKEND=openai_compatible`.

## Local development without Celery

When Postgres and Redis are available locally, set:

```env
DATABASE_URL=postgresql+psycopg://tracerag:tracerag@localhost:5432/tracerag
REDIS_URL=redis://localhost:6379/0
INGESTION_MODE=inline
```

Then:

```bash
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

## Retrieval pipeline

TraceRAG exposes three retrieval strategies so the final project can show a real ablation rather than a single unexplained score:

```text
Dense
  query -> BGE query embedding -> pgvector cosine search

Sparse
  query -> PostgreSQL lexical query -> ts_rank_cd

Hybrid
  Dense top-N + Sparse top-N -> RRF -> optional cross-encoder reranker
```

Default local models:

- Embedding: `BAAI/bge-small-en-v1.5`, 384 dimensions.
- Reranker: `Xenova/ms-marco-MiniLM-L-6-v2` through FastEmbed.

The vector dimension is part of the database schema. If the embedding model is changed to one with a different dimension, update `EMBEDDING_DIM` before creating/migrating the database.

### Retrieval debug endpoint

```bash
curl -X POST http://localhost:8000/v1/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query":"Enterprise audit log retention",
    "top_k":5,
    "strategy":"hybrid",
    "rerank":true
  }'
```

The response exposes dense, sparse, RRF and reranker scores. This is deliberate: during project interviews you should be able to show where a ranking improvement came from.

## Agent design

TraceRAG does not use a generic unrestricted agent loop. It uses a bounded LangGraph state machine:

```mermaid
flowchart TD
    START --> ROUTER
    ROUTER -->|direct| FINAL
    ROUTER -->|retrieve| RETRIEVE
    RETRIEVE --> FINAL
    ROUTER -->|research| MODEL
    MODEL -->|tool calls| EXECUTE
    EXECUTE --> MODEL
    MODEL -->|answer / max steps| FINAL
    FINAL --> END
```

Research tools:

- `search_documents(query, top_k)` — hybrid retrieval + reranking.
- `read_document_section(document_id, section_title)` — fetch adjacent section context.
- `get_document_metadata(document_id)` — inspect a known document.

Reliability controls include Pydantic tool schemas, bounded agent steps, tool exception capture, evidence de-duplication, citation validation and a forced grounded synthesis if a research answer omits valid citations.

## Ingestion path

```text
Upload -> SHA-256 de-duplication -> queued/processing status
       -> parser -> section-aware chunks -> local embeddings
       -> transactionally replace chunks -> ready
       -> increment Redis corpus version
```

The corpus version is part of retrieval cache keys. New ingestion or deletion therefore invalidates old cached rankings without requiring a Redis key scan.

Supported inputs:

- PDF with extractable text
- Markdown
- HTML
- plain text

Scanned-image OCR is intentionally outside V1. A parser failure marks the document as `failed` and preserves the error for debugging.

## Evaluation

The repository includes a 30-question benchmark over the fictional AcmeCloud corpus. It contains single-hop, comparison and multi-document questions.

### Retrieval ablation

After seeding the corpus:

```bash
python -m eval.run_retrieval --strategy dense --no-rerank
python -m eval.run_retrieval --strategy sparse --no-rerank
python -m eval.run_retrieval --strategy hybrid --no-rerank
python -m eval.run_retrieval --strategy hybrid
# Or run the complete ablation table in one command:
python -m eval.run_ablation
```

Reported metrics:

- document-level Recall@K
- Mean Reciprocal Rank (MRR)
- per-case ranked documents

Results are written under `.eval-results/`. Do not put a retrieval improvement on a resume until you have run these commands with the exact final configuration.

### Agent evaluation

```bash
python -m eval.run_agent
```

The deterministic report includes:

- expected-fact coverage
- citation rate
- tool-call count
- latency

With a real LLM backend, optional LLM-as-a-Judge is available:

```bash
python -m eval.run_agent --judge
```

The judge scores correctness, groundedness and citation quality. Treat those scores as model-assisted evaluation, not ground truth; manually inspect a sample before using them to support a claim.

## Observability

Every important execution path opens OpenTelemetry spans. To export them, set `OTEL_EXPORTER_OTLP_ENDPOINT` to an OTLP HTTP collector. If the variable is blank, TraceRAG still creates local spans without exporting them.

Structured logs are JSON and carry fields such as `document_id`, `node` and latency where available.

## API surface

```text
GET    /health
POST   /v1/documents
GET    /v1/documents
GET    /v1/documents/{id}
DELETE /v1/documents/{id}
POST   /v1/search
POST   /v1/chat
GET    /v1/threads/{thread_id}/messages
```

Set `API_KEY` to require `X-API-Key` on `/v1/*` endpoints. Leaving it blank disables API-key authentication for local development.

## Tests

```bash
pytest
ruff check .
```

The unit suite tests chunking, parsing, deterministic mock embeddings, RRF, routing and citation validation. The integration smoke test verifies the generated OpenAPI surface. Database-backed integration tests are a natural next extension if this repository is deployed in CI with service containers.

## Design choices

**Why PostgreSQL + pgvector rather than a separate vector database?** It keeps metadata, conversations, chunks and vectors transactionally close and makes the project easier to operate. The abstraction is still isolated in `app/retrieval/`, so a vector-store migration does not need to change the Agent API.

**Why local embeddings/reranking?** Retrieval experiments remain reproducible and do not consume LLM API budget. Only answer generation and routing need a chat endpoint.

**Why RRF?** Dense and lexical scores are not naturally on the same scale. Rank fusion avoids brittle score normalization and provides a clean ablation point.

**Why a bounded state machine rather than a free-running agent?** Enterprise applications usually need predictable latency, cost and failure behavior. The graph limits tool calls and keeps the retrieval path explicit.

**Why not multi-agent?** It adds complexity without improving the evidence that this project is meant to demonstrate. The first portfolio version focuses on one well-instrumented agent that can actually be evaluated.

## Portfolio / resume evidence

The code is designed to support claims of this form **after you run the final experiments**:

> Built an Agentic RAG service with FastAPI, LangGraph, PostgreSQL/pgvector and Redis; implemented dense + lexical hybrid retrieval, RRF and cross-encoder reranking, and evaluated retrieval on a self-maintained benchmark.

> Designed a bounded research-agent workflow with validated Tool Calling, multi-step retrieval, persistent chat history and source-grounded citations; tracked task, citation, tool-use and latency metrics.

> Decoupled document ingestion from online serving with Celery/Redis, added SHA-256 de-duplication, corpus-versioned cache invalidation, Docker Compose deployment and OpenTelemetry tracing.

Fill in numerical improvements only from `.eval-results/` produced by your own run. See `docs/resume-evidence.md` for the exact evidence checklist.

## Open-source references used as architectural study material

TraceRAG is an independent small implementation, not a fork. Useful larger systems and libraries to study alongside it include:

- Onyx — enterprise search / Agentic RAG platform: https://github.com/onyx-dot-app/onyx
- RAGFlow — document-centric RAG and Agent workflows: https://github.com/infiniflow/ragflow
- LangGraph — stateful agent orchestration: https://github.com/langchain-ai/langgraph
- pgvector-python — PostgreSQL vector integration and hybrid-search examples: https://github.com/pgvector/pgvector-python
- FastEmbed — local embedding and reranking: https://github.com/qdrant/fastembed

## Non-goals for V1

- model fine-tuning or RLHF
- GPU model serving
- OCR for scanned documents
- multi-agent orchestration
- Kubernetes
- enterprise RBAC / SSO
- document-level ACL filtering

Those are legitimate production concerns, but adding them before the core retrieval/agent benchmark is understood would make this portfolio project harder to learn and harder to defend in an interview.
