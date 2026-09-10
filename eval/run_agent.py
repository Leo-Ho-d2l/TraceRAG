from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.services.chat import ChatService
from eval.metrics import citation_present, fact_coverage
from eval.judge import judge_answer


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
            case = {
                "id": row["id"],
                "answer": result.answer,
                "route": result.route,
                "fact_coverage": fact_coverage(result.answer, row.get("answer_facts", [])),
                "citation_present": citation_present(result.answer),
                "tool_calls": len(result.tool_trace),
                "latency_ms": result.latency_ms,
            }
            if use_judge:
                judged = await judge_answer(
                    question=row["question"],
                    expected_facts=row.get("answer_facts", []),
                    answer=result.answer,
                    citations=[c.model_dump(mode="json") for c in result.citations],
                )
                case["judge"] = {
                    "correctness": judged.correctness,
                    "groundedness": judged.groundedness,
                    "citation_quality": judged.citation_quality,
                    "reason": judged.reason,
                }
            per_case.append(case)
    n = max(1, len(per_case))
    return {
        "cases": len(per_case),
        "avg_fact_coverage": sum(x["fact_coverage"] for x in per_case) / n,
        "citation_rate": sum(x["citation_present"] for x in per_case) / n,
        "avg_tool_calls": sum(x["tool_calls"] for x in per_case) / n,
        "avg_latency_ms": sum(x["latency_ms"] for x in per_case) / n,
        "judge_enabled": use_judge,
        "per_case": per_case,
    }


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
    asyncio.run(main())
