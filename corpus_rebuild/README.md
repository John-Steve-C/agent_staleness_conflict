# Corpus rebuild status

**Gate C′ remains closed.** The rebuilt candidate set contains 38 scenario
families and 114 mechanically validated episodes, fully crossing `adapt`,
`abandon`, and `escalate` at k=8. Its pre-model audit passes and is recorded in
`candidate_audit.json`; the `candidate_episodes*.jsonl` files retain each
calibration revision.

The first 2026-09-11 Qwen3.5-35B-A3B P1 calibration completed all 1,140 planned
continuations (10 seeds per item) at exactly 8,000 receiver-trajectory tokens.
There were 59 malformed or truncated JSON responses (5.2%). The strict ledger
excludes any item containing one rather than counting it as an ordinary model
failure. The item gate failed with admitted family clusters `adapt=1`,
`abandon=1`, and `escalate=8`, against the required 10 each. Of 10 admitted
items, 8 (80.0%) were in the 40–70% band. The complete run is in
`p1_qwen35_8k_20260911_r1/`.

A receiver-trajectory audit then found that the 8k padding repeated the task and
pending edit instead of adding neutral history. The renderer was corrected so
the real trajectory appears once and only neutral tool history is padded; exact
Qwen tokenization now verifies 1k, 8k, 32k, and 128k targets. After development
screens on seeds 0–2, revision r4 was frozen and evaluated once on held-out seeds
10–19. All 1,140 continuations were valid and exactly 8k tokens. Gate C′ still
failed: admitted family clusters were `adapt=9`, `abandon=2`, and `escalate=10`.
Of 21 admitted items, 16 (76.2%) were in the 40–70% band; 35 floor items remain
controls. This definitive run is in `p1_qwen35_8k_20260911_r4_heldout/`.

For comparison, `stage_c_gate_audit/` records why the old eight-family Stage-C
corpus is also ineligible. Do not run a payload contrast or Study S1 on either
corpus while Gate C′ is closed.

The calibration path is implemented in
`STORM/STORM/staleness_adaptive/calibration_experiment.py`. It refuses model calls
unless the candidate JSONL contains at least 30 families and fully crosses action
with staleness. It writes all raw responses and applies the 30–70% admission rule.
To calibrate a revised candidate set against an already-running local endpoint:

```bash
cd STORM/STORM
conda run --no-capture-output -n storm-staleness \
  python -m staleness_adaptive.calibration_experiment \
  --episodes /path/to/revised_candidate_episodes.jsonl \
  --output-dir /path/to/unique_calibration_run \
  --context-length 8000 \
  --tokenizer-path /shared/models/hf/Qwen3.5-35B-A3B/tokenizer.json
```

A passing `gate_c_prime.json` from a new, independently held-out calibration
remains the release condition. The next revision must target non-saturated
`abandon` items and recoverable `adapt` items without relaxing the prespecified
thresholds or tuning further on the r4 held-out responses.
