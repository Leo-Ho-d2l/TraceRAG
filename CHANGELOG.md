# Changelog

## v1.0.0 — 2026-09-10

First validated public release.

- Fixed clean-database Alembic migration and Windows async database startup.
- Restored the hybrid retrieval path by removing concurrent use of one `AsyncSession`.
- Reworked PostgreSQL lexical retrieval after measuring 29/30 zero-hit queries in the original implementation.
- Added per-event-loop Redis client reuse, corpus-version cache invalidation, and graceful cache fallback.
- Verified Markdown/PDF/HTML/TXT ingestion, Celery worker execution, all retrieval modes, bounded LangGraph routes and citation resolution.
- Added reproducible 30-case retrieval/agent evaluation with committed raw artifacts.
- Tuned the rerank candidate pool from measured bad cases: Recall@5 0.9722 → 0.9833 and p50 417 ms → 329 ms.
- Quality gate at release: 63 tests passing and `ruff check .` clean.

See `DEBUG_REPORT.md` for root causes, rejected hypotheses and exact validation commands.
