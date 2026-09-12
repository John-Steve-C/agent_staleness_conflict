# Beyond Staleness: A Research Agenda for Asynchronous Agent Coordination

2026-09-12 · Research agenda and revised experiment plan · Local-first

This document extends the plan in [NEXT_STEP_CODEX.md](NEXT_STEP_CODEX.md) and responds to the [v3 proposal](staleness-adaptive-communication-proposal_v3-snapshot.md) using the [leakage-safe Stage-C artifacts](STORM/STORM/crossover_experiment_qwen35_leakage_safe_k16_20260909/). It adds a prerequisite: repair the action-by-staleness design and strengthen outcome validation before testing new communication mechanisms. The work described below is proposed; creating this document does not change the experiment code or historical results.

**Recommendation:** investigate context and stale-state handling, evidence acquisition before recovery, and semantic conflicts beyond textual merging. First make the evaluation capable of distinguishing these mechanisms. The current results do not establish that all six original hypotheses are false, and they also do not justify replacing staleness with another presumed universal predictor.

## 1. What the existing experiment establishes

The saved run contains 128 unique episodes: eight scenario families at each of 16 intervening-write counts, replayed under nine strategies and three seeds, for 3,456 continuations. Here `k` counts intervening writes; it is not an independently measured wall-clock timestep.

Payload shorthand: P0 is a bare refusal; P1 supplies current content, a diff, and stale dependencies; P2 adds winner intent; P3 adds an edit rationale; P4 adds winner task/trajectory context; P5 adds a predicted recovery directive. P5-oracle supplies the ground-truth directive for diagnosis, P1-pad adds unrelated length-control text, and adaptive switches between P1 and P5 using k.

| Observation | Interpretation |
|---|---|
| P3: 317/384 successes (82.6%); P1: 311/384 (81.0%). Reported paired difference +1.6 percentage points, 95% episode-bootstrap interval −2.6 to +5.7. | No reliable overall P3 advantage on this corpus. This is not proof of equivalence or a causal staleness result. |
| P4: 265/384 (69.0%). | Its extra content was associated with worse performance under this setup. Length, content, response budget, and agent behavior require separate diagnosis. |
| P2 on escalate: 38/72 (52.8%), versus P1's 16/72 (22.2%). P2 on adapt: 126/165 (76.4%), versus P1's 148/165 (89.7%). | A promising action-dependent tradeoff: +30.6 points on escalate and −13.3 on adapt. The escalation improvement is entirely in the authorization family; transaction remains at zero for both. |
| P5: 239/384 (62.2%); P5-oracle: 379/384 (98.7%). | The current predicted directive performs poorly. Oracle direction is a diagnostic, and label-based non-adapt scoring contributes to its high result. |
| Actual receiver prompt lengths: 222–864 tokens, median 581.5. | The run does not test long receiver histories. Longer deployment histories must be measured rather than assumed. |
| All 60 unparsable recovery responses have `finish_reason=length` at the 400-token output cap. P4 accounts for 13; P1 for zero. | Output truncation is a measured failure mechanism. It cannot alone explain P4's 46-success deficit relative to P1. |
| Payload length is computed with `len(text.split())`, while prompt length comes from model usage. | The historical “length-matched” control matches a word proxy, not tokenizer tokens. Dividing these quantities does not establish a valid payload/context token ratio. |

Sources: [replay outcomes](STORM/STORM/crossover_experiment_qwen35_leakage_safe_k16_20260909/replay_results.csv), [raw responses](STORM/STORM/crossover_experiment_qwen35_leakage_safe_k16_20260909/model_responses.jsonl), [report](STORM/STORM/crossover_experiment_qwen35_leakage_safe_k16_20260909/report.md), and [payload renderer](STORM/STORM/staleness_adaptive/payloads.py).

The hypothesis status remains differentiated: H1/H2 are unsupported under a confounded design; H3 lacks its proposed high-staleness advantage and has an imperfect length control; H4 is untested with natural investment measurements; H5 has exploratory leads but no general confirmation; H6 failed for the current router. Do not carry forward claims that the observed reversal is entirely a composition artifact, that all hypotheses were conclusively refuted, or that the existing eight families imply a particular minimum detectable effect without a calculation.

## 2. Are label imbalance and perfect abandon scores bugs?

### 2.1 Label imbalance across k: confirmed, and a design defect for the causal question

Counts below are **unique episodes**, before multiplying by strategies or seeds. The last row gives counts at each individual k in that range.

| k | Adapt | Abandon | Escalate | Abandon share |
|---|---:|---:|---:|---:|
| 1 | 8 | 0 | 0 | 0% |
| 2 | 8 | 0 | 0 | 0% |
| 3 | 7 | 1 | 0 | 12.5% |
| 4 | 5 | 2 | 1 | 25% |
| 5 | 4 | 3 | 1 | 37.5% |
| 6 | 3 | 3 | 2 | 37.5% |
| 7–16, each k | 2 | 4 | 2 | 50% |
| **All 128 episodes** | **55** | **49** | **24** | **38.3%** |

Thus, “low k is pure adapt; high k is half abandon” is correct. The stable 2/4/2 composition actually begins at **k=7**, not k=8.

The cause is explicit in [build_crossover_episodes](STORM/STORM/staleness_adaptive/crossover_experiment.py): `high = k >= scenario.switch_k`, followed by `correct_action = scenario.high_action if high else RecoveryAction.ADAPT`. The same switch chooses a different current implementation and winner description. Increasing k therefore changes both the apparent staleness and which task remains to be done.

This is deterministic fixture construction, not evidence of a random data-loading error. It is nevertheless a **design defect for estimating the effect of staleness while holding recovery task type constant**. A classifier can also exploit k as a shortcut to the label. Natural data can legitimately have a changing action distribution; the problem is interpreting this synthetic manipulation as if it isolated staleness.

An aggregate curve mixes two quantities:

`success(payload, k) = sum over actions [action_share(action, k) × success(payload, action, k)]`.

Both terms vary here. A fixed classifier that always chooses abandon would achieve 0% action accuracy at k1–2, 50% at k7–16, and 38.3% overall without examining any code. This is a label-accuracy diagnostic, not a tested end-to-end recovery policy.

Two qualifications matter:

- A stable label mix does not make later k rows identical. Each additional k appends protected revision assignments, increasing input and full-file output requirements. These markers can affect copying difficulty, token cost, and the nominal semantic-change metric.
- Composition does not explain every reversal. Within the escalate stratum, P3−P1 changes from +52.4 points in k5–8 to −16.7 in k9–12 and −25.0 in k13–16. These are sparse, correlated observations, but they rule out asserting that the entire pattern follows from changing action proportions alone.

### 2.2 Perfect abandon scores: a ceiling effect, with an outcome-measurement gap

For each of P1, P2, P3, P4, P5, P5-oracle, P1-pad, and adaptive, all **147/147 abandon continuations succeed**: 49 unique episodes × three seeds. P0 succeeds on 0/147. Thus these abandon cases distinguish a bare refusal from content-bearing feedback, but provide no observed success difference among the content-bearing strategies. They remain useful for cost comparisons and for checking that a new intervention does not regress easy cases.

This does **not** show that every response was automatically accepted. The model still has to output the abandon label. Nor is 100% intrinsically a bug: the peer's current code can make task completion obvious. As an additional check for this document, all **49/49 abandon current-code snapshots passed the existing behavioral validator**, including protected revision assignments. These checks support the current labels within the limited fixture specification; they do not prove exhaustive task completion.

The measurement gap is in [the recovery backend](STORM/STORM/staleness_adaptive/local_model.py). An adapt success requires label agreement plus a valid executable revision. For abandon or escalate, `tests_pass` is set true from label agreement alone. The saved metric therefore combines patch execution with route classification. It does not demonstrate that abandoning leaves all obligations satisfied, or that escalation ultimately resolves a disagreement.

Classification is a legitimate mechanism measure. Calling label agreement a mechanically verified task outcome would be a measurement/reporting error. The oracle score and claims about “capability versus disposition” must be interpreted with that limitation.

### 2.3 Required fixes before the next mechanism grid

**A. Build a balanced controlled corpus without relabeling existing episodes.** Construct 12 new families, each with separate adapt, abandon, and escalate cases at both k=1 and k=8. That gives 36 unique cases per k: 12 per action. Hold each case's intended action constant across k, context length, history condition, and payload. Derive the label from independently specified requirements and coordination rules, not from a k threshold or a winner rationale.

For the initial write-count control, perform one relevant conflicting write in both conditions and add seven task-irrelevant writes for k=8. Define this k explicitly as global writes since the receiver's read, and separately record writes in its read/dependency set. This isolates elapsed write activity; it is **not** a manipulation of semantic damage. A later semantic-severity arm changes relevant code while holding action and write count fixed. Keep revision identity in the event record instead of lengthening required output with dummy assignments.

**B. Give the abandon boundary informative cases.** Include paired full-completion versus partial-completion cases, alternative implementations that truly satisfy the same requirements, an omitted edge case, and an apparently completed function with a missing caller update. A minimally changed requirement or peer implementation should change the justified route for a stated reason. Do not manufacture difficulty by hiding the only necessary evidence while insisting the receiver guess a unique label; use such examples in the explicit information-acquisition study instead.

Keep straightforward abandon cases as regression controls. Do not remove every item above a P1 accuracy threshold or select the test set using measured payload gains. Report a representative evaluation and a separately identified challenge subset. Correctly solved cases are part of the target distribution.

**C. Separate route correctness from verified outcomes.** For the next corpus, report action accuracy, verified task success, and recovery cost separately. Validate abandon against task requirements in the unchanged current snapshot; validate adapt against those requirements and preserved concurrent behavior. For escalation, distinguish a justified request from completed resolution, and evaluate downstream completion only when a manager continuation is actually run. Mark unobserved outcomes as unmeasured. Public coordination rules must establish when the receiver lacks authority to settle a disagreement itself; a single bad peer edit does not automatically make escalation the only valid response.

Where multiple actions are defensible, retain an annotated acceptable-action set or mark the case ambiguous for the single-label analysis. Keep tests used as private evaluation separate from public tests available as intervention evidence.

**D. Repair analysis as well as generation.** Report per-action performance, action confusion matrices, abandon precision and recall, unnecessary-abandonment rate, and equal-action macro averages. On the new balanced grid, also report fixed-weight aggregate curves. Preserve observed-prevalence results on natural data. All variants and seeds from one family stay in the same split; report episode-level paired uncertainty for the fixed corpus and family-level sensitivity for generalization.

For the existing data, show the action-by-k table and within-action contrasts. Reweighting, oversampling, or class-weighted training cannot recover the missing abandon/escalate examples at k1–2. Do not impute those cells or claim weighting alone repaired the causal design. Do not balance a natural corpus by changing its labels.

**E. Add focused acceptance checks for the future implementation.** Before spending inference budget, verify equal counts in every planned action-by-k cell; action invariance across context/k variants; no family overlap between development and test; no ground-truth labels, oracle hints, or hidden evaluator fields in deployable prompts; and tokenizer-consistent length matching. P5 may explicitly state its independently predicted route; that is its intended intervention, not permission to read the ground truth. Verify that a wrong abandon fails on a partial-completion case, a correct abandon passes on its matched completion case, a valid adapt preserves peer behavior, and a justified escalation is not counted as completed resolution. Negative controls must fail before the benchmark is accepted.

The fix is a new, versioned corpus and scoring specification. Keep the original run unchanged so that old results remain reproducible.

## 3. A broader research question and a ranked idea menu

> Given repository state, receiver context, and available evidence, what intervention best helps an agent recover correctly at acceptable cost?

Distinguish **the correct action**, **the probability this receiver can execute it**, and **the best intervention before execution**. With unchanged requirements and repository state, a longer context should not make an already-complete task incomplete. It may instead make recognition less reliable and increase the value of a reread or concise state refresh. Investment in a stale patch changes wasted effort and scheduling costs; it does not by itself justify escalation.

| Priority | Direction | Smallest useful experiment | What it could teach us / main limitation |
|---|---|---|---|
| 1 | Context length × superseded information | Vary history length and stale observations independently with current evidence fixed. | Whether interference or length predicts recovery; constructed histories need natural confirmation. |
| 2 | Evidence acquisition before action | Compare immediate recovery with one targeted reread or public test. | Which missing observation is worth obtaining; include its full cost. |
| 3 | Semantic conflicts beyond textual merging | Cross textual overlap with behavioral compatibility. | Catch clean merges that break contracts and avoid false alarms; requires explicit behavioral requirements. |
| 4 | Context invalidation and refresh | Compare appending a diff with marking old observations superseded, or replacing them with a versioned summary. | Whether repairing the receiver's state beats sending more information; compression can accidentally remove necessary evidence. |
| 5 | Selective routing | Issue a directive only when a calibrated policy prefers it to a tested fallback. | Whether abstention reduces harmful misroutes; raw confidence is not calibrated correctness. |
| 6 | Verifiable grounds for directives | Cross correct/incorrect routes with bare versus checkable supporting evidence. | Whether receivers can reject wrong advice; injected errors are a mechanism diagnostic. |
| 7 | Repeated interference and timing | Replay another write during recovery, then compare retrying, waiting, and serialization. | When communication timing matters more than payload; needs an actual scheduler. |
| 8 | Partial versus full task completion | Paired peer edits satisfying all versus only some obligations. | A harder, interpretable abandon boundary; incomplete specifications create ambiguous labels. |
| 9 | Dependency structure | Match change size while varying changed interfaces and affected callers. | Whether dependency relevance beats raw k or line counts; static dependency approximations are imperfect. |
| 10 | Output and execution constraints | Compare output caps with identical prompts, then separately investigate patch versus full-file output. | Whether failures are coordination or execution limitations; changing output formats changes the task. |

Context position is motivated by [Lost in the Middle](https://arxiv.org/abs/2307.03172); testing effective capacity rather than advertised limits is motivated by [RULER](https://arxiv.org/abs/2404.06654). Reliance on earlier responses in [LLMs Get Lost in Multi-Turn Conversation](https://arxiv.org/abs/2505.06120) motivates a separate history/commitment arm. These studies do not establish the mechanism in Qwen or asynchronous code recovery. No direction assumes a monotonic crossover or claims uniqueness without a fuller literature review.

## 4. Three prioritized studies

### Study A — Context length, write count, and stale-state interference

**Question:** Does receiver context add predictive value beyond staleness, and does superseded relevant information explain more than length alone?

Use the balanced corpus and validation requirements in §2.3. The first grid is:

| Factor | Initial levels |
|---|---|
| Scenario families | 12 newly constructed families |
| Correct action within every family | adapt, abandon, escalate |
| Intervening global writes | k=1, k=8; same task-relevant final state |
| Total model input | approximately 1,024 / 4,096 / 12,288 tokenizer tokens, including system prompt and payload |
| History | valid unrelated history / equally sized history containing superseded relevant observations |
| Payload | P1, P2, P3 |
| Generation seeds | 0, 1 |

Total: **12 × 3 × 2 × 3 × 2 × 3 × 2 = 2,592 recovery continuations**. This is an exploratory mechanism pilot, not a powered confirmatory study or a promise of 2,592 independent observations.

Construct each history from versioned observations. Fix the number and locations of obsolete relevant facts while varying length by adding unrelated valid history. In the matched clean condition, replace the obsolete chunks with equal-length unrelated material. This isolates the effect of including stale relevant observations as a treatment package. To distinguish contradiction from relevance alone, a follow-up replaces those chunks with equally relevant current facts; record absolute stale-span tokens and their fraction of history separately.

Keep the task, current authoritative evidence, and reference action fixed within each matched case. Place the refusal at the end in the main grid and keep stale chunks at the same normalized history positions. Match total input length across payload conditions by adjusting only unrelated history, recording the adjustment. Permit ±2% length tolerance; never truncate essential evidence to meet a target. If a case cannot fit the shortest level, redesign it or mark that level unavailable before inference and do not report a fully balanced grid until repaired.

Use a common 2,048-token output allowance after verifying that reference outputs fit. The saved server configuration is 16,384 tokens, so a 12,288-token input leaves room for this output. Confirm actual tokenizer/chat-template accounting in a smoke check; 32k/128k are later capacity experiments, not assumed available. The current backend sends one system and one user message and does not restore a receiver trajectory. Adding a history field to a prompt is a constructed-context experiment; faithful natural replay requires real receiver-message capture and restoration.

Primary contrasts: payload-by-length and payload-by-history interactions on verified recovery. Also report action accuracy, wrong abandonment, failed code revisions, invalid responses, retained concurrent behavior, and full token/latency costs. Hold no directional sign fixed: long context could help when it supplies relevant evidence, hurt through interference, or have little effect.

**Next decision:** if stale history changes outcomes consistently across families, test versioned invalidation and selective refresh. If only k predicts actions on a supposedly action-balanced corpus, first investigate construction leaks. If nothing varies within the tested lengths, report that range and its uncertainty before expanding context length or family count.

### Study B — Predict the next observation before predicting the route

**Question:** When is a targeted reread or executable check more useful than an immediate directive?

Create matched cases where the initial refusal is insufficient but an accessible dependency, stated requirement, or public test supplies useful evidence. Include complete, partial, contradictory, and inconclusive evidence. Reuse the balanced semantic requirements from Study A, with the evidence-access manipulation identified separately.

Compare P1 with immediate recovery, the current P5 router, one targeted reread before recovery, one relevant executable check before recovery, and a selective policy choosing immediate recovery or one of those observations. Evidence-acquisition conditions receive at most one additional operation before the action decision. Route and selection calls count toward cost even when no useful evidence is obtained.

Distinguish private evaluator tests from public tests the agent may execute. A passed example test is evidence for covered behavior, not proof that the entire assignment is complete. Failed or unavailable checks remain recorded outcomes. Cases whose necessary evidence is unavailable support evaluating uncertainty and coordination; they must not silently become tests of guessing hidden facts.

Measure verified success against total model/tool cost, plus unnecessary abandonment, missed invariant violations, unnecessary escalation, and directive error conditional on coverage. Router abstention means invoking a specified fallback, initially P1 recovery; it is distinct from escalating an actual contract disagreement. Evaluate the fallback empirically rather than assuming it succeeds.

Use held-out calibration and a small policy before considering fine-tuning or reinforcement learning. [KnowNo](https://arxiv.org/abs/2307.01928) motivates selective assistance; its robotics guarantees do not transfer automatically to this setting. Choose policies using measured downstream success and cost, not the old pilot's approximate 82.5% routing break-even estimate.

**Next decision:** keep evidence acquisition if it improves the success/cost tradeoff on unseen families. If route accuracy improves without verified task success, inspect the execution and outcome stages rather than declaring the router solved.

### Study C — Conflicts that merge benchmarks miss

**Question:** Can the system distinguish textual overlap from consequential semantic interference?

Build balanced groups of same-file compatible edits, direct conflicts requiring adaptation or a contract decision, and different-file edits that merge cleanly but break a shared requirement. Include signature/caller mismatch, inconsistent serialization assumptions, partial duplicate implementations, and a stale patch reintroducing removed behavior. Maintain an explicit specification and an acceptable-action annotation for each case.

Compare P1, dependency-targeted evidence, and the intervention selected on development data from Studies A/B. Freeze that choice before evaluating new cases. Measure combined task completion and invariant preservation, unnecessary intervention on compatible edits, and missed semantic conflicts. Require preservation of both agents' legitimate work where the requirements are compatible.

AgenticFlict supplies simulated textual conflicts and related metadata from open or closed-unmerged PRs. It does not directly provide validated adapt/abandon/escalate labels, successful resolutions, or receiver histories. Use it for realistic conflict structures and descriptive statistics within its sampling frame; acquiring resolutions or action labels is a separate data and annotation task. Do not equate a closed PR with justified abandonment or treat a fitted classifier as an information-theoretic routing ceiling. [AgenticFlict](https://arxiv.org/html/2604.03551v1)

After snapshot results are informative, run a small deterministic schedule extension: no further writes, one further relevant write, or repeated relevant writes during recovery. Compare immediate adaptation, refresh/retry, and actual queue/serialization behavior, with a common maximum of five recovery attempts. Keep the external writer workload and event schedule recorded; include serialization's waiting cost. Evaluate eventual correctness, repeated refusals, wasted work, and completion time. Choosing the word `serialize` without enforcing serialization is not a systems result.

**Next decision:** if gains appear only on synthetic semantic conflicts, report that limitation and validate on natural multi-file tasks before proposing deployment.

## 5. Features, prediction targets, and statistical discipline

Use grouped feature ablations, separating quantities observable at decision time from offline annotations.

| Feature group | Candidate observations |
|---|---|
| Staleness | Global and relevant intervening writes, elapsed time, changed symbols, actual dependency overlap |
| Context | Actual model input length, version-identifiable obsolete spans, repetition, position of authoritative evidence, previous refreshes |
| Task/evidence | Stated remaining obligations, observable task overlap, public check outcomes available before the decision |
| Execution | Proposed patch size, output allowance, prior failed repairs |
| Coordination | Repeated refusals, ongoing overlapping assignments, whether dependencies are still being edited |

“True contradiction load,” “task subsumption,” and “invariant violation” must not enter as features computed from hidden labels. Use observable approximations, such as versioned symbol references or public test evidence, and evaluate their errors. Mark perfect annotations as diagnostic information unavailable to deployment.

For action prediction, compare a majority baseline, staleness-only features, context-only features, their combination, and evidence-augmented features. Start with regularized linear classifiers and shallow trees. Report class-wise precision/recall and confusion, including a k-only baseline to detect shortcuts.

For recovery-risk prediction, estimate the chance of verified success under a specified payload and context. For intervention selection, estimate the benefit of a refresh, check, or alternate payload from paired outcomes; do not substitute action-label accuracy for this benefit. Compare against fixed P1 and the existing router, charging policy calls, public tools, failed calls, summaries, and write-time rationale generation where applicable.

Split by family for controlled development and by repository/task lineage for natural evaluation. Keep all k, history, payload, and seed variants together. Use grouped cross-validation for pilot model exploration and a newly collected held-out set for confirmation. Fit calibration, preprocessing, and feature selection only within development folds.

Report paired contrasts with the number of contributing episodes and families. Seeds are repeated model samples, not new scenario families. Estimate confirmatory sample size from pilot variability for a declared practically meaningful effect; do not promise that 12 or 30 families is automatically enough. Use two-sided interaction tests, identify primary contrasts before running, and treat the remaining menu as exploratory. Retain inconclusive results with their uncertainty; do not infer a well-powered null from a nonsignificant result alone.

## 6. Revised implementation sequence and gates

The following schedule is an effort sequence, not a fixed compute-price or completion-date promise.

| Stage | Work and deliverable | Gate before continuing |
|---|---|---|
| **0 — Existing-data audit** | Recompute action-by-k counts, per-action contrasts, family sensitivity, output truncations, and actual token accounting. Preserve the original artifacts. | Counts reconcile with 128 episodes / 3,456 continuations; distinguish classification from executable outcomes. The counts and 49 abandon-snapshot checks in this document are already verified. |
| **1 — Repair the evaluation instrument** | Build the new action-balanced cases, partial/full-completion pairs, independent specifications, separate outcome measures, and focused checks in §2.3. | Equal action counts at each k; no label changes across matched variants; positive and negative behavior checks work; split and leakage audits pass. This stage blocks the main new mechanism grid. |
| **2 — Output/context calibration** | Replay a fixed diagnostic selection of 24 old episodes (eight families × k1/8/16), P1/P2/P4, caps 400/2,048, seeds 0/1: **288 calls**. Separately smoke-check new contexts. | Report truncation as a separate failure cause and confirm reference outputs/context lengths fit. Do not select only previously failed responses. These old episodes diagnose a budget issue, not the repaired causal hypothesis. |
| **3 — Context pilot** | Run the 2,592-continuation Study A with the repaired instrument and predeclared contrasts. | Verify intended manipulation and report family-sensitive uncertainty before choosing a follow-up. Easy or hard items remain visible rather than being removed after seeing results. |
| **4 — Evidence and semantic studies** | Conduct Study B and the snapshot portion of C, then freeze a candidate policy using development data. | Compare verified outcomes and full cost; require evidence of a useful tradeoff on unseen families. An imprecise effect calls for a precision study, not a deployment claim. |
| **5 — Confirmation** | Measure natural receiver histories, replicate selected contrasts on a second model family, and add live/repeated-write confirmation where relevant. | Freeze hypotheses, split, practical effect sizes, and analysis before collecting confirmation data; report unresolved generalization limits. |

A null or reversal at any stage changes the question rather than obligating another payload variant. If task observability dominates context length, prioritize evidence access. If representation dominates message content, prioritize state refresh. If repeated interference dominates one-step decisions, move toward scheduling. If the refined instrument cannot discriminate informative payloads even on an independently defined challenge subset, narrow the claim to the measured population rather than designing examples solely to produce a gain.

### Future code touchpoints, kept separate from this document change

- Corpus construction belongs in the existing crossover generator, but the historical generator/run must remain reproducible through a retained version or separate entry point. New output directories need unique run IDs.
- Receiver history and output logging belong at the recovery backend/replay boundary. The existing episode model and refusal adapter do not themselves provide faithful receiver-trajectory restoration; that is explicit instrumentation work.
- Outcome validation belongs beside the existing behavioral validator, with additive reporting for route correctness versus verified completion. Version the new metric definition rather than silently changing historical score meaning.
- Use tokenizer-consistent length measurements for all new token controls. Preserve historical word-proxy columns as historical measurements.
- Keep test additions focused on balance, invariance, split isolation, leakage, truncation accounting, and behavioral positive/negative cases. No runtime code, dependency, API, or scoring changes are implemented by this document.

**Immediate next experiment:** after the corpus and scoring checks pass, run the controlled context/stale-history pilot. The label imbalance and abandon ceiling are reasons to improve the evaluation first; they are neither proof that richer communication cannot help nor proof that context length will be the missing predictor.
