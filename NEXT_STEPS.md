# Next steps — staleness-adaptive communication

Handoff brief. Full rationale: `staleness-adaptive-communication-proposal_new.md` (v4) §7.2.

## Context in five lines

Stage C ran 8 scenario families × 16 staleness levels (k) × 9 payload strategies × 3 seeds
on Qwen3.5-35B-A3B and returned a null on all six hypotheses. Re-analysis of
`STORM/STORM/crossover_experiment_qwen35_leakage_safe_k16_20260909/replay_results.csv`
shows the null is mostly an instrument artifact. Do **not** run new payload conditions on
the existing corpus — fix the corpus first.

## The three defects (do not reproduce them)

1. **k is the label.** `correct_action` covaries with k: k1–2 is 100% `adapt`, k≥8 is a frozen
   2 adapt / 4 abandon / 2 escalate mix. The reported P3−P1 band reversal is re-weighting,
   not a staleness effect.
2. **38% of episodes are saturated.** Every payload with any content scores 100% on
   `abandon`. Five of eight families are at ceiling on `adapt`; `transaction`-escalate is at
   floor (0/33) for everything. Effective clusters ≈ 8; MDE > 20 points.
3. **Context is ~40× too small.** Receiver prompts are 222–864 tokens (median 581), so the
   126-token P1 payload is 22% of the whole prompt. In a live run it is under 1%.

## Tasks, in order

### T1 · Action-stratified re-analysis ($0, ~half a day)
Recompute every payload contrast split by `correct_action`, clustered on scenario family,
with the minimum detectable effect stated.
**Input:** `replay_results.csv`.
**Output:** `stage_c_reanalysis/` with per-action contrast tables and an MDE note.
**Done when:** every reported contrast carries its realised cluster count and MDE.

### T2 · Rebuild the corpus (blocks everything else)
**Goal:** an instrument that can detect a 10-point effect.
- Every scenario family supplies `adapt`, `abandon` **and** `escalate` at every k.
- ≥30 families; ≥10 family clusters per action cell.
- Item-calibrate: pilot each candidate under P1, admit only 30–70% success with non-zero
  within-family variance. Drop ceiling and floor items from payload contrasts (keep floor
  items as a labelled "no payload can help" control).
- Minimum receiver context 8k.
**Done when:** Gate C′ — ≥10 clusters per action cell and ≥60% of admitted items in the
40–70% P1 band.

### T3 · Context-length knob `L` in the replay driver
Pad the **receiver's own trajectory** (realistic prior tool calls, reads, partial edits) to
`L ∈ {1k, 8k, 32k, 128k}`. **Never pad the payload** — that is the P1-pad confound.
Add a position arm: refusal at head / middle / tail of the trajectory.
**Files:** `STORM/STORM/staleness_adaptive/replay.py`, `payloads.py`.

### T4 · New payload conditions
Implement behind the existing payload strategy interface (`payloads.py`):
- **P6** — route + falsifiable ground (`"Abandon: engineer-B's dedupe() at names.py:42
  already satisfies your assignment."`). Run with route correctness **injected**, not
  predicted, so the router is off the critical path.
- **P7** — one episode-independent sentence granting standing to reject a peer's change
  (~15 tokens, identical across all episodes; audit that it is).
- **P8** — route computed by execution: run A's intended behavioural check against B's
  content (passes → `abandon`); run the tests A depends on (breaks → `escalate`); else
  `adapt`.

### T5 · Study S1 — Context × Payload (the primary test)
`L ∈ {1k, 8k, 32k, 128k}` × `{P1, P2, P3, P6, P7}` × 30 families × 3 actions, k fixed at a
mid value. Pre-register the **`payload × L` interaction** before running.
**Hypothesis H7:** the conditioning variable is the signal ratio
`payload_tokens / context_tokens`, not k; rich payloads lose their advantage and invert as
`L` grows.

### T6 · Study S3 — RecoveryRoute-Bench (parallel, no GPU, $0)
From AgenticFlict (Zenodo, CC-BY-4.0, 336,380 conflict regions): mine PR resolutions into
`abandon` / `adapt` / `escalate` — losing change dropped / rewritten onto the new base /
reverted or contested. Fit the feature set in v4 §5.8; report the routing-accuracy ceiling,
a feature-group ablation, and a human upper bound on a hand-labelled subset.
**Gate:** if the ceiling is below ~82.5%, predictive routing is dead — drop P5 as a
deployment candidate and put the budget on P6 and P8.

### T7 · Study S2 — Deference benchmark
Injected route correctness × {bare, grounded, hedged} × receiver evidence strength.
Primary DV: **deference rate** (does the agent take the action the payload points at),
reported separately for correct and incorrect directives.

## Two leads worth preserving

- **P2 on `escalate`.** Reported as tied with P1 overall (81.0% vs 81.0%); split by action it
  is **+30.6 on escalate, −10.4 on adapt**. Rests on one family (`authorization`: P1 16/39,
  P2 38/39). Power it in T2 — it is the cheapest payload in the study.
- **Deference.** Under P1 the model chose `adapt` on 56/72 episodes whose correct action was
  `escalate`; under P5-oracle it escalated 72/72, so this is disposition, not capability.
  Under P5 it followed the route 90.1% of the time regardless of correctness, turning 160 of
  261 true-`adapt` episodes into abandonments.

## Rules that still bind

- Leakage audits before and after every run; no payload may name the recovery action.
- Inference unit is the **episode**, clustered on scenario family. Seeds are nested, not
  independent.
- State the MDE before running. A null without an MDE is not reportable.
- Never report an aggregate k curve over a corpus where action and k are not crossed.

## Board

Live work board (W1–W12, shared state):
https://claude.ai/code/artifact/ce30e301-8320-4950-9ee7-e196e4a9052c
