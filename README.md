# TraceRAG

**An Agentic RAG service: hybrid retrieval (pgvector + PostgreSQL lexical + RRF + cross-encoder reranking), a bounded LangGraph research agent with validated tool calling, and source-grounded citations — evaluated on a self-maintained benchmark.**

TraceRAG is deliberately smaller than platforms such as Onyx or RAGFlow. The
goal is an architecture that is realistic enough to defend in an interview and
small enough for one engineer to understand end to end.

## Key technical highlights

- **Hybrid retrieval** — dense (pgvector HNSW, cosine) fused with PostgreSQL
  full-text search through Reciprocal Rank Fusion, then an optional cross-encoder
  rerank. All four configurations are separately measurable.
- **A bounded research agent** rather than a free-running loop: LangGraph state
  machine, Pydantic-validated tool arguments, a hard step limit, tool-exception
  capture and evidence de-duplication.
- **Source-grounded answers** — every citation is resolved back to the chunk it
  names before it is returned; a `[S9]` with no matching evidence is dropped, and
  a research answer without valid citations is regenerated from evidence.
- **Async ingestion** — SHA-256 de-duplication, section-aware chunking,
  transactional chunk replacement, Celery/Redis worker *or* inline mode.
- **Corpus-versioned retrieval cache** — Redis keys embed a corpus version, so a
  new ingestion invalidates old rankings without a key scan; a Redis outage
  disables caching instead of failing requests.
- **Evaluation as a first-class artifact** — a 30-question benchmark with a
  committed raw run (`artifacts/benchmark/`), not numbers typed into a README.

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

The data plane and the online serving path are separated on purpose: parsing and
embedding can run in a worker while retrieval and chat stay latency-sensitive
online operations.

## Quick start

Requirements: Docker + Docker Compose. The first run downloads the local
embedding and reranker models.

```bash
cp .env.example .env

# Optional: for real answers, point at any OpenAI-compatible endpoint.
#   LLM_BACKEND=openai_compatible
#   LLM_BASE_URL=https://api.deepseek.com/v1
#   LLM_API_KEY=...
#   LLM_MODEL=deepseek-flash
# Leaving LLM_BACKEND=mock exercises the whole service without a key.

docker compose up --build
```

Open `http://localhost:8000/` for the demo UI and `http://localhost:8000/docs`
for OpenAPI. Then index the bundled fictional corpus:

```bash
docker compose exec api python scripts/seed_demo.py     # 7 documents -> 31 chunks
docker compose exec api python scripts/ask.py \
  "Compare Business and Enterprise audit log retention and observability." --mode research
```

### Local development without Docker

```bash
python -m pip install -e ".[dev]"
docker compose up -d postgres redis     # infrastructure only
alembic upgrade head

python -m app.serve                     # http://localhost:8000
```

`app.serve` is the cross-platform entry point. Use it instead of
`uvicorn app.main:app` on Windows: uvicorn 0.36+ hands `asyncio.run` an explicit
loop factory that hardcodes `ProactorEventLoop`, which psycopg's async driver
rejects, and the application never gets a chance to correct it. On Linux and
macOS `uvicorn app.main:app --reload` works as usual. See `DEBUG_REPORT.md`.

Set these in `.env` for local (non-Docker) runs:

```env
DATABASE_URL=postgresql+psycopg://tracerag:tracerag@localhost:5432/tracerag
REDIS_URL=redis://localhost:6379/0
INGESTION_MODE=inline
```

### Mock mode vs real LLM mode

`LLM_BACKEND=mock` exists only to exercise the service and the tool loop without
an API key. It does not produce meaningful semantic benchmark results. For any
number quoted below, a real OpenAI-compatible chat model was used.

## Retrieval pipeline

```text
Dense    query -> BGE query embedding -> pgvector cosine search (HNSW)
Sparse   query -> stopword-filtered OR tsquery -> ts_rank_cd (GIN)
Hybrid   Dense top-N + Sparse top-N -> RRF -> optional cross-encoder rerank
```

The lexical branch is worth a note. `plainto_tsquery` **conjoins** every token,
and the `simple` configuration removes no stopwords, so a natural-language
question only matched a chunk containing *all* of its words — 29 of 30 benchmark
questions returned nothing at all. The query is now a disjunction of the
question's content words, with PostgreSQL's own `english` configuration deciding
what counts as a stopword. In an isolated comparison that took the lexical branch
from recall@5 0.0167 to 0.9833; the shipped configuration measures 1.0000 in the
ablation below. Details and all measurements are in `DEBUG_REPORT.md`.

Default local models:

- Embedding: `BAAI/bge-small-en-v1.5`, 384 dimensions.
- Reranker: `Xenova/ms-marco-MiniLM-L-6-v2`, via FastEmbed.

The vector dimension is part of the schema. If you change the embedding model to
one with a different dimension, update `EMBEDDING_DIM` before migrating.

### Retrieval debug endpoint

```bash
curl -X POST http://localhost:8000/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"Enterprise audit log retention","top_k":5,"strategy":"hybrid","rerank":true}'
```

The response exposes `dense_score`, `sparse_score`, `rrf_score` and
`rerank_score` separately, so a ranking change can be attributed to a specific
stage rather than asserted.

## Agent design

TraceRAG does not use a generic unrestricted agent loop. It uses a bounded
LangGraph state machine:

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
- `read_document_section(document_id, section_title)` — adjacent context from a known section.
- `get_document_metadata(document_id)` — filename, ingestion status, metadata.

Reliability controls: Pydantic tool schemas, bounded agent steps, tool-exception
capture returned to the model as structured errors, evidence de-duplication by
chunk id, citation validation, and a forced grounded synthesis when a research
answer omits valid citations.

## Benchmark

30 questions over the bundled AcmeCloud corpus (7 documents, 31 chunks): single-hop,
comparison and multi-document. Raw results, including every per-case record and
the exact configuration, are committed under `artifacts/benchmark/`.

Reproduce with:

```bash
python -m eval.run_benchmark --phase final --judge
```

### Retrieval ablation

| strategy | rerank | Recall@5 | Precision@5 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| dense | no | 0.9667 | 0.2667 | 0.9667 | 52.1 | 101.1 |
| sparse | no | 1.0000 | 0.2800 | 0.9167 | 4.2 | 7.1 |
| hybrid | no | 0.9833 | 0.2733 | 0.9833 | 67.0 | 105.0 |
| hybrid | yes | 0.9833 | 0.2733 | 0.9833 | 329.0 | 437.0 |

Document-level metrics; latency measured with the retrieval cache disabled. On a
7-document corpus Recall@5 is near saturation — retrieving 5 of 7 documents is
most of the corpus — so **MRR is the more discriminative metric** here.

### Agent benchmark

| metric | value |
|---|---|
| cases | 30 |
| expected-fact coverage | 0.9711 |
| citation rate | 1.0000 |
| citation validity (every `[Sn]` resolves to a returned source) | 1.0000 |
| citation precision (every returned source is referenced) | 1.0000 |
| average tool calls / steps | 1.03 / 0.83 |
| latency p50 / p95 | 3114 ms / 10491 ms |
| LLM-as-a-Judge correctness / groundedness / citation quality | 0.978 / 0.988 / 0.997 |

Route distribution over the 30 questions: 21 `retrieve`, 9 `research`. Research
cases used 2–7 tool calls and had a p50 latency roughly 3× the `retrieve` path.

### One optimization, with its evidence

The baseline ablation had an anomaly: hybrid **with** reranking scored *worse* on
recall than hybrid **without** it (0.9722 vs 0.9833) while costing 7× the latency.
A 12-candidate RRF pool is 39% of a 31-chunk corpus, so the cross-encoder was
being handed marginal candidates it could promote above the gold document.
Sweeping the pool size over the full dataset:

| candidates | recall@5 | MRR@5 | p50 ms |
|---|---|---|---|
| 4 | 0.9833 | 0.9833 | 368 |
| **6** | **0.9833** | **0.9833** | **355** |
| 8 | 0.9722 | 0.9833 | 398 |
| 12 | 0.9722 | 0.9833 | 504 |
| 20 | 0.9722 | 0.9833 | 629 |

`RERANK_CANDIDATES` is therefore 6: **recall@5 0.9722 → 0.9833, MRR unchanged,
rerank p50 417 ms → 329 ms**. Two other hypotheses (indexing section titles in
the lexical vector; trimming research-path evidence) were measured and rejected —
both are written up in `DEBUG_REPORT.md`, including the numbers, because a
negative result you did not measure is just a guess.

The agent metrics did **not** improve: the before/after differences there are
within run-to-run variance of a non-deterministic model and are reported as such,
not claimed as a gain.

## Reliability and safety

- **Bounded execution** — the research loop stops at `MAX_AGENT_STEPS`; a tool
  that keeps failing cannot spin forever.
- **Validated tool arguments** — every call is parsed by a Pydantic model;
  failures come back to the model as `{"error": "invalid tool arguments",
  "details": ...}` instead of raising into the request.
- **No invented citations** — labels in the answer are resolved against the
  evidence actually retrieved for that turn; unresolved labels are dropped.
  Historical `[Sn]` markers are stripped from prior turns so a stale label cannot
  be re-read as a current source.
- **Cache failure is not request failure** — Redis errors are logged and
  retrieval proceeds uncached.
- **Upload limits** — extension allow-list and a size cap enforced while
  streaming, with SHA-256 de-duplication. Scanned-image OCR is out of scope;
  a parser failure marks the document `failed` and preserves the error.

## Project structure

```text
TraceRAG/
├── app/
│   ├── agent/          # LangGraph state, prompts, tools, graph
│   ├── api/            # REST routes and dependencies
│   ├── core/           # settings, auth, JSON logging, event-loop compatibility
│   ├── db/             # SQLAlchemy models and async sessions
│   ├── ingestion/      # parsers, chunker, ingestion service
│   ├── llm/            # OpenAI-compatible + mock chat clients
│   ├── observability/  # OpenTelemetry setup
│   ├── retrieval/      # embeddings, lexical+dense retrieval, RRF, reranking
│   ├── schemas/        # Pydantic API models
│   ├── services/       # chat, upload and cache services
│   └── web/            # zero-framework demo UI
├── alembic/            # database migrations
├── artifacts/benchmark # committed raw benchmark runs
├── eval/               # 30-case retrieval/agent benchmark
├── sample_data/        # fictional AcmeCloud enterprise corpus
├── scripts/            # seed and CLI demo scripts
├── tests/              # unit + database-backed integration tests
└── docs/               # architecture and resume-evidence notes
```

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

Set `API_KEY` to require `X-API-Key` on `/v1/*`. Leaving it blank disables
API-key authentication for local development.

## Tests

```bash
pytest        # 63 tests
ruff check .
```

Unit tests cover chunking, parsing, deterministic embeddings, RRF rank
direction and accumulation, the generated tsquery, routing heuristics and
citation validation. Integration tests run against real PostgreSQL + Redis and
cover every retrieval strategy, agent routing and the bounded tool loop, tool
argument validation, citation-to-chunk resolution, chat history and cache
cold/warm/invalidation behaviour. Tests force `LLM_BACKEND=mock`: a suite whose
result depends on a remote model's routing is neither deterministic nor free.

## Design choices

**Why PostgreSQL + pgvector rather than a separate vector database?** Metadata,
conversations, chunks and vectors stay transactionally close, and the project is
easier to operate. The abstraction is isolated in `app/retrieval/`, so a
vector-store migration would not change the Agent API.

**Why local embeddings and reranking?** Retrieval experiments stay reproducible
and cost nothing to re-run. Only routing and answer generation need a chat
endpoint.

**Why RRF?** Dense and lexical scores are not on the same scale. Rank fusion
avoids brittle score normalization and gives a clean ablation point.

**Why a bounded state machine instead of a free-running agent?** Enterprise
applications need predictable latency, cost and failure behaviour. The graph
limits tool calls and keeps the retrieval path explicit.

**Why not multi-agent?** It adds complexity without improving what this project
is meant to demonstrate.

## Known limitations

- The benchmark corpus is small (7 documents), so document-level Recall@5 is
  close to saturated and the ablation has limited headroom. It is large enough to
  catch regressions, not to rank techniques.
- `fact_coverage` is a substring matcher, so it under-reports answers that
  paraphrase — for example a reference fact `"5 seconds"` does not match an
  answer that says `"5-second connection timeout"`. The LLM judge scores those
  same answers correct. The metric was deliberately **not** loosened; read it
  together with the judge scores.
- The reranker does not improve document-level MRR on a corpus this small. Its
  candidate pool is capped at 6 because a larger pool measurably *hurt*
  (see `DEBUG_REPORT.md`); on a larger corpus that value should be re-tuned.
- Ingestion runs in-process when `INGESTION_MODE=inline`; the Celery path is
  verified but is not the default for local development.

## Non-goals for V1

- model fine-tuning or RLHF
- GPU model serving
- OCR for scanned documents
- multi-agent orchestration
- Kubernetes
- enterprise RBAC / SSO
- document-level ACL filtering

## References used as architectural study material

TraceRAG is an independent implementation, not a fork. Useful larger systems and
libraries to study alongside it:

- Onyx — enterprise search / Agentic RAG platform: https://github.com/onyx-dot-app/onyx
- RAGFlow — document-centric RAG and Agent workflows: https://github.com/infiniflow/ragflow
- LangGraph — stateful agent orchestration: https://github.com/langchain-ai/langgraph
- pgvector-python — PostgreSQL vector integration and hybrid-search examples: https://github.com/pgvector/pgvector-python
- FastEmbed — local embedding and reranking: https://github.com/qdrant/fastembed
