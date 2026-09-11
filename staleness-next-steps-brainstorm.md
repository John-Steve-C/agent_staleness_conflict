# Where to go after Stage C

**Companion to `staleness-adaptive-communication-proposal_new.md` (v3) · 2026-09-10**
Status: re-analysis of the leakage-safe k16 run, plus a menu of next studies.

---

## 0. The headline, before anything else

**The six hypotheses were not refuted. Four of them were never tested.** The Stage-C
corpus has a structural defect that makes H1/H2/H3 unmeasurable and H5/H6 uninterpretable,
and the re-analysis below shows a large payload effect sitting inside the data that the
aggregate reporting averaged away.

This is not a reason to redo Stage C. It is a reason to change *what the next corpus is*
before spending any GPU time. Sections 1–2 are the evidence; sections 3–8 are the plan.

---

## 1. What the existing data actually shows

All numbers below are recomputed from `crossover_experiment_qwen35_leakage_safe_k16_20260909/replay_results.csv`.

### 1.1 The staleness manipulation is confounded with the outcome labels

`correct_action` is not held constant across k. It *is* k, almost:

| k | adapt | abandon | escalate |
|---|---:|---:|---:|
| 1–2 | 8 | 0 | 0 |
| 3 | 7 | 1 | 0 |
| 4 | 5 | 2 | 1 |
| 5 | 4 | 3 | 1 |
| 6 | 3 | 3 | 2 |
| 7 | 2 | 4 | 2 |
| **8–16** | **2** | **4** | **2** |

Two consequences:

- **Low k is a pure-adapt corpus; high k is half-abandon.** The reported "P3−P1 reversal"
  (+8.3 at k1–4, −6.2 at k13–16) is exactly what you get from re-weighting three action
  cells with very different payload sensitivities. It is a composition artifact, not a
  staleness effect. H2 was never given a chance to be true or false.
- **k ≥ 8 is frozen.** Nine of the sixteen levels are the *same eight episodes with the
  same labels*. The "16 staleness levels" are ~7 distinct configurations plus 9 replicates.

### 1.2 38% of the corpus is saturated and dilutes every contrast

Success rate by strategy × correct action:

| strategy | adapt | abandon | escalate |
|---|---:|---:|---:|
| P0 | 0.0% | 0.0% | 0.0% |
| P1 | 86.8% | **100.0%** | 22.2% |
| P2 | 76.4% | **100.0%** | **52.8%** |
| P3 | 91.5% | **100.0%** | 26.4% |
| P4 | 62.4% | **100.0%** | 20.8% |
| P1-pad | 91.5% | **100.0%** | 12.5% |
| P5 | 23.4% | **100.0%** | 65.3% |
| P5-oracle | 97.0% | 100.0% | 100.0% |

Every payload that contains *any* content scores 100% on abandon. That is 49 of 128
episodes contributing exactly zero discriminative information while absorbing 38% of the
weight in every headline number. The aggregate P3−P1 of +1.6 points is a real quantity
about this corpus and a meaningless quantity about payload design.

### 1.3 The effect that was hidden: P2, on escalate, is +30.6 points

P2 (one-sentence declared intent) was reported as *tied* with P1 (81.0% vs 81.0%). Split
by action it is not tied at all — it trades:

- **escalate: 22.2% → 52.8%** (+30.6)
- **adapt: 86.8% → 76.4%** (−10.4)

That is H5's mechanism claim — payload value concentrates where the correct move is *not*
adapt — showing up clearly. H5 was tested with P3 and scored 0.0/+1.8/+4.2, so it was
recorded as "not established". **H5 was tested with the wrong payload.** A brief statement
of *what the other agent was trying to do* changes the receiver's willingness to push back;
a longer structured rationale (P3) does not, and length-matched padding (P1-pad, 12.5%)
makes it worse than doing nothing.

**Caveat that matters: this rests on one scenario family.** Escalate exists only in
`authorization` and `transaction`, and `transaction` is 0/33 for every non-P5 strategy —
a dead item. So the entire escalate signal is `authorization`: P1 16/39, P2 38/39, P3 19/39,
P1-pad 9/39. One cluster. This is a lead worth powering, not a finding.

### 1.4 Most items have no discriminative power

At P1: `deduplication` 57/57, `pagination` 57/57, `formatting` 21/21, `normalization` 18/18,
`cache` 12/12 on adapt — five families at ceiling. `transaction`-escalate at floor for
everything. Of eight families, roughly **one and a half carry all the variance**. With
episode-clustered inference over 8 clusters, the minimum detectable effect is somewhere
north of 20 points. A 10-point effect was never in reach, so "no reliable difference"
carries almost no information.

### 1.5 Context length is a constant, and it is ~40× too small

Receiver prompts run **222–864 tokens, median 581**. P1's payload is 126 tokens, so the
**payload is 22% of the entire receiver context.**

In a real STORM run the receiving engineer holds 15k–100k tokens of trajectory and the
refusal payload is well under 1%. **Stage C tested a signal-to-noise regime that cannot
occur in deployment**, and it is precisely the regime where the context-degradation
literature predicts *no* dilution. And yet P4 still lost 12 points at a 29% signal ratio.
Dilution is already biting at miniature scale. This is the strongest single argument for
the direction you raised.

### 1.6 One coherent behavioural finding does survive: deference

Two results, same underlying bias:

- **Under-escalation.** With P1, on episodes where the correct move is to push back, the
  model chose `adapt` **56 of 72 times** (78%). It does not lack the capability — under
  P5-oracle it escalates 72/72. It lacks the *disposition*.
- **Over-compliance.** Under P5 the model followed the predicted route 90.1% of the time
  and succeeded in 16.4% of misrouted cases. The router predicted `abandon` for 192 of 261
  true-`adapt` episodes, and the recovery agent duly abandoned 160 of them — throwing away
  work that plain P1 recovered 87% of the time.

The receiving agent's prior is *"the other agent is right."* Information payloads don't
shift it; a directive exploits it in whichever direction the router points. That is a
mechanism-level result about asynchronous multi-agent coding, it is orthogonal to staleness,
and nobody has characterized it.

---

## 2. The reframe

The v3 question is *how much should the refusal payload contain, as a function of how stale
the reader is?* The data says that question is under-specified in two ways: staleness of the
*world* was proxied by k, and staleness of the *reader's mind* was never measured at all.

**Proposed new centre of gravity:**

> When a concurrent write contradicts what a receiving agent believes, what determines
> whether it correctly stands its ground, adapts, or defers — and how does payload design
> move that decision?

Staleness becomes one input among several rather than *the* conditioning variable. Three
things this buys: it is supported by data you already have, it explains both the P5 failure
and the P1 failure with one mechanism, and it survives a null on H2.

---

## 3. Factor menu — what else to condition on

Ranked by expected value per unit of effort.

### F1. Receiver context length `L` — your suggestion, made precise ★ highest priority

**Claim:** the operative variable is the *signal ratio* `payload_tokens / context_tokens`,
not k. There is a τ\*, but it is measured in context tokens.

- Manipulate by padding the receiver's **own trajectory** (realistic prior tool calls,
  reads, partial edits), *not* the payload. L ∈ {1k, 8k, 32k, 128k}.
- Predicts: P3/P4's advantage shrinks and then inverts as L grows; P2's compactness becomes
  an advantage rather than a wash; the P1-vs-P4 gap widens monotonically.
- Cheap: same replay harness, same fixtures, one new knob. Long-context runs cost more
  tokens but replay is still ~$0.10/continuation.
- This is also the arm that makes the pilot *externally valid* — right now it isn't.

### F2. Contradiction load ★ the best new measure

Not "how much changed in the repo" but **how many tokens of the receiver's context are now
false**. Count the spans in A's context that the winner's edit falsifies: quoted file
content, symbol signatures A referenced, assumptions in A's plan.

- This is what "stale-state reference errors" actually means, and it is directly measurable.
- It reframes the payload's job: not *filling a gap* but *overwriting a belief*. Retraction
  is a harder operation than instruction, and that asymmetry is publishable on its own.
- Slots straight into the H4 horse race: `s_contradiction` vs `s_temporal` vs `s_semantic`
  vs `s_invest` vs k, competing to predict recovery outcome.
- Prediction: it dominates k, because k only matters through it.

### F3. Payload position in context

Asynchronous notification means the refusal can land anywhere in the receiver's history —
including buried under later tool calls. Cross position ∈ {head, middle, tail} with L.
Lost-in-the-middle × asynchrony is genuinely unstudied, it's nearly free once F1 is built,
and a positive result is immediately actionable for orchestrator design ("re-surface the
refusal at the tail before resuming").

### F4. Investment / sunk cost

Already specified as `s_invest` and still untested. Hypothesis worth stating sharply: the
correct action is largely determined by investment ratio — cheap work → adapt, expensive
work built on a false premise → escalate. If true, C2 lands and the router gets a strong
feature for free.

### F5. Evidence strength on the receiver's side

How well-grounded is A's own position? An agent holding a failing test that B's change
breaks should escalate; an agent holding a vague plan should adapt. Manipulate by varying
whether A's context contains executable evidence (a test, an assertion) or only prose.
Interacts with F1 directly: this is the *other* side of the signal ratio.

### F6. Task-semantic overlap between A and B

`abandon` is correct exactly when B's edit subsumes A's task. This is a semantic
subsumption relation, not a staleness quantity, and it is computable (§7). Currently
invisible to the design.

---

## 4. New payload conditions

### P6 — directive **with falsifiable grounds** ★ the key experiment

`"Abandon: engineer-B's dedupe() at names.py:42 already satisfies your assignment."`
versus bare `"Abandon."` (current P5).

**Hypothesis:** grounds do not help when the directive is right — they let the receiver
*catch it when it is wrong*. Predicts P6 ≈ P5 on correctly-routed episodes, and P6 ≫ P5
on misrouted ones (16.4% → materially higher).

Why this is the best single condition to run: it reconciles the two literatures the whole
proposal is built against. Reasoning in the channel is valuable not as an answer but as an
**error-detection substrate**. It also converts the P5 finding from "our router is bad" into
"directive payloads must be falsifiable" — a design principle rather than an engineering
excuse. And it is a 2×2 you can run on existing fixtures: {bare, grounded} × {correct route,
wrong route}, with route correctness *injected* rather than predicted, so the router is
removed from the critical path entirely.

### P7 — standing / authority framing, zero information

Add one sentence granting the agent explicit standing to reject a peer's change. No episode
content, no routing call, ~15 tokens.

If under-escalation (§1.6) is a disposition rather than an information deficit, P7 should
recover a large share of the 78% under-escalation rate at essentially zero cost. A positive
result replaces "how much to send" with **"permission, not information"**, which is a much
sharper paper and an easier deployment story.

### P8 — verification instead of prediction ★ the systems contribution

Stop predicting the route. Compute it. In a code setting the test suite is a cheap oracle:

1. Run A's intended behavioural check against B's current content. Passes → **abandon**
   (B already did it).
2. Run the tests A's context depends on against B's content. Breaks → **escalate**.
3. Otherwise → **adapt**.

One sandbox execution per refusal, no LLM call, no 613-token routing overhead. The Stage-C
router needs ~82.5% accuracy to break even; an execution-grounded router plausibly clears
that because it is answering a decidable question instead of guessing. Reframes RQ5 from
*information vs direction* to **prediction vs verification**, which is a better question and
one this domain is uniquely able to answer.

### P2+ — declared intent, properly powered

§1.3 says P2 is the most interesting payload in the study and it was reported as a tie.
Give it a real test: it is also the cheapest (written once at write time, reused by every
refused reader), so a confirmed P2 > P3 result is directly deployable.

---

## 5. Instrument rebuild — prerequisites, not options

No new claim survives without these.

1. **Fully cross action × staleness.** Every family supplies all three correct actions at
   every k. Without this, k and the label are the same variable.
2. **Retire saturated items.** Pilot each candidate episode under P1; keep those with
   success in the **30–70%** band and non-zero within-family variance. Standard item
   analysis. This alone is worth more than doubling N.
3. **≥30 families, not 8.** k costs nothing statistically — families are the clusters.
   Target ≥10 clusters per action cell.
4. **Report the MDE.** State the minimum detectable effect before running. If it is 20
   points, say so; then "no reliable difference" means something.
5. **Realistic context scale.** Minimum 8k receiver context, since 581 tokens is not the
   deployment regime.
6. **Keep `transaction`-class floor items** as a labelled "no payload can help" control —
   they measure the information ceiling, but exclude them from payload contrasts.

---

## 6. Three studies

### Study 1 — Context × Payload (recommended first) · ~2 weeks, ~$300

`L ∈ {1k, 8k, 32k, 128k}` × `{P1, P2, P3, P6, P7}` × 30 rebuilt families × 3 actions,
staleness held fixed at a mid value.

Primary: **payload × L interaction**, pre-registered. Secondary: contradiction load as a
continuous predictor; payload position (F3) as a nested arm.

This is your idea, and it has the strongest prior of anything here — §1.5 shows the pilot
sat in an unrealistic corner of exactly this axis.

### Study 2 — The deference benchmark · ~3 weeks, ~$400

Injected route correctness × {bare, grounded (P6), hedged} × evidence strength (F5).
DV: deference rate, plus recovery success. Output is a **trust-calibration curve** —
how much a receiving agent should weight a peer's assertion against its own evidence.

Removes the router from the critical path, so it is unblocked by the H6 result. Novel,
safety-adjacent, and squarely the mechanism the data already points at.

### Study 3 — RecoveryRoute-Bench from AgenticFlict · ~2 weeks, $0 GPU, runs in parallel

Extends the merge-dataset work you already started, and de-risks everything else.

336,380 conflict regions with real resolutions. Mine the *resolution* as ground-truth
recovery action (the losing branch's change was dropped → abandon; rewritten onto the new
base → adapt; the conflicting change was reverted or contested → escalate). Build the
feature set in §7, fit models, report:

- **the achievable routing accuracy ceiling** — is 82.5% even reachable?
- **feature-group ablation** — how much comes from staleness vs context vs task-semantics?
- a human/LLM upper bound on a hand-labelled subset.

If the ceiling is below 82.5%, P5-style directive routing is dead on arrival and you have
proved it cheaply — which itself is a result, and it redirects everything toward P6/P8
(make wrong directives survivable, or verify instead of predict).

---

## 7. Feature set for multi-factor action prediction

Your specific question — what besides staleness predicts the correct action. Grouped so the
ablation is interpretable:

**Staleness (current)** — k; `s_temporal`; `s_semantic` (Palantír severity); symbol-overlap
binary; `s_invest` (tokens, tool calls).

**Context (new, F1–F3)** — receiver context length; signal ratio `payload/context`;
**contradiction load** (absolute + as a fraction of context); position of the stale content;
number of prior refusals in this episode; turns since A's last read.

**Task semantics (new, F6)** — symbol-level overlap between A's assignment and B's edit;
**subsumption score**: does B's edit already satisfy A's stated task (this is the abandon
label); **invariant-violation score**: does B's edit break a property A's code or tests
assert (this is the escalate label); test-file overlap.

**Repo graph** — dependency distance between A's file and B's file; whether the changed
symbol is in A's read set; fan-in of the changed symbol; whether the change is a signature
change (Palantír's indirect-conflict case).

**History** — A's prior refusal count; whether A has already adapted once in this file;
manager assignment overlap.

**The design insight:** two of these features *are* the labels. `abandon` ⟺ subsumption,
`escalate` ⟺ invariant violation. So don't build a general classifier — build two targeted
detectors and route on them. And per §4/P8, both are *executable* rather than predictable in
a code setting, which is why verification should beat prediction.

---

## 8. Sequencing and gates

| When | Do | Gate |
|---|---|---|
| **Now, $0** | Re-analysis of §1 written up as an internal errata to v3. Recompute all contrasts action-stratified with MDE reported. | If the P2-on-escalate lead survives adding families, it becomes a primary hypothesis. |
| **Wk 1–2** | Rebuild corpus to §5 spec (30+ families, item-calibrated, action×k crossed). In parallel: Study 3, no GPU needed. | ≥10 clusters per action cell; P1 success in 40–70% on ≥60% of items. |
| **Wk 3–4** | Study 3 result. | Routing ceiling ≥82.5% → P5/P8 stays alive. Below → drop predictive routing, go to P6/P8. |
| **Wk 3–5** | Study 1 (context × payload), the H7 test. | Pre-registered payload×L interaction. |
| **Wk 6–8** | Study 2 (deference), plus P7 as a cheap side arm. | — |
| **Wk 9–11** | Tier-2 end-to-end on whatever won. | — |

---

## 9. What the paper is, under each outcome

- **H7 holds (context length is the conditioner).** The strongest outcome: you found the
  conditioning variable the two literatures were missing, and it isn't staleness. "Send more"
  and "send less" are both right, at different signal ratios, and τ\* is measured in context
  tokens.
- **P6 ≫ P5 on misroutes.** Directive payloads must be falsifiable. A design principle for
  both STORM- and ATM-class systems, and a clean reconciliation of the reasoning-exchange
  literature: reasoning is an error-detection substrate, not an answer channel.
- **P7 recovers under-escalation.** "Permission, not information." Cheapest possible
  intervention, biggest reframe, and a direct hit on Chun & Ahmed's open problem.
- **P8 beats predictive routing.** Verification beats prediction in domains with cheap
  oracles. A systems contribution, not just an ablation.
- **Everything null on a properly-powered instrument.** Now a real null — 30+ calibrated
  families, realistic context, action-crossed design, stated MDE. Stage C cannot support
  that claim; a rebuilt instrument can, and §1 is the appendix explaining why the obvious
  earlier reading was wrong.

All five are publishable. The difference from v3 is that the null is now *earned*.
