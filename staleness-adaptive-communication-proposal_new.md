# Staleness-Adaptive Communication in Asynchronous Multi-Agent Code Generation

**Internal planning and pilot-decision document — v4**
Revised 2026-09-11 · Horizon: ~3 months · Status: Stage-C pilot re-analysed; instrument rebuild required before any confirmatory claim

> **What changed in v4.** A re-analysis of the same Stage-C artifact overturns the v3 reading of its own result. `correct_action` is not held constant across the staleness knob — k1–2 is a pure-`adapt` corpus, k≥8 is a frozen 2/4/2 mix — so the reported P3−P1 band reversal is a composition artifact and **H1, H2 and H3 were never actually tested**. Every payload carrying any content scores 100% on `abandon`, so 38% of the corpus contributes no discrimination while absorbing 38% of the weight in each headline number. Of eight scenario families, six sit at ceiling in the adapt stratum, leaving a family-clustered MDE north of 20 points. Split by action, P2 — reported as tied with P1 — is **+30.6 points on `escalate` and −13.3 on `adapt`**, which is H5's mechanism claim showing up under a payload H5 was never tested with. Receiver contexts run 222–864 tokens, so the payload is 22% of the whole prompt against <1% in a live run. The proposal therefore changes from "test the observed reversal on a natural corpus" to **"rebuild the instrument, then test context length and deference rather than staleness."** Sections 4, 5.2, 5.3b, 7.2 and 10 carry the change.

> **What changed in v3.** The corrected Stage-C experiment is now complete: 8 controlled scenario families × 16 staleness levels × 9 strategies × 3 seeds, using local Qwen3.5-35B-A3B (3,456 recovery continuations). The earlier 100% P3 result is withdrawn because the synthetic winner rationale leaked the ground-truth recovery action and the old substring scorer could be satisfied by comments. The replacement run uses action-free rationales, behavioral validators, protected concurrent-write markers, pre/post-run leakage audits, and episode-clustered inference. It finds no reliable P3-over-P1 crossover and shows that policy-predicted P5 is limited by routing accuracy. The proposal is therefore changed from “build the adaptive protocol after a positive pilot” to “test the observed reversal and routing mechanism on a natural, held-out refusal corpus before making a deployment claim.”

> **What changed from v1.** STORM's implementation is public — [github.com/dreamyang-liu/STORM](https://github.com/dreamyang-liu/STORM), built on the OpenHands SDK, with the Commit0 harness included. The build plan is rewritten around forking it rather than building from scratch, which cuts harness work from ~3–4 weeks to ~1.5–2 and promotes Tier 2 and the second model family from stretch goals to plan. A new **Gate 0** (reproduce STORM's numbers before committing) is now the first milestone, and an unresolved **licensing question** is the top near-term risk. A second system — ATM — has also appeared with a *different* hand-designed refusal payload; it adds a condition (P5) and sharpens the framing rather than displacing it.

---

## 1. One-paragraph version

When multiple LLM agents edit one repository concurrently, a write is refused whenever the writer's view of the code has gone stale. Two systems ship hand-designed refusal payloads — STORM sends content plus a diff plus a stale-dependency list; ATM sends a structured verdict envelope with a refinement hint — and neither design has been adequately ablated. Our controlled pilot returned a null on all six hypotheses, and re-analysis shows that most of that null is an instrument artifact rather than a finding: the staleness manipulation is confounded with the outcome label, 38% of the corpus is saturated at 100% for every informative payload, and eight scenario families leave a minimum detectable effect above 20 points. What does survive is sharper than the original hypothesis. Split by correct action, a one-sentence declared intent (P2) is **+30.6 points on `escalate` and −13.3 on `adapt`** against the STORM baseline, so payload value is action-conditional rather than staleness-conditional. And the receiving agent shows a consistent deference bias: under P1 it adapts on 56 of 72 episodes where it should push back; under P5, the router points to `abandon` on 108 of 165 true-`adapt` continuations and the receiver follows it 90 times. The next study therefore rebuilds the instrument to a calibrated, action-crossed corpus and tests two conditioning variables the pilot held constant — **receiver context length** and **the falsifiability of a directive** — with an adaptive protocol as a conditional deliverable rather than an assumed one.

---

## 2. Why this question, and why now

Two literatures are pointing at each other and neither has noticed.

**The multi-agent communication literature says send more.** Chun and Ahmed's characterization study finds that removing reasoning from inter-agent messages costs up to **18.6%** performance, and removing cross-agent references costs up to **38.7%** in collective-refinement systems. Their diagnosis is that communication is "dominated by answer propagation while reasoning and verification remain underutilized." The latent-communication line pushes harder still, arguing a token channel discards most of what the sender knows — roughly 15 bits per token against ~40,000 bits in a hidden state.

**The context-engineering literature says send less.** *Less Context, Better Agents* finds that pruning an agent's context to the last five tool calls **improves** completion from 71.0% to 79.0% while cutting tokens 63.9%. Its two named failure modes are distraction and — directly relevant — **stale-state reference errors**, where superseded state in context actively degrades the agent's model of the world.

**There is already evidence the effect changes sign.** Work on runtime monitoring of multi-agent reasoning exchange finds that sharing reasoning traces "corrects more errors than it introduces in most cases" — gains as large as 60.34% → 93.10% in one domain — while explicitly identifying cases where **reasoning exchange misleads the receiver toward the wrong answer.** A payload effect whose sign flips, with no characterization of what flips it.

Both literatures are credible and give opposite advice. The resolution is almost certainly that neither is unconditionally right and the conditioning variable has not been isolated. We think it is staleness, and asynchronous code editing is where it can be measured with mechanical ground truth rather than benchmark accuracy deltas.

**The gap is specifically about asynchrony.** The unifying survey of latent communication catalogues 18 methods across a three-axis taxonomy and **assumes synchronous sequential message passing throughout** — buffering, delay, and out-of-order consumption are absent. Chun and Ahmed close by naming "adaptive communication strategies tailored to agent roles and task requirements" as their principal open problem. That sentence is what this proposal is written against.

### 2.1 Two baselines now exist, both with unmeasured payloads

**STORM** applies optimistic concurrency control to a shared agent workspace: reads return a version counter, a write is valid only if no file the agent read has changed since observation, and on refusal the agent gets current content, unified diffs, and a stale-dependency list. It reports 46.2% weighted / 82.5% macro on Commit0-Lite against 24.6% / 63.8% for git-worktree isolation. Its stated limitations are our entry points: file-level granularity causes false-positive refusals, bash writes bypass mediation, and file-level consistency misses semantic conflicts — "two agents might implement the same helper with different signatures."

**ATM** takes the opposite architectural stance: *pre-write admission* rather than post-hoc validation. A CID broker is the sole serialization authority, conflicts are detected at **atom** rather than file granularity, and refused intents are routed through structured recovery paths — queue, serialize, steward review, refine — rather than simply bounced. Its refusal payload is richer than STORM's: verdict label, blocking layer, conflicting CID or ConflictKey, the preserved intent/patch envelope, and a **"refinement hint or recovery route selected by policy."**

That ATM exists is good news, not bad. It is a governance and feasibility paper evaluated on its own bespoke ATM-AdmissionBench (20 scenarios, 42 mode-level comparisons), and it states plainly that its results "support feasibility within observed single-domain settings, but not broad comparative superiority over alternative concurrency-control systems." It does not ablate its payload either. What it gives us is a *second point in the design space* — a directive payload rather than a merely informative one — which we adopt as condition P5 and which turns out to sharpen the central hypothesis considerably (§5.2).

**Human precedent, still under-cited.** Palantír solved this for humans in 2011: it computed conflict severity as non-comment lines changed over total, and distinguished **direct** conflicts (same text) from **indirect** ones (a remote signature change breaking local usage). Awareness cut undetected indirect conflicts from 34 to 8 — but resolving indirect conflicts took developers *1.5 minutes longer* while direct conflicts got 3 minutes faster. Shallow conflicts need content; deep conflicts need understanding; the two have different cost structures. That asymmetry is our hypothesis in human form.

---

## 3. Contribution claims

**C1.** The first ablation of refusal-feedback payload in an asynchronous multi-agent coding system, covering the payload designs shipped by both STORM and ATM.

**C2.** An operationalization of *staleness* separating temporal, semantic, investment and **contextual** components — the last being contradiction load, the share of the receiver's own context that the winning edit has falsified — with evidence on which predicts recovery cost.

**C3.** A leakage-audited, action-stratified, **power-audited** evaluation protocol that distinguishes payload content, token volume, routing quality, oracle direction and instrument sensitivity; followed by either a held-out adaptive policy with measured gains or a well-powered null constraining the "send more reasoning" prior.

**C4.** A characterization of **inter-agent deference** — the receiving agent's prior that a concurrent writer is right — as the mechanism that governs both the under-escalation failure of informative payloads and the catastrophic failure mode of directive payloads, together with a payload design (falsifiable grounds) that bounds its cost.

---

## 4. Research questions and hypotheses

**RQ1.** Does the optimal refusal payload depend on staleness magnitude?
**RQ2.** Which operationalization of staleness best predicts recovery outcome?
**RQ3.** Is any advantage of rich payloads content, or merely token volume?
**RQ4.** Does rich feedback help by improving patch adaptation, or by improving *decisions about whether to adapt at all*?
**RQ5.** Is more *information* what helps, or more *direction*?
**RQ6.** *(new)* Is the conditioning variable staleness at all, or the **signal ratio** of payload tokens to receiver-context tokens?
**RQ7.** *(new)* What governs whether a receiving agent defers to a concurrent writer, and can payload design move it?

| ID | Hypothesis | Current evidence and decision |
|---|---|---|
| **H1** | Recovery quality declines monotonically with staleness under every payload. | **Not testable in the Stage-C corpus.** `correct_action` covaries with k by construction (§7.2), so the k curve mixes a manipulation with a label change. Re-test only on an action-crossed corpus. |
| **H2** | **(core)** The advantage of intent- and reasoning-bearing payloads over content-only increases with staleness. There is a threshold τ\* below which content-only is statistically indistinguishable at lower cost, and above which richer payloads win. | **Not tested.** The reported band reversal (+8.3 at k1–4, −6.2 at k13–16) is reproduced exactly by re-weighting three action cells of differing payload sensitivity. With 8 family clusters the MDE exceeds 20 points, so the null is uninformative. Carries forward to the rebuilt corpus, demoted from core. |
| **H3** | The high-staleness advantage survives a length-matched padded control. | **Premise still not met**, but P1-pad is informative in its own right: 91.5% on `adapt` (tied with P3) and 12.5% on `escalate` (worse than P1's 22.2%). Token volume neither explains P3's adapt performance nor substitutes for intent on escalate. |
| **H4** | Investment staleness predicts recovery cost better than temporal staleness. | **Still untested.** Now competes against contradiction load (§5.3b), which is predicted to dominate all four because k only matters through it. |
| **H5** | **(mechanism)** Intent/rationale-payload benefit concentrates in episodes where the correct action is *abandon* or *escalate*, not *adapt*. | **Tested with the wrong payload; supported by P2.** P3−P1 was 0.0/+1.8/+4.2 and recorded as not established. P2−P1 is **−13.3 on `adapt` and +30.6 on `escalate`**. Declared intent buys willingness to push back and costs adaptation fidelity. Rests on one family (`authorization`), so it is a lead to power, not a result. |
| **H6** | **(directive test)** A route predicted from observable episode state (P5) matches or beats P3 at high staleness for fewer end-to-end tokens. | **Rejected for the current router**, and the failure mode is now characterized: the router predicts `abandon` for 108 of 165 true-`adapt` continuations, and the recovery agent follows it into 90 abandonments. The bottleneck is routing *and* the receiver's uncritical compliance with it. |
| **H7** | **(new, core)** The conditioning variable is the **signal ratio** `payload_tokens / context_tokens`, not k. Rich payloads lose their advantage and then invert as receiver context grows; τ\* is measured in context tokens. | **Untested — Stage C held it constant.** Prompts ran 222–864 tokens, putting P1 at 22% of the whole context against <1% in a live run. P4's −12.0 points at a 29% ratio is dilution already biting at miniature scale. Primary target of Study S1. |
| **H8** | **(new, mechanism)** A directive carrying **falsifiable grounds** is no better than a bare directive when it is right, and materially better when it is wrong, because grounds let the receiver detect the contradiction. | **Untested.** Current P5 succeeds in 94.7% of correctly routed and 16.4% of misrouted cases; H8 predicts grounding lifts the second number without moving the first. Primary target of Study S2. |
| **H9** | **(new, systems)** An execution-grounded router — running A's behavioural check and A's dependent tests against B's content — beats a predictive router on accuracy and on end-to-end tokens. | **Untested.** Reframes RQ5 from information-versus-direction to **prediction versus verification**, which is the question a code setting is uniquely able to answer. |

The two mechanism questions are now one. When the correct move is "adapt my patch to the new shape," the diff may already contain what is needed; when it is "stop, the other agent implemented this" or "push back, that broke an invariant I was maintaining," the diff is ambiguous — and the receiving agent resolves ambiguity by deferring. Under P1 it chose `adapt` on 56 of 72 episodes whose correct action was `escalate`; under P5-oracle it escalated 72/72, so this is disposition, not capability. Under P5 it followed the predicted route 90.1% of the time regardless of correctness. **Informative payloads fail to overcome deference; directive payloads weaponize it.** That single mechanism, not payload richness, is what the next studies are built to measure.

---

## 5. Experimental design

### 5.1 Setting

Commit0-Lite: 16 Python repositories, implement missing code until existing tests pass. Chosen because STORM's numbers are on it and its code ships the harness, so the baseline is comparable by construction rather than by approximation. Four engineer agents plus one manager, matching STORM's configuration.

### 5.2 Independent variable 1 — payload condition

| ID | Payload | Origin / notes |
|---|---|---|
| **P0** | Bare refusal: "Write rejected, stale read on `{file}`." | Floor. Isolates the value of *any* information. |
| **P1** | Current content + unified diff + stale-dependency list. | **= STORM's shipped behavior. The baseline that matters.** |
| **P2** | P1 + winning agent's declared intent (1–2 sentences, emitted once at write time). | Cheap: written once, reused by every refused reader. It must not contain a recommended recovery action. |
| **P3** | P1 + a structured rationale for the winning edit, capped at N tokens and captured when that edit is made. | Must explain the edit without naming adapt/abandon/escalate, exposing evaluator fields, or using a rationale selected from the later ground-truth recovery label. |
| **P4** | P1 + winning agent's full task assignment and recent trajectory. | Ceiling. Expected to suffer dilution. |
| **P5** | P1 + a policy-predicted recovery route and one-line hint. The controlled vocabulary is adapt / abandon / escalate; queue / serialize will be added only when the corpus has mechanically labeled examples. | **Modeled on ATM.** The policy sees only observable episode state; it never sees the ground-truth action, winner rationale, or evaluator metadata. |
| **P5-oracle** | P1 + the ground-truth recovery route and oracle hint. | Diagnostic upper bound only. Never include it in deployment comparisons or describe it as P5 performance. |
| **P1-pad** | P1 padded with conflict-irrelevant repo text, token-matched to P3. | **Control for H3.** |
| **P6** | P1 + a recovery route **plus the falsifiable ground for it** — the symbol, file and line that justify the route. | **New. Tests H8.** Run with route correctness *injected* rather than predicted, so the router is off the critical path. |
| **P7** | P1 + one sentence granting the agent explicit standing to reject a peer's change. No episode content, no routing call, ~15 tokens. | **New. Tests whether under-escalation is disposition rather than information deficit.** |
| **P8** | P1 + a route computed by **execution**: run A's intended behavioural check against B's content (passes → abandon); run the tests A depends on (breaks → escalate); otherwise adapt. | **New. Tests H9.** One sandbox run per refusal, no LLM routing call. |

Two comparisons carry most of the practical weight. **P2 vs P3** asks whether the edit rationale adds value beyond declared intent. **P3 vs policy-predicted P5** is the information-versus-direction question. P5's cost must include its routing call; in the corrected pilot it was more expensive end to end than P3, so compact payload length alone is not a valid efficiency claim. **P5-oracle vs P5** isolates route-selection error and is a mechanism diagnostic, not a fair strategy comparison.

Three comparisons are added in v4. **P6 vs P5 under injected wrong routes** is the H8 test and the single most informative contrast available, because it measures whether a payload can be wrong *safely*. **P7 vs P1** asks whether the 78% under-escalation rate is an information problem at all. **P8 vs P5** asks whether the routing bottleneck should be predicted or simply computed; its cost accounting must include sandbox execution time, which is wall-clock rather than tokens.

The original pilot's P3 construction is invalidated and must not be reused: the rationale was selected from `correct_action` and directly named the desired recovery route in every P3 example. Future data generation has a mandatory pre-run schema/lexical leakage audit and a post-run audit of the exact prompts received by the model.

### 5.3 Independent variable 2 — staleness

Primary knob is **edit-distance staleness**: buffer the refused agent's notification until *k* other writes have landed. The corrected mechanism pilot used every integer k ∈ {1,…,16} to search for a crossover without interpolation. The natural-corpus study will pre-register a smaller set of bins from the observed distribution rather than extend synthetic k further. Edit distance is chosen over wall-clock because it is model-speed-invariant and exactly reproducible under replay; a secondary temporal arm (τ ∈ {0s, 30s, 2min}) checks external validity.

Every episode additionally records all three natural measures, so H4 is testable observationally inside the injected design:

- **s_temporal** — seconds from A's last read of the conflicting file to refusal.
- **s_semantic** — Palantír's severity metric (non-comment lines changed / total non-comment lines in A's read set), plus a binary for whether changed symbols intersect symbols A referenced. Reproduces Palantír's direct/indirect distinction.
- **s_invest** — tokens generated and tool calls issued by A between that read and the refused write.
- **s_contradiction** *(new)* — tokens in A's own context that the winning edit has falsified: quoted file content, signatures of symbols A referenced, assumptions in A's stated plan. Reported absolutely and as a fraction of context.

### 5.3b Independent variable 3 — receiver context length

Stage C held this constant without intending to. Receiver prompts ran **222–864 tokens (median 581)** against a 126-token P1 payload, so the payload was **22% of the entire prompt**; in a live STORM run the receiving engineer holds 15k–100k tokens and the same payload is under 1%. The pilot therefore measured a signal-to-noise regime that cannot occur in deployment — and specifically the regime in which the context-degradation literature predicts no dilution at all. P4's −12.0 points at a 29% ratio is that mechanism already biting at miniature scale.

`L ∈ {1k, 8k, 32k, 128k}`, manipulated by padding **the receiver's own trajectory** — realistic prior tool calls, reads and partial edits — never the payload, which would reintroduce the P1-pad confound. A nested arm varies the **position** of the refusal in that trajectory (head / middle / tail): asynchronous notification means a refusal can arrive buried under later tool calls, which is a lost-in-the-middle question that only exists in the asynchronous setting.

H7 is the `payload × L` interaction. It replaces H2 as the core pre-registered test.

### 5.4 Two-tier structure (what makes 3 months possible)

A naive grid — ten payloads × four levels × seeds, each a full multi-agent run — is unaffordable. STORM reports **$199–$429 per configuration** and ~13 hours wall-clock for 16 repos.

**Tier 1 — Episode replay. Large N, cheap, primary instrument.** Harvest a *refusal episode corpus* from natural runs. Each episode snapshots: repo state at A's read, repo state at refusal, A's full trajectory and context, B's edit with intent and reasoning trace, and all three staleness measures. Then replay only the recovery — restore A's context to the instant of refusal, inject payload P_i, continue until A produces a next write attempt or gives up (cap ~20 iterations). Each cell becomes one ~15k-in / 3k-out continuation. Target corpus: **250–300 episodes.**

**Tier 2 — End-to-end live runs. Small N, validity check.** Full sessions on 6 Commit0-Lite repos under three conditions: P1, the Tier-1 winner, and the adaptive policy. Confirms Tier-1 rankings move repo-level pass rate and wall-clock. **Now planned rather than stretch,** thanks to the harness time freed by forking STORM.

**Stated limitation, up front:** Tier 1 measures immediate recovery quality, not the counterfactual end-to-end outcome, because a changed decision cannot be cheaply propagated forward through the rest of a session. Tier 2 exists to test whether that shortcut is safe. Tier-1-only claims must be scoped to recovery quality.

### 5.5 Dependent variables

**Primary (mechanical, no judge):**

- *Recovery success* — correct coordination action plus action-specific validation. For adapt, the revised file must parse, preserve every intervening concurrent edit, and pass isolated behavioral checks. For abandon/escalate, success requires the correct non-write terminal action and no repeat write. Substring or comment-presence checks are prohibited. (Tier 1)
- *Repo pass rate* — Score_w and Score_macro, STORM's definitions, for direct comparability. (Tier 2)

**Secondary:**

- *Recovery cost* — tokens and tool calls from refusal to accepted write.
- *Repeat-refusal rate* — fraction of episodes whose recovery write is *also* refused. Direct measure of feedback sufficiency; expected to be where P0 collapses.
- *Action-type correctness* — adapt / abandon / escalate against a rubric. Tests H5.
- *Redundant implementation rate* — two agents implement the same symbol with different signatures. STORM's named unsolved failure; a payload that reduces it is a concrete win.
- *Net efficiency* — Cost_eff and Time_eff, STORM's definitions.
- *Deference rate* **(new)** — the fraction of episodes in which the recovery agent takes the action the payload points at, reported separately for correct and incorrect directives. Under Stage-C P5 this was 90.1% irrespective of correctness. This is the primary DV for H8 and the direct measure of C4.
- *Contradiction-detection rate* **(new)** — the fraction of misrouted episodes in which the agent explicitly contests the directive rather than complying. Zero under bare directives; H8 predicts it is non-zero under P6.

### 5.6 Confound controls

1. **Token volume** → P1-pad, length-matched to P3.
2. **Difficulty ↔ staleness confound** → staleness is *injected*, not observed; design is within-episode paired, so episode difficulty is held constant by construction.
3. **Ground-truth leakage and scorer gaming** → recovery labels, oracle hints, and evaluator fields are excluded from model-visible prompts; P3 action words are audited before and after the run; adapt outputs are independently rescored with AST and behavioral validators. The LLM judge, if used on natural episodes, labels action type only, is blind to condition, and is validated against ~100 human-labeled episodes with reported agreement.
4. **Model idiosyncrasy** → full grid on two model families. STORM uses **LiteLLM identifiers**, so a local vLLM OpenAI-compatible endpoint drops in with a config change — this arm is now cheap to add, which is the main reason it moves from stretch to plan.
5. **Order effects** → randomized episode presentation, seeds recorded.
6. **Action-mix ↔ staleness confound** → **this is the defect that invalidated Stage C, not a residual risk.** The next corpus crosses action with staleness by construction: every scenario family supplies `adapt`, `abandon` and `escalate` at every staleness level. Aggregate k curves are not reported until this holds.
7. **Item saturation** → pilot every candidate episode under P1 and admit only those with success in the **30–70%** band and non-zero within-family variance. Stage C carried five ceiling families and one floor family out of eight; standard item analysis is worth more here than doubling N.
8. **Cluster count** → ≥30 scenario families, ≥10 clusters per action cell. Staleness levels are nearly free statistically; families are the inference units.
9. **Context-scale realism** → no arm below an 8k receiver context, since 581 tokens is not the deployment regime and silently determines the payload's share of attention.

### 5.7 Statistical plan

The inference unit is the **episode**, not the continuation seed. Seeds are averaged within episodes, and episode outcomes are clustered on scenario family. Report paired payload-minus-P1 differences using family-clustered bootstrap intervals and family-clustered sign-randomization p-values. Do not treat the three seeds as three independent episodes.

For the larger natural corpus, use within-episode paired mixed-effects models:

```
recovery_success ~ payload * staleness + (1 | episode) + (1 | repo)      # logistic
recovery_cost    ~ payload * staleness + (1 | episode) + (1 | repo)      # linear
```

H2 is the **payload × staleness interaction term**, pre-registered before the natural-corpus grid. Any τ\* selected on the development corpus must be evaluated on held-out episodes; a threshold optimized and reported on the same corpus is exploratory only. H4 compares model fit across staleness operationalizations. H6 is a planned contrast between **policy-predicted** P5 and P3 at high staleness, with end-to-end token cost including the P5 routing call. P5-oracle is reported separately as an upper bound.

**Power is now a pre-registered deliverable, not an assumption.** Stage C's nominal 128 episodes were 8 scenario families × 16 staleness levels; with family-clustered inference the effective cluster count was 8, and 2 for the `escalate` cell. The action-level planning MDE is 37.3 points for `adapt` and 57.5 for `escalate`; it is not empirically estimable for the saturated `abandon` baseline. These are larger than any effect the design was built to find, which is why its null is uninformative. Every subsequent run states its MDE before execution, computed from Stage C's observed between-family variance, and reports the realised cluster count per action cell alongside every contrast.

With ~30 calibrated families crossed over three actions, a 10-percentage-point paired difference becomes detectable. Retiring the saturated `abandon` variants recovers a further 38% of effective weight that Stage C spent on cells where every informative payload ties at 100%.

### 5.8 Feature set for recovery-action prediction

Grouped so the ablation is interpretable. Used by S3 to establish the routing ceiling and by P8 to decide what is worth computing rather than predicting.

**Staleness (current)** — k; `s_temporal`; `s_semantic` (Palantír severity); symbol-overlap binary; `s_invest` in tokens and tool calls.

**Context (new, §5.3b)** — receiver context length; signal ratio; contradiction load, absolute and as a fraction of context; position of the stale content in the trajectory; prior refusals in this episode; turns since A's last read.

**Task semantics (new)** — symbol-level overlap between A's assignment and B's edit; **subsumption score**, whether B's edit already satisfies A's stated task; **invariant-violation score**, whether B's edit breaks a property A's code or tests assert; test-file overlap.

**Repo graph** — dependency distance between A's file and B's file; whether the changed symbol is in A's read set; fan-in of the changed symbol; whether it is a signature change, which is Palantír's indirect-conflict case.

**History** — A's prior refusal count; whether A has already adapted once in this file; manager assignment overlap.

**The design consequence:** two of these features *are* the labels. `abandon` ⟺ subsumption, `escalate` ⟺ invariant violation. So the target is not a general classifier but two detectors, and in a code setting both are **executable rather than predictable** — which is the argument for P8 and the reason RQ5 is restated as prediction versus verification.

---

## 6. Build plan — fork STORM

**Recommendation: yes, fork it.** Rebuilding reproduces someone else's design decisions with less fidelity, no comparability, and three extra weeks spent on infrastructure that is not the contribution.

### 6.1 What the repo gives you

Verified from the repository and its README:

- Python ≥3.12, `uv`, Docker; `bash setup.sh` installs deps and builds images.
- Built on the **OpenHands SDK** (vendored as `software-agent-sdk/`).
- Three entry points: `scripts/run_single.sh`, `run_multi.sh`, `run_batch.sh`.
- Configurable task type (commit0 / paperbench), model, subagent count, iteration limits, communication rounds.
- **Commit0 harness included** — dataset from HuggingFace to `STORM/data/commit0/commit0_combined_disk/`; outputs cost breakdowns, runtimes, event logs, and pytest results to `outputs/<task>/<model>/<identifier>/`.
- **LiteLLM model identifiers** — OpenRouter and DashScope configured; any OpenAI-compatible endpoint (i.e. local vLLM) works by configuration.

The versioned file store, write validation, manager/engineer roles, task decomposition, and evaluation all come free. **Event logs in particular are close to the episode logger we would otherwise have written.**

### 6.2 Health assessment — read this before committing

The repo is a fresh research artifact, not a maintained library: **6 stars, 0 forks, 8 commits on `master`.** Expect rough edges, thin documentation beyond the README, and no responsiveness guarantee. Two consequences:

- **No license is specified.** Absent a license, default copyright applies and you have no grant to modify or redistribute. For an internal experiment this is a low practical risk; for anything you publish, release, or build a public artifact on, it is a real one. **Open an issue or email the authors in week 1, not week 6.** Authors: Mengyang Liu, Taozhi Chen, Zhenhua Xu, Xue Jiang, Yihong Dong.
- **Reproduce before you build.** See Gate 0.

### 6.3 What you still build

| Component | Description | Est. |
|---|---|---|
| **Payload strategy interface** | A seam at the refusal site so P0–P8 are swappable by config. This is the natural extension point; STORM already assembles a payload there. | 2–3 days |
| **Episode logger** | Extend the existing event log to a full replayable snapshot at each refusal. | 2–3 days |
| **Replay driver** | Restore agent context to a snapshot, inject payload, continue, capture outcome. **Still the hardest piece and the one most likely to overrun** — faithful context restoration is fiddly and getting it wrong silently invalidates Tier 1. | ~1 week |
| **Staleness scheduler** | Buffer notifications by k intervening writes; temporal arm. | 2–3 days |
| **Intent/reasoning capture** | Require a structured intent on write; retain the trace. | 1–2 days |
| **Context-length harness** *(new, v4)* | Pad the receiver's trajectory to a target `L` with realistic prior tool calls and reads, and place the refusal at a chosen position. Unblocks S1 and the position arm; must never pad the payload. | 3–4 days |
| **Item calibrator** *(new, v4)* | Pilot each candidate episode under P1, score it, and admit only 30–70% items with non-zero within-family variance. Reports realised cluster counts per action cell. | 2–3 days |
| **Execution router for P8** *(new, v4)* | Run A's behavioural check and A's dependent tests against B's content in the existing sandbox and emit a route. | 4–5 days |
| **Contradiction-load meter** *(new, v4)* | Diff the winning edit against A's context and count falsified spans — quoted content, referenced signatures, plan assumptions. | 2–3 days |
| **Bash mediation** *(optional)* | Close the write path STORM lists as bypassing its mediation layer. | 4–5 days |

**Estimate: ~1.5–2 weeks to the original instrumented pilot, plus ~2 weeks for the v4 additions.** The v4 components are not new scope in the discretionary sense — the context-length harness and the item calibrator are what make any subsequent number interpretable, and §7.2 is the evidence for that. The execution router is the one genuinely optional item; defer it if Gate S3 kills predictive routing outright, since P8 then has no competitor worth beating.

---

## 7. Timeline and gates

**Week 1 · Stage 0 — Reproduce and de-risk. (New, and the most important addition in v2.)**
Set up the fork, run `run_multi.sh` on 3 Commit0-Lite repos, and attempt to reproduce STORM's reported figures. Simultaneously open the licensing question with the authors.

> **Gate 0.** Multi-agent must beat single-agent on the 3-repo subset, in the direction and rough magnitude STORM reports (46.2% vs 20.7% weighted). If the baseline does not reproduce, you do not have the baseline you think you have — and every downstream number is uninterpretable. Fall back to reimplementing the mediation layer only (~300 LOC; the OCC idea is simple even if the system is not) and accept looser comparability. **Do not skip this gate to save a week.**

**Weeks 1–3 · Stage A — Observational analysis on AgenticFlict.** Runs in parallel, no harness needed. 29,609 conflicting agent PRs, 336,380 conflict regions, 59,412 repositories, public on Zenodo under CC-BY-4.0. Characterize the empirical distribution of conflict severity and locality; estimate what fraction of real agent-agent conflicts are high-staleness restructuring versus low-staleness local edits.

> **Gate A.** If under ~10% of real conflicts are high-severity or non-local, the crossover has little practical headroom. Narrow the claim, or pivot to the observational study as the standalone deliverable.

**Weeks 2–4 · Stage B — Instrumentation.** (Was weeks 2–6.)

> **Gate B.** ≥30 refusal episodes per wall-clock hour across 3 repos. Below that, cut to 4 payload conditions (P0, P1, P3, P5) and 2 staleness levels.

**Weeks 4–6 · Stage C — Controlled pilot grid, local model. COMPLETE 2026-09-09.**

> **Gate C decision.** The corrected 128-episode / 3,456-continuation pilot found P3 82.6% versus P1 81.0% (paired +1.6 points; 95% episode-clustered bootstrap interval −2.6 to +5.7; p=0.510) and no consistently positive P3−P1 crossover. The best same-corpus P1→P3 threshold was k=1—equivalent to always using P3—and the best P1→P5 threshold was k=17—equivalent to never using P5 over the tested k=1…16 range. **Decision (v3): do not claim H2, do not deploy an adaptive policy from these data, and do not spend the next budget merely extending synthetic k.** **Amended in v4 (§7.2): the band reversal that this gate treated as a confirmatory target is a composition artifact, so it is withdrawn as a target. The corpus itself must be rebuilt before any payload claim — natural or synthetic — is interpretable.**

The earlier P0-vs-P3 gate was not diagnostic of H2: P0 is an information-deprived floor and cannot establish that P3 beats the meaningful STORM baseline P1 as staleness grows. Gate C is therefore evaluated with paired P3−P1, P1-pad, P4, and policy-predicted P5 contrasts.

**Weeks 1–2 · Stage C′ — Instrument rebuild.** Item-calibrate candidate episodes under P1 to a 30–70% band; build ≥30 families with action fully crossed against staleness; raise the minimum receiver context to 8k. Runs concurrently with S3, which needs no GPU.

> **Gate C′.** ≥10 family clusters per action cell, and ≥60% of admitted items landing in the 40–70% P1 band. Below either, the corpus is not an instrument and no payload contrast is run on it.

> **First Gate C′ attempt (2026-09-11): FAIL.** A mechanically audited set of 38
> families fully crossed `adapt` / `abandon` / `escalate` at k=8 and was piloted
> under P1 for 10 seeds at exactly 8k receiver-trajectory tokens (1,140
> continuations). There were 59 malformed/truncated JSON responses; the strict
> ledger excludes any affected item rather than counting malformed output as an
> ordinary model failure. Only 10 items were admitted; family clusters by action
> were `adapt=1`, `abandon=1`, `escalate=8`. Although 80.0% of admitted items
> landed in the 40–70% band, the ≥10-per-action requirement failed. Accordingly, Study
> S1 was not run. Artifacts and the item-level exclusion ledger are in
> `corpus_rebuild/p1_qwen35_8k_20260911_r1/`.

> **Held-out Gate C′ attempt (2026-09-11): FAIL.** The receiver-trajectory
> renderer was first corrected so task and pending-edit content appears once and
> only neutral tool history fills the requested context. Revision r4 was frozen
> after seeds 0–2 and evaluated once on held-out seeds 10–19: 1,140/1,140 valid
> continuations at exactly 8k tokens. It admitted 21 items, with 76.2% in the
> 40–70% band, but clusters were `adapt=9`, `abandon=2`, `escalate=10`. The
> action-cell threshold still fails, so no S1 payload contrast was run. Artifacts
> are in `corpus_rebuild/p1_qwen35_8k_20260911_r4_heldout/`; those responses must
> not become another development set.

**Weeks 1–4 · Study S3 — RecoveryRoute-Bench on AgenticFlict.** *No GPU; fully parallel.* Mine PR resolutions across the 336,380 conflict regions into `abandon` / `adapt` / `escalate` labels — losing change dropped, rewritten onto the new base, or reverted and contested. Fit the §5.8 feature set; report the achievable routing-accuracy ceiling, a feature-group ablation and a human upper bound on a hand-labelled subset.

> **S3 reconstruction checkpoint (2026-09-11).** Repository histories are
> available for 53/55 merged conflicting PRs (16/17 repos; 10,348/10,359 file
> records), and every referenced base/head/merge commit in those repositories was
> recovered. The resolved tree is exact-base for 99 records, exact-head for 7,879,
> manual/combined for 132, unchanged for 16, and absent on all three sides for
> 2,222. These are provenance signals, not route outcomes. A balanced 30-item
> adjudication sheet is ready in `recovery_route_bench/`; Gate S3 and model fitting
> remain pending independent labels from resolved diffs plus PR discussion/reverts.

> **Gate S3.** If the ceiling falls below the ~82.5% break-even, predictive directive routing is dead on arrival. Drop P5 as a deployment candidate and redirect the budget to P6 (survivable wrong directives) and P8 (verification).

**Weeks 3–5 · Study S1 — Context × Payload.** `L ∈ {1k, 8k, 32k, 128k}` × `{P1, P2, P3, P6, P7}` × 30 rebuilt families × 3 actions, staleness fixed at a mid value. Primary: the pre-registered `payload × L` interaction (H7). Secondary: contradiction load as a continuous predictor; payload position as a nested arm.

**Weeks 6–8 · Study S2 — The deference benchmark.** Injected route correctness × {bare, grounded, hedged} × receiver evidence strength. Primary DV is deference rate alongside recovery success; the output is a trust-calibration curve. P7 rides along as a cheap side arm.

**Weeks 9–11 · Stage E — Tier 2 end-to-end confirmation on 6 repos,** on whichever condition won.

**Weeks 11–12 · Stage F — Held-out analysis, adaptive-policy prototype only if H7 or H8 holds, writeup.**

### 7.1 Stage-C result record

| Finding | Corrected local-Qwen result | Interpretation |
|---|---:|---|
| P3 vs P1 | 82.6% vs 81.0%; +1.6 points [−2.6, +5.7], p=0.510 | No reliable overall reasoning-rationale benefit. |
| P3−P1 by k band | +8.3 (k1–4), +8.3 (k5–8), −4.2 (k9–12), −6.2 points (k13–16) | Descriptive reversal, not a confirmed crossover; band cells contain few family clusters. |
| P1-pad vs P1 | 79.9% vs 81.0% | Matching P3's length does not produce its small observed gain. |
| P4 vs P1 | 69.0% vs 81.0%; −12.0 points [−17.7, −6.8], p=0.0001 | Extra trajectory context can actively hurt; “richness” is not a scalar. |
| P5 vs P3 | 62.2% vs 82.6% | The current predicted directive is not competitive. |
| P5 route quality | 58.6% router accuracy; 94.7% recovery success if correct, 16.4% if wrong | Routing error dominates P5. |
| P5-oracle | 98.7% success | Correct direction is sufficient in these fixtures, but this is a non-deployable upper bound. |
| Adaptive (threshold k=4) vs P1 | 69.0% vs 81.0% | The current adaptive composition is worse than fixed P1 and should not be deployed. |

The complete result, raw prompts/responses, audits, tables, and rerun command are in [`STORM/STORM/crossover_experiment_qwen35_leakage_safe_k16_20260909/`](STORM/STORM/crossover_experiment_qwen35_leakage_safe_k16_20260909/). Reproduce it with:

```bash
cd /home/wentao/Asyn_agent/STORM/STORM
bash crossover_experiment_qwen35_leakage_safe_k16_20260909/run_command.sh
```

Cost comparisons remain provisional: the controlled fixtures already contained the P3 edit rationale, so the cost of generating that rationale is not included, whereas P5's extra routing call is included. The success comparison is still valid within the fixtures; the end-to-end cost comparison needs natural write-time rationale capture.

### 7.2 Stage-C re-analysis — why the null is mostly an instrument artifact

Recomputed from `replay_results.csv` on 2026-09-11. Published as a working page at [the Stage C post-mortem](https://claude.ai/code/artifact/ce30e301-8320-4950-9ee7-e196e4a9052c), which also carries the shared work board for the items below.

**1 · The staleness knob is the outcome label.** `correct_action` is not held constant across k:

| k | adapt | abandon | escalate |
|---|---:|---:|---:|
| 1–2 | 8 | 0 | 0 |
| 3 | 7 | 1 | 0 |
| 4 | 5 | 2 | 1 |
| 5 | 4 | 3 | 1 |
| 6 | 3 | 3 | 2 |
| 7 | 2 | 4 | 2 |
| **8–16** | **2** | **4** | **2** |

Low k is a pure-`adapt` corpus and high k is half-`abandon`, so the reported P3−P1 band reversal is reproduced by re-weighting three action cells of differing payload sensitivity. From k=8 the composition never changes again: nine of sixteen levels are the same eight episodes with the same labels, making them replicates rather than staleness levels.

**2 · 38% of the corpus cannot discriminate.** Success by payload × correct action:

| Payload | adapt | abandon | escalate |
|---|---:|---:|---:|
| P0 | 0.0% | 0.0% | 0.0% |
| P1 | 89.7% | **100.0%** | 22.2% |
| P2 | 76.4% | **100.0%** | **52.8%** |
| P3 | 91.5% | **100.0%** | 26.4% |
| P4 | 62.4% | **100.0%** | 20.8% |
| P1-pad | 91.5% | **100.0%** | 12.5% |
| P5 | 27.3% | **100.0%** | 65.3% |
| P5-oracle | 97.0% | 100.0% | 100.0% |

Every payload carrying any content ties at 100% on `abandon` — 49 of 128 episodes contributing no discrimination while absorbing 38% of the weight in each headline number. The live cell is `escalate`, which is also the smallest at 24 episodes from two families.

**3 · The effect the aggregate hid.** P2 was reported as tied with P1 at 81.0%. Split by action it trades: **escalate 22.2% → 52.8% (+30.6), adapt 89.7% → 76.4% (−13.3)**. That is H5's mechanism claim under a payload H5 was not tested with. The caveat is severe — `escalate` exists only in `authorization` and `transaction`, and `transaction` is 0/33 for every non-P5 strategy, so the entire signal is `authorization` (P1 16/39, P2 38/39, P3 19/39, P1-pad 9/39). One cluster. A lead to power, not a result.

**4 · Most items have no discriminative power.** At P1 within the adapt stratum: `deduplication` 48/48, `pagination` 48/48, `serialization` 18/18, `formatting` 12/12, `normalization` 9/9, and `cache` 6/6 — six ceiling families; `transaction`-escalate is 0/33 for every non-P5 strategy. Roughly two of eight families carry the adapt variance, which is what puts the action-level MDE above 20 points.

**5 · Context scale is wrong by ~40×.** Prompts ran 222–864 tokens (median 581) with a 126-token P1 payload — 22% of the whole context, against under 1% in a live run. See §5.3b.

**6 · What survives: deference.** Under P1, on episodes whose correct action was `escalate`, the model chose `adapt` **56 of 72 times**; under P5-oracle it escalated 72/72, so this is disposition, not capability. Under P5 the router predicted `abandon` for 108 of 165 true-`adapt` continuations and the recovery agent abandoned **90** of them — discarding work P1 recovered 89.7% of the time. One bias, two manifestations: the receiving agent's prior is that the other agent is right.

### 7.3 Immediate re-analysis actions

| ID | Action |
|---|---|
| W1 | Recompute every payload contrast split by `correct_action`, over family clusters, with the MDE stated. |
| W2 | Issue an errata against the Gate C decision recording the k↔label confound, the `abandon` saturation and the 8-cluster MDE. |
| W3–W4 | Item-calibrate and rebuild the corpus to the §5.6 spec. |
| W5 | Add the context-length knob `L` to the replay driver (pad the receiver trajectory, never the payload). |
| W6–W8 | Implement P6, P7 and P8 behind the existing payload strategy interface. |
| W9–W10 | Build RecoveryRoute-Bench and report the routing ceiling. |

### Honest assessment

Forking still makes 3 months workable rather than merely optimistic, but v4 spends the slack differently than v3 intended. Two weeks now go to the instrument rather than to extra arms, because §7.2 shows what an uncalibrated corpus costs: a complete grid, 3,456 continuations, and a headline result that turned out to be a re-weighting of its own label distribution. That is the cheapest version of that lesson we were going to get.

The realistic downside outcome is now stronger than v3's. S3 is fully independent of the harness, needs no GPU, and answers a question that stands alone — whether recovery-action routing is learnable at all from observable state, at a scale of 336,380 real conflict regions rather than 128 fixtures. If everything downstream stalls, that plus the Stage-C methodology post-mortem is still a defensible paper about how not to measure inter-agent communication.

One thing to hold onto: the most interesting number in Stage C — P2's +30.6 points on `escalate` — was invisible in the aggregate and rests on a single scenario family. Both halves of that sentence are the lesson.

---

## 8. Budget

**API inference**

| Item | Estimate |
|---|---|
| Gate 0 reproduction, 3 repos | $50–120 |
| Corpus generation (~6 repos, several runs) | $300–600 |
| Corpus calibration — pilot ~600 candidate episodes under P1 to admit ~300 | ~$60 |
| Study S1 — 30 families × 3 actions × 5 payloads × 4 context lengths × 3 seeds, long contexts dominating | ~$900 |
| Study S2 — deference grid, injected route correctness | ~$400 |
| Study S3 — AgenticFlict analysis | **$0 API** (CPU only) |
| Tier 2 — 6 repos × 3 conditions × 2 seeds | $150–350 |
| Pilots, re-runs, failed configurations | 2× reserve |
| **Total** | **~$2,500–4,200** |

The two-tier structure is what produces this number; a single-tier design over the same grid is roughly an order of magnitude more. The v4 additions are cheap where it matters: S3 costs no API budget at all and gates the most expensive downstream arm, and P7 is effectively free. The one real increase is S1, where 32k and 128k receiver contexts dominate token spend — which is the price of testing H7 at a scale that resembles deployment.

**Local GPU.** The open-weight arm needs a coder model strong enough for non-trivial agent behavior — Qwen-class at 32B+ under vLLM. Below that, agents fail for reasons unrelated to payload and the experiment measures nothing. LiteLLM configuration makes the integration itself trivial.

**Wall-clock is the binding constraint, not dollars.** STORM needed ~13 hours for 16 repos with 4 agents. Corpus generation is the bottleneck; replay is cheap and parallel.

---

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **STORM's licensing is unresolved.** No license file; default copyright applies. | **High (near-term)** | Contact authors week 1. If no grant: keep the fork private and internal, or fall back to a clean-room mediation layer. Never publish an artifact built on it without written permission. |
| **Baseline fails to reproduce.** 8 commits, 6 stars, 0 forks — untested by anyone outside the authors. | **High** | Gate 0, week 1, before any dependent work. Fallback path specified. |
| **Too few refusal episodes.** A well-partitioning manager makes conflicts rare — exactly Co-Coder's thesis (+14.0% pass rate, 2.10× speedup, conflicts "avoided by construction"). | High | Deliberately overlapping assignments as a *documented manipulation*, reported separately from natural-assignment runs with the external-validity caveat stated. |
| **Effect too small or non-monotone.** | High | Gate C found no reliable overall P3−P1 effect. Use an action-crossed corpus, clustered uncertainty, and a pre-registered interaction rather than assuming a monotone crossover. |
| **The instrument cannot detect the effect it was built to find.** Stage C ran at an MDE above 20 points on 8 clusters, with 38% of episodes saturated. | **High — realised once already** | State the MDE before every run; item-calibrate to a 30–70% P1 band; ≥10 clusters per action cell; retire saturated variants. A null is only reportable alongside its MDE. |
| **The manipulation is confounded with the outcome label.** `correct_action` covaried with k throughout Stage C. | **High — realised once already** | Cross action with staleness by construction and verify the crossing before inference, not after. Treat any aggregate curve over an uncrossed corpus as uninterpretable. |
| **Results are a Qwen alignment artifact, not an agent property.** Deference and directive over-compliance are exactly the behaviours RLHF shapes. | **High** | Second model family before the confirmatory run, chosen from a different post-training lineage. If deference does not replicate, the contribution reframes to a model property and says so. |
| **P6/P7 leak the desired action through framing rather than content.** | Medium | The same pre/post-run prompt audit as P3, extended to check that the standing sentence in P7 is episode-independent and identical across all episodes. |
| **Replay infidelity** silently invalidates Tier 1. | High | Validate by replaying with the *original* payload and confirming the original action reproduces above a threshold rate. Report that rate. |
| **Payload leaks the desired action or scorer rewards surface strings.** | **High** | Mandatory pre/post-run prompt audit; P3 rationale independent of recovery labels; isolated AST/behavioral validation; independently rescore saved outputs. The superseded pilot demonstrates that this failure can reverse the conclusion. |
| **ATM or a follow-up runs the ablation first.** | Medium | ATM is a governance/feasibility paper on a bespoke benchmark that disclaims comparative superiority — it is not positioned to ablate. Monitor, but do not redesign around it. Our differentiator is the staleness interaction, which neither system studies. |
| **Judge unreliability** on recovery quality. | Medium | Mechanical outcomes primary; judge for action-type only, validated against ~100 human labels. |
| **Crossover appears in one model family only.** | Medium | Report as a model property; reframe the contribution. |

---

## 10. What each outcome buys

**Current position: an uninformative null plus two live leads.** Stage C rejects the naive "more information always helps" reading — P4 is significantly worse than P1 and P1-pad does not help — but it cannot speak to H2, because the manipulation and the label move together and the instrument's MDE exceeds the effect anyone expected. The publishable questions have moved to H7 and H8.

**H7 holds — context length is the conditioner.** The strongest outcome. The variable both literatures were missing is the signal ratio, not staleness: "send more" and "send less" are both right at different ratios, and τ\* is measured in context tokens. Deployable as a payload budget keyed to receiver context, and a direct answer to Chun and Ahmed's open problem.

**H8 holds — P6 ≫ P5 on misroutes.** Directive payloads must be falsifiable. A design principle for both STORM- and ATM-class systems, and a clean reconciliation of the reasoning-exchange literature: reasoning in the channel is an error-detection substrate, not an answer channel.

**P7 recovers under-escalation.** "Permission, not information." Roughly fifteen tokens, no routing call, and it would replace the entire payload-volume framing.

**H9 holds — P8 beats predictive routing.** Verification beats prediction in domains with cheap oracles. A systems contribution rather than an ablation, and it retires the 82.5% router-accuracy target instead of chasing it.

**Everything null on a rebuilt instrument.** Now a null worth reporting: 30+ item-calibrated families, action crossed with staleness, realistic context scale, stated MDE. Stage C cannot support that claim; §7.2 becomes the appendix explaining why the obvious earlier reading was wrong.

All five are publishable, and the difference from v3 is that the null is now *earned* rather than inherited from an instrument that could not have detected the effect.

---

## 11. Open decisions before the next stage

1. **Instrument rebuild is not optional.** Action must be crossed with staleness, items calibrated to a 30–70% P1 band, and family count raised to ≥30. *Recommendation: do this before any new payload condition is run; nothing downstream is interpretable without it.*
2. **Which of S1 / S2 / S3 goes first?** *Recommendation: S3 immediately and in parallel — it needs no GPU and its routing-accuracy ceiling decides whether P5/P8 stay alive at all. Then S1, since H7 has the strongest prior. S2 last, and it is unblocked by either result.*
3. **Overlapping assignments — yes or no?** *Recommendation unchanged: natural assignment for the corpus; induce overlap only if episode yield fails, then report it as a separate labelled arm.*
4. **Licensing.** Blocking for anything public. *Recommendation: email the authors; proceed internally in parallel.*
5. **Second model family.** Deference (§4) is exactly the kind of behaviour that could be a Qwen alignment artifact rather than a property of LLM agents. Select the second family before the confirmatory run, not after.
6. **Rationale source and cap N.** Use a structured edit rationale emitted with the winning write. Fix N before the grid from the Stage-C token distribution; do not tune it against recovery success.
7. **Retire or repair P5?** *Recommendation: retire predictive P5 as a deployment candidate. Keep it as the comparison arm for P6 (grounds) and P8 (verification), and keep P5-oracle only as a mechanism bound.*
8. **Do we keep k at all?** *Recommendation: yes, but demoted to a covariate. Report it alongside contradiction load in the H4 horse race rather than as the primary manipulation.*

---

## 12. References

**Direct baselines**

- Liu, Chen, Xu, Jiang & Dong, [Multi-agent Collaboration with State Management (STORM)](https://arxiv.org/html/2605.20563) (arXiv 2605.20563). OCC for shared agent workspaces; the system we fork and whose payload we ablate. **Code: [github.com/dreamyang-liu/STORM](https://github.com/dreamyang-liu/STORM)** — OpenHands SDK, Commit0 harness included, LiteLLM model config; 6 stars / 8 commits / **no license specified** as of 2026-09-06.
- [ATM: CID-Brokered Pre-Write Admission for Multi-Agent Code Co-Synthesis](https://arxiv.org/abs/2607.00041) (arXiv 2607.00041). Pre-write admission at atom granularity; structured refusal payload with policy-selected refinement hint — the source of condition **P5**. Self-disclaims broad comparative superiority.
- Ogenrwot & Businge, [AgenticFlict](https://arxiv.org/html/2604.03551v1) (arXiv 2604.03551; companion to AIware 2026). Stage A data source. [Zenodo record](https://zenodo.org/records/19396917) — CC-BY-4.0, 149 MB. **Verified accessible.**
- [Commit0: Library Generation from Scratch](https://arxiv.org/abs/2412.01769) (arXiv 2412.01769). 54 libraries, 16 in Lite; our task environment.
- [When Parallelism Pays Off: Cohesion-Aware Task Partitioning for Multi-Agent Coding](https://arxiv.org/html/2606.00953v1) (arXiv 2606.00953). Avoid-by-construction alternative; defines the regime where our question is moot.

**Communication content in multi-agent systems**

- Chun & Ahmed, [What Do Agents Communicate? Characterizing Information Exchange in Multi-Agent Systems](https://arxiv.org/abs/2605.20548) (arXiv 2605.20548). C1–C5 taxonomy; removing reasoning costs up to 18.6%; names adaptive communication strategies as the open problem.
- [Beyond Tokens: A Unified Framework for Latent Communication in LLM-based Multi-Agent Systems](https://arxiv.org/html/2606.05711v2) (arXiv 2606.05711). 18 methods, three-axis taxonomy; **assumes synchrony throughout** — the gap this proposal occupies.
- [LatentMAS: Latent Collaboration in Multi-Agent Systems](https://github.com/Gen-Verse/LatentMAS) (ICML 2026 Spotlight).
- [Preventing Error Propagation in Multi-Agent AI through Runtime Monitoring](https://arxiv.org/html/2606.29026) (arXiv 2606.29026). **Closest evidence that payload effects change sign**: reasoning exchange helps substantially in most pairings but demonstrably misleads in others.

**The counter-force: context degradation**

- [Less Context, Better Agents](https://arxiv.org/html/2606.10209) (arXiv 2606.10209). 71.0% → 79.0% from pruning with 63.9% fewer tokens; names stale-state reference errors as a degradation mechanism.

**Asynchrony**

- [AgentComm-Bench: Stress-Testing Cooperative Embodied AI Under Latency, Packet Loss, and Bandwidth Collapse](https://arxiv.org/html/2603.20285v1) (arXiv 2603.20285).
- [Asynchronous Tool Usage for Real-Time Agents](https://arxiv.org/pdf/2410.21620) (arXiv 2410.21620).
- [ProtocolBench: Which LLM MultiAgent Protocol to Choose?](https://arxiv.org/pdf/2510.17149) (arXiv 2510.17149).

**Human precedent (CSCW / SE)**

- Sarma, Redmiles & van der Hoek, [Palantír: Early Detection of Development Conflicts Arising from Parallel Code Changes](https://web.engr.oregonstate.edu/~sarmaa/wp-content/uploads/2020/08/05928359.pdf), IEEE TSE. Severity metric; direct vs. indirect conflicts; the 34→8 result and the direct/indirect cost asymmetry.
- Kasi & Sarma, [Cassandra: Proactive Conflict Minimization Through Optimized Task Scheduling](https://www.semanticscholar.org/paper/Cassandra:-Proactive-conflict-minimization-through-Kasi-Sarma/61423b1a0920ede7d54595469b4d644e2a3a62bc). The human ancestor of Co-Coder.
- [Predicting Merge Conflicts in Collaborative Software Development](https://arxiv.org/pdf/1907.06274) (arXiv 1907.06274).

**Supporting**

- [Adaptive Theory of Mind for LLM-based Multi-Agent Coordination](https://ojs.aaai.org/index.php/AAAI/article/view/40204), AAAI. Relevant to the intent-payload condition.
- [Towards a Science of Scaling Agent Systems](https://arxiv.org/html/2512.08296v1) (arXiv 2512.08296).
