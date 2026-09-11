# Qwen staleness-strategy crossover experiment

Model: `qwen3.5-35b-a3b`

Design: 8 paired scenario families × 16 staleness levels × 9 strategies × 3 seeds = 3456 continuations.

## Success curves

Each cell contains scenario families × seeds observations. Success requires the correct
coordination action and, for `adapt`, a syntactically valid revision satisfying the
behavioral validator while preserving every concurrent revision marker.

| k | P0 | P1 | P2 | P3 | P4 | P5 predicted | P5 oracle | P1-pad | Adaptive | P3−P1 | P5−P1 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0% | 83% | 75% | 92% | 75% | 38% | 96% | 88% | 83% | +8% | -46% |
| 2 | 0% | 79% | 75% | 88% | 62% | 38% | 92% | 79% | 79% | +8% | -42% |
| 3 | 0% | 79% | 75% | 79% | 58% | 50% | 92% | 79% | 79% | +0% | -29% |
| 4 | 0% | 75% | 88% | 92% | 54% | 25% | 100% | 83% | 25% | +17% | -50% |
| 5 | 0% | 88% | 88% | 96% | 67% | 62% | 100% | 88% | 62% | +8% | -25% |
| 6 | 0% | 75% | 88% | 79% | 62% | 62% | 100% | 75% | 54% | +4% | -12% |
| 7 | 0% | 75% | 88% | 83% | 67% | 75% | 100% | 75% | 75% | +8% | +0% |
| 8 | 0% | 75% | 88% | 88% | 67% | 88% | 100% | 75% | 88% | +12% | +12% |
| 9 | 0% | 83% | 75% | 83% | 71% | 75% | 100% | 75% | 75% | +0% | -8% |
| 10 | 0% | 88% | 79% | 83% | 79% | 88% | 100% | 79% | 88% | -4% | +0% |
| 11 | 0% | 83% | 88% | 75% | 83% | 75% | 100% | 75% | 75% | -8% | -8% |
| 12 | 0% | 83% | 88% | 79% | 75% | 62% | 100% | 83% | 62% | -4% | -21% |
| 13 | 0% | 83% | 75% | 75% | 88% | 79% | 100% | 83% | 79% | -8% | -4% |
| 14 | 0% | 83% | 75% | 75% | 62% | 54% | 100% | 79% | 54% | -8% | -29% |
| 15 | 0% | 83% | 79% | 79% | 67% | 62% | 100% | 88% | 62% | -4% | -21% |
| 16 | 0% | 79% | 75% | 75% | 67% | 62% | 100% | 75% | 62% | -4% | -17% |

## Overall strategy performance

| Strategy | Success | Action accuracy | Policy accuracy | Payload tokens | Recovery tokens | Policy tokens | End-to-end tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| P0 | 0.0% | 43.0% | — | 6.0 | 426.8 | 0.0 | 426.8 |
| P1 | 81.0% | 85.4% | — | 125.8 | 748.8 | 0.0 | 748.8 |
| P2 | 81.0% | 84.6% | — | 136.8 | 737.2 | 0.0 | 737.2 |
| P3 | 82.6% | 86.2% | — | 144.1 | 765.5 | 0.0 | 765.5 |
| P4 | 69.0% | 73.2% | — | 170.4 | 802.1 | 0.0 | 802.1 |
| P5 | 62.2% | 62.2% | 58.6% | 155.8 | 731.1 | 613.0 | 1344.1 |
| P5-oracle | 98.7% | 100.0% | — | 140.5 | 742.8 | 0.0 | 742.8 |
| P1-pad | 79.9% | 83.6% | — | 144.1 | 777.1 | 0.0 | 777.1 |
| adaptive | 69.0% | 73.7% | 64.4% | 149.7 | 735.2 | 526.0 | 1261.2 |

## P3 leakage-safe result

P3 improved over P1 by +1.6% overall (95% paired bootstrap interval [-2.6%, +5.7%]; episode-clustered randomization p=0.510). This does not establish an overall P3 advantage.

| Staleness band | P3−P1 | 95% bootstrap interval |
|---|---:|---:|
| k1-4 | +8.3% | [+2.1%, +15.6%] |
| k5-8 | +8.3% | [-2.1%, +20.8%] |
| k9-12 | -4.2% | [-9.4%, +0.0%] |
| k13-16 | -6.2% | [-12.5%, -1.0%] |

More payload was not monotonically better: P4 achieved 69.0% success and P1-pad achieved 79.9%, versus 81.0% for P1.

| Correct action | P3−P1 | 95% bootstrap interval |
|---|---:|---:|
| abandon | +0.0% | [+0.0%, +0.0%] |
| adapt | +1.8% | [-2.4%, +6.7%] |
| escalate | +4.2% | [-13.9%, +25.0%] |

Action-stratified contrasts also fail to establish a universal P3 benefit; see `robustness_contrasts.csv` for action-by-k-band reversals.

## P5 interpretation

Policy-predicted P5 achieved 62.2% success, versus 82.6% for P3 and 98.7% for P5-oracle. The oracle arm measures the upper bound from a correct compact direction; its gap from P5 contains routing and directive-adherence errors.

The router was correct on 16.4% of adapt cases, 100.0% of abandon cases, and 70.8% of escalate cases.

## Estimated crossover

- First consistently positive P3−P1 level: not observed.
- First consistently positive P5−P1 level: not observed.
- First P3−P1 bootstrap interval fully above zero: not observed.
- First P5−P1 bootstrap interval fully above zero: not observed.
- Best exploratory P1→P3 threshold: k=1 (82.6% success, 144.1 mean payload tokens).
- Best exploratory P1→P5 threshold: k=17 (81.0% success, 125.8 mean payload tokens).

The threshold sweep maximizes observed success and breaks ties using lower payload
cost. It is exploratory and fitted on the same controlled corpus; it is not a
held-out deployment threshold.

## Routing policy

P5 is generated in two stages. A frozen Qwen policy first predicts a route from
only the losing task, the base/proposed/current files, the diff, and observed k.
The recovery continuation then receives P1 plus that predicted route and hint.
`correct_action`, winner intent, and winner reasoning are withheld from the router.

The recovery agent followed the predicted route in 90.1% of P5 continuations. Recovery succeeded in 94.7% when the route was correct and 16.4% when it was wrong.

| Ground-truth group | n | Router accuracy |
|---|---:|---:|
| overall | 128 | 58.6% |
| adapt | 55 | 16.4% |
| abandon | 49 | 100.0% |
| escalate | 24 | 70.8% |

## Validity notes

- Pre-run P3 leakage audit passed: True.
- Post-run prompt/rescoring audit passed: True.
- Invalid or unparsable model responses: 60.
- Invalid or unparsable policy responses: 1.
- P5 is policy-predicted; P5-oracle is retained only as an explicit upper bound.
- End-to-end P5 tokens include the extra routing call. P3's winner reasoning was already present in the fixture, so its original generation cost is not measured.
- Winner reasoning describes the winning edit without recovery-action words; the pre-run audit enforces this constraint.
- Correct actions switch at fixture-specific k values, so action mix and staleness are coupled. The observed crossover is a mechanism demonstration, not a causal estimate from natural conflicts.
- The corpus contains adapt, abandon, and escalate labels, but no ground-truth queue or serialize episodes.
- This paired controlled study improves on the four-case pilot, but it is still not
  a natural-refusal Commit0 corpus or an end-to-end STORM pass-rate experiment.
- Bootstrap intervals resample episode-level paired effects while retaining all
  seeds inside each episode cluster; they quantify this corpus only.

## Artifacts

- `config.json`: model and experimental design
- `leakage_audit.json`: pre-run directive and evaluator leakage checks
- `implementation_audit.md`: diagnosis of the superseded 100% P3 result
- `postrun_audit.json`: raw-prompt and independent rescoring checks
- `run_command.sh`: complete rerun command
- `episodes.jsonl`: 128 replayable paired episodes
- `replay_results.csv`: all model-level outcomes
- `by_k_strategy.csv`: success and token curves
- `by_action_strategy.csv`: performance stratified by correct action
- `paired_advantage.csv`: paired strategy-minus-P1 effects with bootstrap intervals
- `robustness_contrasts.csv`: overall, k-band, and action-stratified contrasts
- `threshold_sweep.csv`: P1→P3/P5 candidate thresholds
- `policy_accuracy.csv`: router accuracy and action distribution
- `policy_responses.jsonl`: raw policy requests, responses, and predictions
- `model_responses.jsonl`: raw requests, responses, and parsed decisions
- `staleness-curves.html`: interactive P1/P3/P4/P1-pad comparison
