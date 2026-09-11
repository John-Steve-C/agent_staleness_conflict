# Controlled staleness-adaptive communication case studies

> These are deterministic mechanism checks for the framework, not LLM or Commit0
> evidence.
> The recovery backend encodes only which payload families expose enough information to
> choose the fixture's mechanically specified action.

## Primary crossover check

| k | Case | Correct action | P1 success | P3 success | Adaptive selection | Adaptive success |
|---:|---|---|---:|---:|---|---:|
| 1 | k1-local-validation | adapt | 1 | 1 | P1 | 1 |
| 2 | k2-compatible-signature | adapt | 1 | 1 | P1 | 1 |
| 4 | k4-redundant-cache | abandon | 0 | 1 | P5 | 1 |
| 8 | k8-security-invariant | escalate | 0 | 1 | P5 | 1 |

In the two low-staleness adaptation cases (k=1,2), P1 and P3 are tied. In the
high-staleness decision cases (k=4,8), P3 gains 100 percentage points over P1.
The threshold policy selects P1 below k=4 and directive P5 at or above k=4,
matching P3 on all four fixtures with 33.8% fewer mean payload tokens.

## Interpretation

The case studies verify that the framework can express the proposed H2 crossover and
the H5/H6 decision mechanism: content/diff is sufficient for local adaptation, while
intent-bearing or directive payloads disambiguate abandon/escalate decisions. This
does not estimate an effect size. Natural STORM refusals replayed through an LLM
backend are required before accepting or rejecting the research hypotheses.

## Artifacts

- `episodes.jsonl`: replayable refusal snapshots
- `replay_results.csv`: every episode × payload result
- `summary.csv`: aggregate recovery, action, repetition, and token metrics
