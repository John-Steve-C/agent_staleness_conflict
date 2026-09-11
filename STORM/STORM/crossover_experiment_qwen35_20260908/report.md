# Qwen staleness-strategy crossover experiment

Model: `qwen3.5-35b-a3b`

Design: 6 paired scenario families × 8 staleness levels × 8 strategies × 3 seeds = 1152 continuations.

## Success curves

Each cell contains scenario families × seeds observations. Success requires the correct
coordination action and, for `adapt`, a syntactically valid revision satisfying the
fixture checks.

| k | P0 | P1 | P2 | P3 | P4 | P5 | P1-pad | Adaptive | P3−P1 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 33% | 100% | 83% | 100% | 78% | 100% | 100% | 100% | +0% |
| 2 | 33% | 100% | 83% | 100% | 89% | 100% | 100% | 100% | +0% |
| 3 | 33% | 100% | 83% | 100% | 72% | 100% | 100% | 100% | +0% |
| 4 | 0% | 83% | 83% | 100% | 83% | 100% | 83% | 100% | +17% |
| 5 | 0% | 83% | 83% | 100% | 72% | 100% | 83% | 100% | +17% |
| 6 | 0% | 67% | 83% | 100% | 83% | 100% | 67% | 100% | +33% |
| 7 | 0% | 67% | 83% | 100% | 83% | 100% | 61% | 100% | +33% |
| 8 | 0% | 67% | 83% | 100% | 78% | 100% | 61% | 100% | +33% |

## Overall strategy performance

| Strategy | Success | Mean payload tokens | Mean total model tokens |
|---|---:|---:|---:|
| P0 | 12.5% | 6.0 | 441.8 |
| P1 | 83.3% | 75.3 | 522.5 |
| P2 | 83.3% | 86.5 | 527.5 |
| P3 | 100.0% | 108.4 | 541.7 |
| P4 | 79.9% | 115.8 | 567.0 |
| P5 | 100.0% | 89.0 | 528.5 |
| P1-pad | 81.9% | 108.4 | 551.1 |
| adaptive | 100.0% | 84.1 | 522.5 |

## Estimated crossover

- First consistently positive P3−P1 level: 4.
- First consistently positive P5−P1 level: 4.
- First P3−P1 bootstrap interval fully above zero: 6.
- First P5−P1 bootstrap interval fully above zero: 6.
- Best exploratory P1→P3 threshold: k=4 (100.0% success, 96.6 mean payload tokens).
- Best exploratory P1→P5 threshold: k=4 (100.0% success, 84.1 mean payload tokens).

The threshold sweep maximizes observed success and breaks ties using lower payload
cost. It is exploratory and fitted on the same controlled corpus; it is not a
held-out deployment threshold.

## Validity notes

- Invalid or unparsable model responses: 19.
- P5 is an oracle directive in this experiment: the fixture supplies its correct route.
- Winner reasoning is constructed to expose the intended coordination evidence.
- This paired controlled study improves on the four-case pilot, but it is still not
  a natural-refusal Commit0 corpus or an end-to-end STORM pass-rate experiment.
- Bootstrap intervals in `paired_advantage.csv` resample paired scenario/seed outcomes
  within each k; they quantify this corpus only.

## Artifacts

- `config.json`: model and experimental design
- `run_command.sh`: complete rerun command
- `episodes.jsonl`: 48 replayable paired episodes
- `replay_results.csv`: all model-level outcomes
- `by_k_strategy.csv`: success and token curves
- `paired_advantage.csv`: paired strategy-minus-P1 effects with bootstrap intervals
- `threshold_sweep.csv`: P1→P3/P5 candidate thresholds
- `model_responses.jsonl`: raw requests, responses, and parsed decisions
