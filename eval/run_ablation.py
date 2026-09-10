from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from eval.run_retrieval import run


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("eval/dataset.jsonl"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path(".eval-results/ablation.json"))
    args = parser.parse_args()

    configs = [
        ("dense", False),
        ("sparse", False),
        ("hybrid", False),
        ("hybrid", True),
    ]
    rows = []
    for strategy, rerank in configs:
        result = await run(args.dataset, args.top_k, rerank, strategy)
        rows.append(
            {
                "strategy": strategy,
                "rerank": rerank,
                "recall_at_k": result["recall_at_k"],
                "mrr": result["mrr"],
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    print(f"{'strategy':<10} {'rerank':<8} {'recall@k':>10} {'mrr':>10}")
    for row in rows:
        print(
            f"{row['strategy']:<10} {str(row['rerank']):<8} "
            f"{row['recall_at_k']:>10.4f} {row['mrr']:>10.4f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
