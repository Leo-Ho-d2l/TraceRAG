"""Run the full benchmark and write reproducible raw artifacts.

    python -m eval.run_benchmark --phase baseline
    python -m eval.run_benchmark --phase final --judge

Writes under artifacts/benchmark/:
    <phase>.json          every per-case record and the aggregate metrics
    <phase>_retrieval.csv retrieval ablation table
    <phase>_agent.csv     per-question agent results
    <phase>_summary.md    human-readable summary

`artifacts/` is committed, unlike `.eval-results/`, so the numbers quoted in the
README can be traced back to a raw run.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
from pathlib import Path

from app.core.config import settings

from app.core.event_loop import run_async

ARTIFACT_DIR = Path("artifacts/benchmark")

RETRIEVAL_CONFIGS = [
    ("dense", False),
    ("sparse", False),
    ("hybrid", False),
    ("hybrid", True),
]


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def environment() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "llm_backend": settings.llm_backend,
        "llm_model": settings.llm_model if settings.llm_backend != "mock" else "mock",
        "llm_temperature": settings.llm_temperature,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "rerank_model": settings.rerank_model if settings.rerank_backend != "none" else "none",
        "chunk_target_chars": settings.chunk_target_chars,
        "chunk_overlap_chars": settings.chunk_overlap_chars,
        "dense_k": settings.dense_k,
        "sparse_k": settings.sparse_k,
        "rerank_candidates": settings.rerank_candidates,
        "default_top_k": settings.default_top_k,
        "rrf_k": settings.rrf_k,
        "max_agent_steps": settings.max_agent_steps,
    }


async def run_retrieval_ablation(dataset: Path, top_k: int) -> list[dict]:
    from eval.run_retrieval import run as run_retrieval

    results = []
    for strategy, rerank in RETRIEVAL_CONFIGS:
        result = await run_retrieval(dataset, top_k, rerank, strategy, use_cache=False)
        results.append(result)
        print(
            f"  {strategy:<7} rerank={str(rerank):<5} "
            f"recall@{top_k}={result['recall_at_k']:.4f} "
            f"mrr={result['mrr']:.4f} "
            f"p50={result['latency_ms']['p50']:.1f}ms"
        )
    return results


def write_summary(path: Path, payload: dict) -> None:
    lines = [f"# TraceRAG benchmark — {payload['phase']}", ""]
    lines.append(f"Generated: {payload['generated_at']}")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    for key, value in payload["environment"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")

    if payload.get("retrieval"):
        lines.append(f"## Retrieval ablation (Recall@{payload['top_k']}, MRR, latency)")
        lines.append("")
        lines.append("| strategy | rerank | Recall@K | Precision@K | MRR | p50 ms | p95 ms |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in payload["retrieval"]:
            lines.append(
                f"| {row['strategy']} | {row['rerank']} | {row['recall_at_k']:.4f} | "
                f"{row['precision_at_k']:.4f} | {row['mrr']:.4f} | "
                f"{row['latency_ms']['p50']:.1f} | {row['latency_ms']['p95']:.1f} |"
            )
        lines.append("")

    agent = payload.get("agent")
    if agent:
        lines.append("## Agent benchmark")
        lines.append("")
        lines.append(f"- cases: {agent['cases']}")
        lines.append(f"- LLM backend: `{agent['llm_backend']}` / `{agent['llm_model']}` (temperature {agent['temperature']})")
        lines.append(f"- real LLM: {agent['is_real_llm']}")
        lines.append(f"- avg expected-fact coverage: {agent['avg_fact_coverage']:.4f}")
        lines.append(f"- citation rate: {agent['citation_rate']:.4f}")
        lines.append(f"- avg citation validity: {agent['avg_citation_validity']:.4f}")
        lines.append(f"- avg citation precision: {agent['avg_citation_precision']:.4f}")
        lines.append(f"- avg tool calls: {agent['avg_tool_calls']:.2f}")
        lines.append(f"- avg agent steps: {agent['avg_steps']:.2f}")
        lines.append(f"- latency p50: {agent['latency_ms']['p50']:.0f} ms, p95: {agent['latency_ms']['p95']:.0f} ms")
        if agent.get("judge_enabled"):
            lines.append(f"- judge correctness: {agent.get('judge_correctness', 0):.3f}")
            lines.append(f"- judge groundedness: {agent.get('judge_groundedness', 0):.3f}")
            lines.append(f"- judge citation quality: {agent.get('judge_citation_quality', 0):.3f}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="baseline", help="label for the artifact files")
    parser.add_argument("--dataset", type=Path, default=Path("eval/dataset.jsonl"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--skip-agent", action="store_true")
    args = parser.parse_args()

    import datetime as _dt

    payload: dict = {
        "phase": args.phase,
        "generated_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "top_k": args.top_k,
        "dataset": str(args.dataset),
        "environment": environment(),
    }

    print(f"[{args.phase}] retrieval ablation")
    retrieval = await run_retrieval_ablation(args.dataset, args.top_k)
    payload["retrieval"] = retrieval

    _write_csv(
        ARTIFACT_DIR / f"{args.phase}_retrieval.csv",
        [
            {
                "strategy": row["strategy"],
                "rerank": row["rerank"],
                "top_k": row["top_k"],
                "recall_at_k": round(row["recall_at_k"], 6),
                "precision_at_k": round(row["precision_at_k"], 6),
                "mrr": round(row["mrr"], 6),
                "latency_p50_ms": round(row["latency_ms"]["p50"], 3),
                "latency_mean_ms": round(row["latency_ms"]["mean"], 3),
                "latency_p95_ms": round(row["latency_ms"]["p95"], 3),
            }
            for row in retrieval
        ],
        [
            "strategy",
            "rerank",
            "top_k",
            "recall_at_k",
            "precision_at_k",
            "mrr",
            "latency_p50_ms",
            "latency_mean_ms",
            "latency_p95_ms",
        ],
    )

    if not args.skip_agent:
        from eval.run_agent import run as run_agent

        print(f"[{args.phase}] agent benchmark (backend={settings.llm_backend})")
        agent = await run_agent(args.dataset, None, args.judge)
        payload["agent"] = agent
        _write_csv(
            ARTIFACT_DIR / f"{args.phase}_agent.csv",
            [
                {
                    "id": case["id"],
                    "type": case["type"],
                    "route": case["route"],
                    "fact_coverage": round(case["fact_coverage"], 4),
                    "citation_present": case["citation_present"],
                    "citation_validity": round(case["citation_validity"], 4),
                    "citation_precision": round(case["citation_precision"], 4),
                    "citation_count": case["citation_count"],
                    "tool_calls": case["tool_calls"],
                    "steps": case["steps"],
                    "latency_ms": case["latency_ms"],
                    "cited_docs": "|".join(case["cited_docs"]),
                }
                for case in agent["per_case"]
            ],
            [
                "id",
                "type",
                "route",
                "fact_coverage",
                "citation_present",
                "citation_validity",
                "citation_precision",
                "citation_count",
                "tool_calls",
                "steps",
                "latency_ms",
                "cited_docs",
            ],
        )
        print(
            f"  fact_coverage={agent['avg_fact_coverage']:.4f} "
            f"citation_rate={agent['citation_rate']:.4f} "
            f"citation_validity={agent['avg_citation_validity']:.4f} "
            f"tools={agent['avg_tool_calls']:.2f} "
            f"p50={agent['latency_ms']['p50']:.0f}ms"
        )
        if args.judge:
            print(
                f"  judge correctness={agent.get('judge_correctness', 0):.3f} "
                f"groundedness={agent.get('judge_groundedness', 0):.3f} "
                f"citation_quality={agent.get('judge_citation_quality', 0):.3f}"
            )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / f"{args.phase}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_summary(ARTIFACT_DIR / f"{args.phase}_summary.md", payload)
    print(f"wrote artifacts to {ARTIFACT_DIR}/{args.phase}.json")


if __name__ == "__main__":
    run_async(main())
