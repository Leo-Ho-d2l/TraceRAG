# Evaluation

TraceRAG ships with a 30-question synthetic enterprise benchmark over the AcmeCloud demo corpus.
The benchmark is intentionally small enough to inspect manually and large enough to expose retrieval and routing regressions.

## Retrieval metrics

Run:

```bash
python -m eval.run_retrieval --dataset eval/dataset.jsonl --top-k 5
python -m eval.run_retrieval --dataset eval/dataset.jsonl --top-k 5 --no-rerank
```

The script reports Recall@K and MRR at the document level and saves every ranked result to `.eval-results/`.
For resume use, do not quote metrics until they have been run on your final corpus and configuration.

## Agent metrics

With a real `LLM_BACKEND=openai_compatible` configuration:

```bash
python -m eval.run_agent --dataset eval/dataset.jsonl
```

The initial deterministic metrics are fact coverage, citation rate, tool-call count and latency. Add an LLM-as-a-Judge only after manually reviewing a sample; a judge is another model and should not be treated as ground truth.
