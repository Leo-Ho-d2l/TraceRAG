from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.core.event_loop import run_async
from app.db.session import SessionLocal
from app.services.chat import ChatService
from eval.judge import judge_answer
from eval.metrics import (
    citation_precision,
    citation_present,
    citation_validity,
    fact_coverage,
    latency_stats,
)


def load_dataset(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def run(dataset_path: Path, limit: int | None = None, use_judge: bool = False) -> dict:
    rows = load_dataset(dataset_path)
    if limit:
        rows = rows[:limit]
    per_case = []
    async with SessionLocal() as session:
        service = ChatService(session)
        for row in rows:
            result = await service.answer(
                question=row["question"], thread_id=None, mode="auto", top_k=6
            )
            citations = [c.model_dump(mode="json") for c in result.citations]
            case = {
                "id": row["id"],
                "question": row["question"],
                "type": row.get("type"),
                "answer": result.answer,
                "route": result.route,
                "fact_coverage": fact_coverage(result.answer, row.get("answer_facts", [])),
                "citation_present": citation_present(result.answer),
                "citation_validity": citation_validity(result.answer, citations),
                "citation_precision": citation_precision(result.answer, citations),
                "citation_count": len(citations),
                "cited_docs": [c["filename"] for c in citations],
                "tool_calls": len(result.tool_trace),
                "steps": result.total_steps,
                "latency_ms": result.latency_ms,
            }
            if use_judge:
                judged = await judge_answer(
                    question=row["question"],
                    expected_facts=row.get("answer_facts", []),
                    answer=result.answer,
                    citations=citations,
                )
                case["judge"] = {
                    "correctness": judged.correctness,
                    "groundedness": judged.groundedness,
                    "citation_quality": judged.citation_quality,
                    "reason": judged.reason,
                }
            per_case.append(case)

    def average(key: str) -> float:
        return sum(x[key] for x in per_case) / max(1, len(per_case))

    summary = {
        "cases": len(per_case),
        "llm_backend": settings.llm_backend,
        "llm_model": settings.llm_model if settings.llm_backend != "mock" else "mock",
        "temperature": settings.llm_temperature,
        "is_real_llm": settings.llm_backend != "mock",
        "avg_fact_coverage": average("fact_coverage"),
        "citation_rate": average("citation_present"),
        "avg_citation_validity": average("citation_validity"),
        "avg_citation_precision": average("citation_precision"),
        "avg_tool_calls": average("tool_calls"),
        "avg_steps": average("steps"),
        "latency_ms": latency_stats([x["latency_ms"] for x in per_case]),
        "judge_enabled": use_judge,
        "per_case": per_case,
    }
    if use_judge:
        judged_cases = [x for x in per_case if "judge" in x]
        for key in ("correctness", "groundedness", "citation_quality"):
            summary[f"judge_{key}"] = sum(x["judge"][key] for x in judged_cases) / max(
                1, len(judged_cases)
            )
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("eval/dataset.jsonl"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--judge", action="store_true", help="Enable LLM-as-a-Judge (requires a real LLM backend)")
    parser.add_argument("--output", type=Path, default=Path(".eval-results/agent.json"))
    args = parser.parse_args()
    result = await run(args.dataset, args.limit, args.judge)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_case"}, indent=2))


if __name__ == "__main__":
    run_async(main())
