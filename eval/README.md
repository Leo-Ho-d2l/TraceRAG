# Evaluation

TraceRAG ships with a 30-question benchmark over the AcmeCloud demo corpus. It is
small enough to inspect by hand and large enough to expose retrieval and routing
regressions. The questions are single-hop, comparison and multi-document.

The benchmark is **not** run in mock mode for any claim made in the README. A
mock run only proves the code paths execute.

## Run everything

```bash
python -m eval.run_benchmark --phase baseline --judge
python -m eval.run_benchmark --phase final --judge
```

This writes, under `artifacts/benchmark/` (committed, so the numbers in the
README can be traced to a raw run):

| File | Contents |
|---|---|
| `<phase>.json` | environment, aggregate metrics and every per-case record |
| `<phase>_retrieval.csv` | the dense/sparse/hybrid/hybrid+rerank ablation table |
| `<phase>_agent.csv` | per-question route, fact coverage, citation metrics, latency |
| `<phase>_summary.md` | human-readable summary |

`.eval-results/` (git-ignored) is still used by the individual runners below when
you want a quick single-configuration run.

## Retrieval ablation

```bash
python -m eval.run_retrieval --strategy dense  --no-rerank
python -m eval.run_retrieval --strategy sparse --no-rerank
python -m eval.run_retrieval --strategy hybrid --no-rerank
python -m eval.run_retrieval --strategy hybrid
python -m eval.run_ablation          # all four in one table
```

Metrics are document-level Recall@K, Precision@K, MRR and latency percentiles.
Latency is measured **with the retrieval cache disabled** (the default here):
the cache key does not change between two runs of the same configuration, so a
cache-enabled run would report Redis latency instead of retrieval latency, and a
re-run after a code change could serve rankings produced by the older code. Pass
`--use-cache` if you explicitly want the cached path.

On a 7-document corpus, Recall@5 is close to saturated (retrieving 5 of 7
documents is most of the corpus), so **MRR is the more discriminative metric**
here. Read the two together.

## Agent metrics

```bash
python -m eval.run_agent
python -m eval.run_agent --judge
```

Deterministic metrics: expected-fact coverage, citation rate, citation validity
(every `[Sn]` marker resolves to a returned source), citation precision (every
returned source is referenced), tool-call count, agent steps and latency.

With `--judge`, an LLM scores correctness, groundedness and citation quality.
A judge is another model: treat those numbers as model-assisted evaluation, not
ground truth, and read a sample of the answers before quoting them.

## Reproducibility

`artifacts/benchmark/*.json` records the model names, temperature, chunking
parameters, `top_k` values and RRF constant used for that run. Quote metrics only
together with that configuration.
