# Next steps — staleness-adaptive communication

Handoff brief. Full rationale: `staleness-adaptive-communication-proposal_new.md` (v4) §7.2.

## Decision, 2026-09-12

1. **Gate C′ is closed.** The one passing calibration is a 3-seed screen and does not
   replicate at 10 seeds. Do not start Study S1 on the synthetic corpus.
2. **T6 (RecoveryRoute-Bench) is stopped** — the archive cannot carry the label. Write it up
   as a negative data-availability finding; do not commission the human adjudication.
3. **T7 (deference) runs now.** It is the only experiment Gate C′ does not block.
4. **The payload study moves to CooperBench** as its substrate. The synthetic corpus is
   retired rather than revised an eleventh time.

## Context in five lines

Stage C ran 8 scenario families × 16 staleness levels (k) × 9 payload strategies × 3 seeds
on Qwen3.5-35B-A3B and returned a null on all six hypotheses. Re-analysis of
`crossover_experiment_qwen35_leakage_safe_k16_20260909/replay_results.csv` shows the null is
mostly an instrument artifact. Do **not** run new payload conditions on that corpus.

## Execution status

| Task | State |
|---|---|
| **T1** action-stratified re-analysis | **Done.** `stage_c_reanalysis/` — contrasts carry realised cluster counts and MDEs: adapt 37.3 pts (G=8), escalate 57.5 pts (G=2), abandon not estimable (P1 saturated). |
| **T2** corpus rebuild | **Suspended after 10 revisions.** See below. |
| **T3** context-length knob | **Done.** Exact Qwen tokenizer checks at 1k/8k/32k/128k. Found and fixed a padding bug that repeated the task instead of adding neutral history. |
| **T4** P6 / P7 / P8 | **Done.** In `payloads.py` with injected-route and execution-result guards. |
| **T5** Study S1 | Blocked. Moves to the CooperBench substrate (T9). |
| **T6** RecoveryRoute-Bench | **Closed — negative result.** |
| **T7** deference benchmark | **Next.** |

## Why the r10 pass is not a pass

`item_calibration_qwen35_r10_fresh_screen_20260911` reports `passed: true` with admitted
clusters 16/13/11. It used **3 seeds** (16–18). The same 120 candidates over **10 seeds**
(`..._development_...`, seeds 0–9) give 7/7/13 — fail.

- **25 of 120 items flip admission** between the two runs.
- **19 of the 40** screen-admitted items are rejected at 10 seeds.
- At 3 seeds `p1_success_rate` can only be 0, .33, .67 or 1.0; binomial SE at n=3 is ≈0.29,
  so the 30–70% band reduces to "landed on .67".

After ten revisions against a noisy threshold, one crossing is expected. The r4 held-out
10-seed run (9/2/10, fail) is the honest reading. **Any admission decision must use ≥10
seeds.**

## The four defects (do not reproduce them)

1. **k is the label.** `correct_action` covaries with k: k1–2 is 100% `adapt`, k≥8 is a frozen
   2 adapt / 4 abandon / 2 escalate mix. The P3−P1 band reversal is re-weighting, not
   staleness.
2. **38% of episodes are saturated.** Every content-bearing payload scores 100% on
   `abandon`; six of eight families are at ceiling on `adapt`; `transaction`-escalate is at
   floor for everything.
3. **Context is ~40× too small.** Receiver prompts were 222–864 tokens (median 581), so the
   126-token P1 payload was 22% of the whole prompt against <1% in a live run.
4. **The binary DV forces item selection.** A pass/fail outcome needs each item's difficulty
   inside a narrow band, estimated from a handful of Bernoulli draws — which is why
   admission is unstable and why ten revisions have not closed Gate C′. A graded outcome
   gets sensitivity from within-task variation instead. **This is the reason for the
   CooperBench move, not external validity.**

---

## T7 · Deference benchmark — run this now

**Why it is unblocked.** The primary DV is *compliance*, not success: does the agent take the
action the directive points at? That does not depend on the item sitting in a difficulty
band, so Gate C′ does not gate it. Run on the full r10 pool of 120 candidates **including
floor and ceiling items** — they are usable here precisely because solvability is not what is
being measured.

**Design.** Injected route correctness {correct, wrong} × directive form {bare (P5), grounded
(P6), hedged} × receiver evidence strength {executable test in context, prose plan only}.
Route correctness is injected, never predicted — the router stays off the critical path.

**DVs.**
- *Primary:* deference rate, reported separately for correct and incorrect directives.
- *Primary:* contradiction-detection rate — does the agent explicitly contest a wrong
  directive rather than comply?
- *Secondary:* recovery success given a wrong directive. Report **only on the admitted
  subset**; it inherits the difficulty-band problem.

**Seeds:** ≥10. **Inference:** cluster on scenario family, state the MDE.

**H8 predicts** grounded directives move the wrong-directive cell without moving the
correct-directive cell.

**Interpretive anchor:** CooperBench's failure taxonomy — commitment deviation 32%,
communication breakdown 26% — is the same family, so this result is directly comparable to a
652-task external benchmark.

## T6 · Close out as a negative result

The audit answered the question, negatively. From `recovery_route_bench/`:

- No outcome field in the archive; PR state is not a substitute.
- 29,609 conflicting PRs, but only **55 merged**; 0 regions carry both full-text sides.
- After history reconstruction: 10,348 file records, **534 with all three sides present**,
  and **25 true reconciliations** (`manual_or_combined`) — of which **19 are Markdown and
  none are Python**.

A 30-item hand-adjudicated sheet cannot fit the §5.8 feature set. **Do not commission the
two-reviewer annotation.** Keep `agenticflict_*.py` and the reconstruction outputs, and write
the finding up — it forecloses an approach others will otherwise attempt. AgenticFlict
remains valid for Gate A characterization only. Note its agent mix is 9,470 Codex / 881
Copilot / 8 everything else, so "agent-agent" is largely one model against a human base.

## T8 · Gate CB — reproduce CooperBench before building on it (~3 days)

[CooperBench](https://github.com/cooperbench/CooperBench): 652 tasks, 12 repos, 4 languages,
MIT licence, two agents implementing potentially-conflicting features over a Redis channel,
scored per-feature against expert-written tests. MIT also retires the STORM licensing risk
(v4 §9) for this arm.

Run one two-agent task end to end and confirm it surfaces conflict/refusal episodes at a
usable rate.

> **Gate CB.** ≥1 conflict episode per task on a 10-task pilot, with both agents' patches and
> trajectories recoverable. Below that, the substrate does not produce the events the payload
> study needs, and the synthetic corpus stays — with the binary-DV problem then addressed
> directly by adopting a graded merge score.

**Read their result before designing against it.** CooperBench reports *"communication
reduces conflicts but not failures"* — up to 20% of budget spent messaging, fewer conflicts,
no gain in success. That is an independent 652-task version of the null we have been chasing.
It validates the question and it is a scooping risk.

**What still differentiates us:** they measure *whether* agents communicate. There is no
payload ablation, no staleness manipulation, no context-length manipulation, and their
channel is agent-initiated chat rather than a system-generated refusal. Our question becomes:
*given that naive communication does not help, what must the refusal message contain, and how
much receiver context can it survive?*

## T9 · Migrate the payload study to CooperBench (replaces T5)

Two-tier, as in v4 §5.4, but on a real substrate:

- **Harvest** refusal/conflict episodes from a CooperBench subset — both patches, both
  trajectories, the test suites, the repo state at each side's read.
- **Replay** the recovery only, injecting P1 / P2 / P3 / P6 / P7 × `L ∈ {1k, 8k, 32k, 128k}`.
  The T3 context knob transfers directly and is the actual novel IV.
- **Score on merge quality**, graded: exact match → AST-equivalent → both feature test suites
  pass → one passes → neither. No admission band, no item calibration, no Gate C′.
- **H7 remains the primary test:** the conditioning variable is the signal ratio
  `payload_tokens / context_tokens`, not k. Pre-register the `payload × L` interaction.
- The coordination label falls out of the merge outcome — "was a correct reconciliation
  possible?" — instead of being annotated separately.

## Two leads worth preserving

- **P2 on `escalate`.** Reported as tied with P1 overall (81.0% vs 81.0%); split by action it
  is **+30.6 on escalate, −13.3 on adapt**. Rests on one family (`authorization`: P1 16/39,
  P2 38/39). It is the cheapest payload in the study — written once at write time.
- **Deference.** Under P1 the model chose `adapt` on 56/72 episodes whose correct action was
  `escalate`; under P5-oracle it escalated 72/72, so this is disposition, not capability.
  Under P5 it followed the route 90.1% of the time regardless of correctness; on true-`adapt`
  continuations it was told `abandon` 108/165 times and followed that route 90 times.

## Rules that still bind

- **≥10 seeds for any admission or gate decision.** The r10 screen is why.
- Leakage audits before and after every run; no payload may name the recovery action.
- Inference unit is the **episode**, clustered on scenario family. Seeds are nested, not
  independent.
- State the MDE before running. A null without an MDE is not reportable.
- Never report an aggregate k curve over a corpus where action and k are not crossed.
- Do not iterate a candidate pool against a gate more than twice without changing the
  measurement — a third attempt is selecting on noise.

## Board

Live work board (W1–W12, shared state):
https://claude.ai/code/artifact/ce30e301-8320-4950-9ee7-e196e4a9052c
