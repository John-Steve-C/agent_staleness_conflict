# A Focused Plan for Context-Adaptive Refusal Feedback

2026-09-12 · Consolidated research priorities · One study at a time

This plan combines [the other agents' brainstorm](staleness-next-steps-brainstorm.md), [their implementation brief](NEXT_STEPS.md), and [the previous research agenda](staleness-context-and-coordination-research-agenda.md). It replaces their broader lists as the recommended near-term work sequence. The source documents and historical experiment remain unchanged; no experiments or code changes are executed by this document.

## 1. Main claim and the three priorities

**The central question is when a refusal message should contain additional intent, reasoning, or direction to improve recovery from concurrent edits.** Context length, staleness, and available evidence are candidate conditioning variables. A better action classifier is useful only if it improves the resulting recovery; a new benchmark is useful only if it helps answer this question.

The candidate claim to investigate is:

> The value of additional refusal feedback depends on the receiver's context and the information that has become obsolete. An adaptive communication rule must exploit a reproducible difference in payload benefit, not merely predict which episodes are difficult.

This remains a hypothesis. A longer context reducing every strategy's success equally would establish a context effect, but would not establish that payload choice should adapt to context. Likewise, a more accurate route classifier does not demonstrate better completed recovery.

| Priority | Work | Relation to the main claim | Decision |
|---|---|---|---|
| **1 — Required foundation** | Repair corpus construction and outcome measurement. | Makes any subsequent payload comparison interpretable. | **Do first.** This is a prerequisite, not a separate research program. |
| **2 — Highest research priority** | Test P1/P2/P3 under short/long context and current/superseded relevant history. | Directly tests whether the value of additional information depends on receiver state. | **Run one compact primary study.** |
| **3 — Conditional mechanism priority** | Test whether factual grounds help receivers reject wrong directives. | Explains when reasoning is useful as evidence for checking a route, connecting the P5 failure to communication design. | **Reserve as the next mechanism study; do not launch alongside Priority 2.** |

**If resources cover only two items, choose Priorities 1 and 2.** If Priority 2 yields a credible interaction, confirming that interaction on new families takes precedence over starting Priority 3. The third priority is the best additional mechanism question, not an obligation to keep expanding the experiment list.

## 2. What the synthesis keeps, changes, and postpones

| Proposal from the source documents | Consolidated decision and reason |
|---|---|
| Rebuild the instrument before adding payloads. | **Keep.** Correct action changes with k in the old generator, and easy abandon cases dominate part of the comparison. |
| Make context length and contradiction load central. | **Keep as testable factors.** Do not assume a signal-ratio threshold or that contradiction necessarily dominates k. |
| Give P2 another test. | **Include inside Priority 2.** Its action-specific tradeoff is a useful lead, so it does not need a separate experiment. |
| Test P6, a directive with falsifiable grounds. | **Promote above the earlier agenda's standalone evidence-acquisition and semantic-conflict studies.** It changes the message directly and tests a plausible reason information could help. |
| Retain only items where P1 scores 30–70%; require 30 families immediately. | **Revise.** Keep easy controls and a separately defined challenge subset. Do not select evaluation cases on observed payload performance. Start with a diagnostic pilot, then size confirmation from measured variation. |
| Use 1k/8k/32k/128k contexts plus a position arm. | **Reduce.** Start with two lengths within the existing server limit and fix message position. Additional lengths and positions are follow-ups only if needed. |
| Run a merge-derived routing benchmark in parallel. | **Defer.** It adds acquisition and annotation work and is less direct evidence for a payload-content claim. |
| Implement P7 authority framing and P8 execution routing immediately. | **Defer.** Authority framing is another mechanism; public tests supply partial evidence rather than a complete action oracle. Neither is required for the first comparison. |
| The previous agenda's separate tool-selection, semantic-conflict, and scheduling studies. | **Defer as independent studies.** Use partial completion and cross-file requirements as case types in the shared corpus, without opening new experiment tracks. |

Several numerical or interpretive statements in the earlier proposals should not be carried into the new plan:

- The stable high-k composition starts at **k=7**: 2 adapt / 4 abandon / 2 escalate per k. At k1–2, all eight cases are adapt. Higher-k files still accumulate protected revision assignments, so the rows are not identical copies.
- The actual P1 adapt result is **148/165 = 89.7%**, not 86.8%. P2 is **126/165 = 76.4%**, a **13.3-point reduction**. P2's escalation improvement is **16/72 to 38/72**, or **+30.6 points**, and comes from one family. It is a lead to replicate, not established general behavior.
- Under P5, **90/165 true-adapt continuations ended in abandon**. The earlier 160/261 description does not match the saved run. Under-escalation and route adherence motivate studying deference, but do not establish a psychological cause; non-adapt scoring currently relies on label agreement.
- The payload's reported length is a whitespace-token proxy; actual prompt length uses the model tokenizer. Their ratio does not establish the claimed 22% signal fraction. Natural receiver lengths and an MDE above 20 points were not demonstrated by those calculations.
- A fitted router does not establish a routing-accuracy ceiling, and the pilot's approximate 82.5% break-even is not a universal rejection threshold.

Counts were checked against the [saved replay outcomes](STORM/STORM/crossover_experiment_qwen35_leakage_safe_k16_20260909/replay_results.csv). The earlier agenda provides the fuller audit and hypothesis-status qualifications; repeating the entire audit is not a new workstream.

## 3. Priority 1 — Repair the evaluation, with a bounded scope

**Deliverable:** one versioned pilot corpus and a scoring/reporting specification usable by both subsequent studies.

Build 12 new scenario families, each supplying separate adapt, abandon, and escalate cases: **36 base cases**. Specify task obligations and coordination rules before writing winner descriptions or payloads. Include straightforward completion controls and harder full-versus-partial-completion pairs. Some cases may involve a caller or shared invariant in another file; this adds useful variation without creating a separate semantic-conflict benchmark.

For each case, the intended action must remain fixed across payload and context variants. Remove the old rule that derives `correct_action` from a k threshold. Every k included in a future comparison must contain all three actions with the same family composition. Test that the generator can represent each case at k1 and k8 without changing its label merely because the counter changed; the first model grid below uses only k4. Record revision history rather than requiring output to grow with synthetic marker assignments.

The abandon ceiling needs a careful response. All content-bearing strategies scored 147/147 on the old abandon continuations, but all 49 unique abandon snapshots also passed the existing behavioral checks. Easy completion is not inherently a scoring bug. Keep easy cases as regression controls and add independently specified near misses. Report abandon precision and unnecessary abandonment, not just recall on already-complete cases. Do not relabel, oversample, or discard old rows to manufacture low-k support.

Separate three outcomes:

1. **Route correctness:** agreement with the specified action or acceptable-action set.
2. **Verified recovery:** task obligations hold after adaptation, or already hold when abandoning; legitimate peer behavior is preserved.
3. **Completed coordination:** escalation actually resolves the disagreement in a continued workflow. Leave this unmeasured in a one-step pilot rather than crediting it from the label.

Report verified outcomes on adapt/abandon cases separately from justified escalation. An action-macro diagnostic may include all three routes, but must be named as a composite rather than an end-to-end task-success rate. An invariant violation alone does not always require escalation: the public coordination rules must explain when the receiver needs a manager decision.

**Gate before inference:** balanced action counts, independent task specifications, action invariance across variants, behavioral positive/negative controls, no hidden-label access in deployable prompts, and family-disjoint development/evaluation splits. A false abandon on a partial-completion case must fail; a valid complete case must pass. P5 may state its independently predicted route, while access to oracle fields remains forbidden.

Also replace word-proxy length matching with actual tokenizer accounting and check output capacity. All 60 unparsable historical responses ended at the 400-token cap. Use a common 2,048-token allowance for the new pilot after confirming reference outputs fit, with truncation reported separately. Keep calibration as a small setup check; the earlier proposed 288-call historical budget comparison is not required for this focused plan.

**Scope boundary:** do not rebuild the complete STORM system, collect a large natural corpus, train a router, or design every future payload during this stage. Twelve families support exploration, not an automatic claim of statistical power. Before confirmation, calculate required family counts for a predeclared practically meaningful effect.

## 4. Priority 2 — One primary context-by-payload study

**Question:** does added intent or rationale become more or less useful as context grows or relevant remembered information becomes obsolete?

P1 is current content plus diff and stale dependencies. P2 adds the winner's declared intent. P3 adds an action-free rationale for the winning edit. Including these three conditions tests the meaningful STORM baseline, the promising compact-intent lead, and the original reasoning claim in a single grid.

| Factor | Initial choice |
|---|---|
| Cases | 12 families × 3 actions |
| Input length L | approximately 1,024 or 12,288 actual model tokens |
| Relevant history | current/version-consistent observations or matched superseded observations |
| Payload | P1, P2, P3 |
| Seeds | 0, 1 |
| Fixed controls | k=4; same task-relevant repository state and intended action within a case; refusal at the tail; common output allowance |

**Size: 12 × 3 × 2 × 2 × 3 × 2 = 864 continuations.** This replaces the previous 2,592-continuation proposal for the first run. Do not add P4, P5, P6, P7, or a position sweep to this grid.

Construct both history conditions with the same task-relevant symbols, observation locations, and amount of relevant material; change whether their recorded values/contracts agree with the current state. Mark provenance and versions. In particular, avoid contrasting irrelevant history with stale relevant history and attributing the whole difference to contradiction. Extend short contexts to long ones using unrelated valid history while keeping the number of manipulated relevant observations fixed. Log both absolute obsolete-span tokens and their fraction of context.

The current authoritative state in the refusal remains identical. Place relevant history at a fixed normalized position and the refusal at the end. Match total input across payloads within ±2% by adjusting unrelated history only; never drop essential evidence to meet a target. If the core case cannot fit 1,024 tokens, repair the pilot specification before running the grid rather than silently truncating. Input plus the 2,048-token output allowance must fit the saved server's 16,384-token limit.

These are **constructed context variants**, not restored natural agent trajectories. A fresh-history condition is a controlled alternative representation at the recovery decision. Do not claim its history arose through an identical live execution. Faithful natural replay is later confirmation work.

This first run studies **contextual staleness**, meaning superseded information in the receiver's history. It fixes write count and task-relevant world state to avoid multiplying factors. Therefore it cannot establish that context is a better predictor than varying k, or confirm the original monotonic write-count hypothesis. That narrower scope is intentional. If the mechanism holds, vary k or semantic-change severity in a subsequent confirmation rather than opening another simultaneous study.

### Analysis and interpretation

Predeclare P2−P1 and P3−P1 differences and test whether they change with L or history condition. Report within-action effects, verified adapt/abandon outcomes, justified escalation, failed revisions, unnecessary abandonment, truncation, and actual token cost. The P2 escalation lead is tested across the new families as part of this analysis; it is not a separate experiment.

Use family-level paired summaries with seeds nested within cases and report uncertainty appropriate to the small pilot. Show an equal-action composite only with its scoring definition beside it. A change driven entirely by escalation labels supports a route-decision claim, not verified task completion. Treat all pilot effects as exploratory and use new families for confirmation. Do not search for a threshold and report its training-set result as a deployed adaptive rule.

| Result | What it supports | Next action |
|---|---|---|
| Payload differences change with L/history across multiple families. | A candidate receiver-state-dependent communication effect. | Freeze the contrast; prioritize confirmation on new families before new mechanisms. |
| L/history reduces every payload equally. | A receiver-context difficulty effect. | Do not claim adaptive payload value; inspect error types before choosing a remedy. |
| One payload consistently wins without interaction. | A fixed-payload improvement on the measured cases. | Confirm that simpler finding; do not force an adaptive-policy narrative. |
| Apparent benefit exists only in one family or intervals remain wide. | Insufficient evidence for generalization. | Improve precision on the same question, rather than adding experimental axes. |
| No practically important effect and uncertainty is sufficiently narrow. | A constrained null for these lengths and history manipulations. | Report it; proceed to Priority 3 only if route-error robustness remains a relevant unresolved concern. |

Predicting the correct action from context length is not the primary goal here. With identical requirements and state, that label is fixed. The relevant later prediction target is **which message improves this receiver's decision or execution**, compared with a fixed baseline. No separate classifier-training study is needed to answer the first-stage question.

## 5. Priority 3 — Factual grounds for checking a directive

**Question:** can added information help an agent identify and reject an incorrect recovery directive?

This combines the other agents' P6 proposal with the earlier agenda's concern about evidence and selective recovery. It is more directly related to refusal-message content than building a new router or adding tool-selection machinery. It also avoids presuming that the observed errors prove deference: that is a mechanism to test.

Run this only after analyzing Priority 2, and after any immediately warranted confirmation of its primary result. Reuse the shared corpus as exploratory data; confirm any new P6 effect later on independent families.

At fixed k4, long context, and superseded history, compare:

- A common P1 base plus a directive and length-control text.
- The same base and directive plus a compact, checkable factual ground referencing the visible state.

Test the correct route and each of the two incorrect routes. For each case, prepare the factual-ground block from observable task/code information and keep that block identical across the three route conditions. Never fabricate a fact to make an injected wrong route sound justified, and do not select the grounding statement from an evaluator label. Match length using neutral control material; current code, requirements, and source availability stay fixed.

The actual P5 already contains a one-line hint, so this contrast must not be described as a faithful ablation of a previously “bare P5.” Name these explicit experimental forms separately. Injected correct/incorrect directions are diagnostic interventions, not deployable router predictions.

**Maximum initial size:** 36 cases × 3 supplied routes × 2 message forms × 2 seeds = **432 continuations**, plus **72 fresh P1 reference continuations**, totaling **504**. Treat the fixed wrong-route frequencies as an experimental error injection, not the frequency expected in deployment. This run is conditional, not included in the mandatory initial budget.

The principal contrast is the benefit of factual grounds on wrong-route cases versus correct-route cases. Report rejection of incorrect routes, retention of correct routes, verified outcomes where available, unjustified escalation, and cost. Higher rejection alone is insufficient: an agent that ignores every directive would also reject wrong advice. If the effect appears only on correct routes, grounds may improve execution or presentation but have not demonstrated the proposed error-checking mechanism.

If this works, its immediate contribution is a communication design principle: route advice should expose facts that the receiver can check. A practical router or tool-assisted verifier is a later implementation. Do not infer that “a passing test means abandon” or “a failed test means escalate”; coverage and coordination authority still matter.

## 6. Sequential execution and explicit deferrals

**Sequence:** repair and smoke-check → run the 864-continuation primary grid → analyze → choose one next step: confirm the primary result, resolve its uncertainty, run the 504-continuation directive diagnostic, or stop with a bounded conclusion. Only one substantive study is active at a time. Concurrent calls within that study are execution details, not additional research tracks.

The first planned scientific run is 864 continuations; the additional 504 are conditional. Confirmation is not assigned an invented sample count or dollar cost: size it from pilot variability and measured local throughput. Spend additional sampling on independent families before simply adding more seeds or more k values. No deployment claim follows from these pilot counts alone.

The following ideas remain useful but are **outside the initial work package**:

| Deferred item | Why it waits / what would justify it |
|---|---|
| AgenticFlict/RecoveryRoute-Bench | Dataset creation is not necessary to test message value. AgenticFlict contains simulated textual conflicts from open/unmerged PRs, not packaged recovery labels or receiver histories. Additional annotation would need a separate justification. [Dataset paper](https://arxiv.org/html/2604.03551v1) |
| P7 authority wording | Add only if errors remain compatible with an authority-framing mechanism after task evidence and scoring are checked. |
| P8 execution routing and learned selective routing | Add only after demonstrating which evidence or message intervention helps; evaluate tool costs and incomplete checks. |
| Standalone semantic-conflict benchmark | Use a few relevant case types in the shared corpus now; scale into a benchmark only when needed for external validation. |
| Queue/serialize, repeated interference, topology | These address live coordination dynamics and need actual scheduling/continuations; they are a later systems claim. |
| 32k/128k contexts, position sweeps, model-family grid | Expand only to test a specific generalization question, after validating capacity and the initial mechanism. |

The deliverable from the focused phase should be one clear answer about payload usefulness, with a trustworthy evaluation and appropriately limited uncertainty. It should not be a collection of new datasets, routers, and payload variants whose connection to the original communication claim is unclear.
