# Local-model refusal-payload case study

Model: `qwen3.5-35b-a3b`

> This is a four-episode, one-seed pilot on controlled code conflicts. It is real model
> inference, but it is not a powered Commit0 experiment and cannot confirm H2 statistically.

## Per-case decisions

| k | Correct | P1 | P3 | P5 | Adaptive (selected) |
|---:|---|---|---|---|---|
| 1 | adapt | adapt ✓ | adapt ✓ | adapt ✓ | adapt ✓ (P1) |
| 2 | adapt | adapt ✓ | adapt ✓ | adapt ✓ | adapt ✓ (P1) |
| 4 | abandon | adapt ✗ | abandon ✓ | abandon ✓ | abandon ✓ (P5) |
| 8 | escalate | adapt ✗ | escalate ✓ | escalate ✓ | escalate ✓ (P5) |

## Primary H2 diagnostic

- P3 − P1 recovery gap at low staleness (k=1,2): +0%
- P3 − P1 recovery gap at high staleness (k=4,8): +100%

A larger high-staleness gap is directionally consistent with H2; an equal or smaller
gap is not. Inspect `model_responses.jsonl` for the decisions and explanations rather
than treating four binary outcomes as an effect-size estimate.

## Secondary diagnostics

- H3 length control: P1-pad success was 50%, versus 50% for P1 and 100% for P3.
- H6 direction versus transcript: P5 and P3 both achieved 100%; P5 used 28.6% fewer proxy payload tokens.
- Adaptive policy: 100% success with 33.8% fewer proxy payload tokens than P3.
- P2 intent alone achieved 50%; in these fixtures, the winner's conclusion was more
  reliable than its short declared intent for abandon/escalate decisions.

The P1-pad and P3 prompts differed by at most six model-tokenizer tokens per case,
so the observed high-staleness difference is not explained by gross prompt length.
