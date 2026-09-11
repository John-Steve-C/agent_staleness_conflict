# Qwen staleness-strategy crossover experiment

Model: `qwen3.5-35b-a3b`

Design: 6 paired scenario families × 8 staleness levels × 9 strategies × 3 seeds = 1296 continuations.

## Success curves

Each cell contains scenario families × seeds observations. Success requires the correct
coordination action and, for `adapt`, a syntactically valid revision satisfying the
fixture checks.

| k | P0 | P1 | P2 | P3 | P4 | P5 predicted | P5 oracle | P1-pad | Adaptive | P3−P1 | P5−P1 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 33% | 100% | 83% | 100% | 83% | 83% | 100% | 100% | 100% | +0% | -17% |
| 2 | 33% | 100% | 83% | 100% | 89% | 67% | 100% | 100% | 94% | +0% | -33% |
| 3 | 33% | 100% | 78% | 100% | 72% | 67% | 100% | 100% | 100% | +0% | -33% |
| 4 | 0% | 83% | 83% | 100% | 83% | 67% | 100% | 83% | 67% | +17% | -17% |
| 5 | 0% | 83% | 83% | 100% | 72% | 83% | 100% | 83% | 83% | +17% | +0% |
| 6 | 0% | 67% | 83% | 100% | 78% | 100% | 100% | 67% | 100% | +33% | +33% |
| 7 | 0% | 67% | 83% | 100% | 78% | 83% | 100% | 61% | 83% | +33% | +17% |
| 8 | 0% | 67% | 83% | 100% | 78% | 100% | 100% | 61% | 100% | +33% | +33% |

## Overall strategy performance

| Strategy | Success | Action accuracy | Policy accuracy | Payload tokens | Recovery tokens | Policy tokens | End-to-end tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| P0 | 12.5% | 47.9% | — | 6.0 | 433.7 | 0.0 | 433.7 |
| P1 | 83.3% | 83.3% | — | 75.3 | 523.8 | 0.0 | 523.8 |
| P2 | 82.6% | 84.7% | — | 86.5 | 523.5 | 0.0 | 523.5 |
| P3 | 100.0% | 100.0% | — | 108.4 | 542.1 | 0.0 | 542.1 |
| P4 | 79.2% | 80.6% | — | 115.8 | 568.3 | 0.0 | 568.3 |
| P5 | 81.2% | 81.2% | 83.3% | 104.2 | 540.7 | 422.9 | 963.6 |
| P5-oracle | 100.0% | 100.0% | — | 90.0 | 526.5 | 0.0 | 526.5 |
| P1-pad | 81.9% | 81.9% | — | 108.4 | 552.2 | 0.0 | 552.2 |
| adaptive | 91.0% | 91.7% | 90.0% | 92.9 | 530.0 | 266.5 | 796.4 |

## P5 interpretation

Policy-predicted P5 achieved 81.2% success, versus 100.0% for P3 and 100.0% for
P5-oracle. The oracle result shows that a compact direction can carry enough
recovery information; the deployable P5 gap is primarily a routing-policy bottleneck.

The router was correct on 65.2% of adapt cases, 100.0% of abandon cases, and 100.0%
of escalate cases. It over-routed compatible low-staleness work to terminal actions,
but identified every abandon/escalate case in this corpus.

## Estimated crossover

- First consistently positive P3−P1 level: 4.
- First consistently positive P5−P1 level: 6.
- First P3−P1 bootstrap interval fully above zero: 6.
- First P5−P1 bootstrap interval fully above zero: 6.
- Best exploratory P1→P3 threshold: k=4 (100.0% success, 96.6 mean payload tokens).
- Best exploratory P1→P5 threshold: k=6 (93.8% success, 85.6 mean payload tokens).

The threshold sweep maximizes observed success and breaks ties using lower payload
cost. It is exploratory and fitted on the same controlled corpus; it is not a
held-out deployment threshold.

## Routing policy

P5 is generated in two stages. A frozen Qwen policy first predicts a route from
only the losing task, the base/proposed/current files, the diff, and observed k.
The recovery continuation then receives P1 plus that predicted route and hint.
`correct_action`, winner intent, and winner reasoning are withheld from the router.

The recovery agent followed the predicted route in 97.9% of P5 continuations.
Recovery succeeded in 97.5% when the route was correct and 0.0% when it was wrong.

| Ground-truth group | n | Router accuracy |
|---|---:|---:|
| overall | 48 | 83.3% |
| adapt | 23 | 65.2% |
| abandon | 17 | 100.0% |
| escalate | 8 | 100.0% |

## Validity notes

- Invalid or unparsable model responses: 13.
- Invalid or unparsable policy responses: 0.
- P5 is policy-predicted; P5-oracle is retained only as an explicit upper bound.
- End-to-end P5 tokens include the extra routing call. P3's winner reasoning was
  already present in the fixture, so its original generation cost is not measured.
- Winner reasoning is constructed to expose the intended coordination evidence.
- Correct actions switch at fixture-specific k values, so action mix and staleness
  are coupled. The observed crossover is a mechanism demonstration, not a causal
  estimate from natural conflicts.
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
- `policy_accuracy.csv`: router accuracy and action distribution
- `policy_responses.jsonl`: raw policy requests, responses, and predictions
- `model_responses.jsonl`: raw requests, responses, and parsed decisions
