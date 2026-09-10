from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.retrieval.hybrid import HybridRetriever
from eval.metrics import recall_at_k, reciprocal_rank


def load_dataset(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def run(dataset_path: Path, top_k: int, rerank: bool, strategy: str) -> dict:
    rows = load_dataset(dataset_path)
    per_case = []
    async with SessionLocal() as session:
        retriever = HybridRetriever(session)
        for row in rows:
            hits, cached = await retriever.retrieve(row["question"], top_k=top_k, rerank=rerank, strategy=strategy)
            ranked_docs = []
            for hit in hits:
                if hit.filename not in ranked_docs:
                    ranked_docs.append(hit.filename)
            relevant = set(row["gold_docs"])
            per_case.append(
                {
                    "id": row["id"],
                    "question": row["question"],
                    "ranked_docs": ranked_docs,
                    "recall": recall_at_k(ranked_docs, relevant, top_k),
                    "rr": reciprocal_rank(ranked_docs, relevant),
                    "cached": cached,
                }
            )
    n = max(1, len(per_case))
    return {
        "cases": len(per_case),
        "top_k": top_k,
        "rerank": rerank,
        "strategy": strategy,
        "recall_at_k": sum(x["recall"] for x in per_case) / n,
        "mrr": sum(x["rr"] for x in per_case) / n,
        "per_case": per_case,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("eval/dataset.jsonl"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--strategy", choices=["dense", "sparse", "hybrid"], default="hybrid")
    parser.add_argument("--output", type=Path, default=Path(".eval-results/retrieval.json"))
    args = parser.parse_args()
    result = await run(args.dataset, args.top_k, not args.no_rerank, args.strategy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_case"}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
