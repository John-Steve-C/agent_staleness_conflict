# Staleness-Adaptive Communication in Asynchronous Multi-Agent Code Generation

**Internal planning document — v2**
Revised 2026-09-06 · Horizon: ~3 months · Status: pre-decision

> **What changed from v1.** STORM's implementation is public — [github.com/dreamyang-liu/STORM](https://github.com/dreamyang-liu/STORM), built on the OpenHands SDK, with the Commit0 harness included. The build plan is rewritten around forking it rather than building from scratch, which cuts harness work from ~3–4 weeks to ~1.5–2 and promotes Tier 2 and the second model family from stretch goals to plan. A new **Gate 0** (reproduce STORM's numbers before committing) is now the first milestone, and an unresolved **licensing question** is the top near-term risk. A second system — ATM — has also appeared with a *different* hand-designed refusal payload; it adds a condition (P5) and sharpens the framing rather than displacing it.

---

## 1. One-paragraph version

When multiple LLM agents edit one repository concurrently, a write is refused whenever the writer's view of the code has gone stale. Two systems now ship hand-designed refusal payloads — STORM sends content plus a diff plus a stale-dependency list; ATM sends a structured verdict envelope with a refinement hint — and **neither has been ablated.** Both payloads were designed, not measured. We propose that there is no single right payload, that the right one depends on **how stale the refused writer is**, and that this is measurable. Forking STORM gives us a working baseline whose numbers are directly comparable; a two-tier design (a large corpus of cheaply replayed refusal episodes, plus a small set of end-to-end runs) makes the grid affordable. If a crossover exists, the deliverable is a staleness-adaptive protocol. If not, the null is a correction to how this literature currently reasons about payload richness.

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

**C2.** An operationalization of *staleness* separating temporal, semantic, and investment components, with evidence on which predicts recovery cost. We expect investment staleness — work built on the false premise — to dominate, which would be directly actionable for orchestrator design.

**C3.** Either a staleness-adaptive protocol with measured gains over STORM's fixed payload, or a well-powered null constraining the "send more reasoning" prior.

---

## 4. Research questions and hypotheses

**RQ1.** Does the optimal refusal payload depend on staleness magnitude?
**RQ2.** Which operationalization of staleness best predicts recovery outcome?
**RQ3.** Is any advantage of rich payloads content, or merely token volume?
**RQ4.** Does rich feedback help by improving patch adaptation, or by improving *decisions about whether to adapt at all*?
**RQ5.** Is more *information* what helps, or more *direction*?

| ID | Hypothesis | Status if false |
|---|---|---|
| **H1** | Recovery quality declines monotonically with staleness under every payload. | Sanity check. Failure means the manipulation is broken. |
| **H2** | **(core)** The advantage of intent- and reasoning-bearing payloads over content-only increases with staleness. There is a threshold τ\* below which content-only is statistically indistinguishable at lower cost, and above which richer payloads win. | Fixed payloads are defensible; report the null against the "send more" prior. |
| **H3** | The high-staleness advantage survives a length-matched padded control. | The effect is token budget, not content — different finding, still publishable. |
| **H4** | Investment staleness predicts recovery cost better than temporal staleness. | Temporal delay is the right knob; simplifies orchestrator design. |
| **H5** | **(mechanism)** Intent-payload benefit concentrates in episodes where the correct action is *abandon* or *escalate*, not *adapt*. | Benefit is in patch repair, not decision-making — points toward diff enrichment instead. |
| **H6** | **(new)** A directive payload (P5, ATM-style recovery route) matches or beats a full reasoning trace (P3) at high staleness for a fraction of the tokens. | Raw reasoning carries something a policy directive cannot compress. Also informative. |

H5 and H6 together are what make the result explanatory rather than merely empirical. When the correct move is "adapt my patch to the new shape," the diff already contains everything needed. When it is "stop, the other agent implemented this" or "push back, that broke an invariant I was maintaining," the diff is *ambiguous*. H6 then asks whether resolving that ambiguity requires transmitting the other agent's reasoning, or merely transmitting a decision. **If P5 ≈ P3, the headline is not "send more" but "send a conclusion"** — a sharper and far cheaper result, and one that reframes ATM's design choice as empirically vindicated rather than merely asserted.

---

## 5. Experimental design

### 5.1 Setting

Commit0-Lite: 16 Python repositories, implement missing code until existing tests pass. Chosen because STORM's numbers are on it and its code ships the harness, so the baseline is comparable by construction rather than by approximation. Four engineer agents plus one manager, matching STORM's configuration.

### 5.2 Independent variable 1 — payload condition

| ID | Payload | Origin / notes |
|---|---|---|
| **P0** | Bare refusal: "Write rejected, stale read on `{file}`." | Floor. Isolates the value of *any* information. |
| **P1** | Current content + unified diff + stale-dependency list. | **= STORM's shipped behavior. The baseline that matters.** |
| **P2** | P1 + winning agent's declared intent (1–2 sentences, emitted once at write time). | Cheap: written once, reused by every refused reader. |
| **P3** | P1 + winning agent's reasoning trace for that edit, capped at N tokens. | Expensive, per-recipient. |
| **P4** | P1 + winning agent's full task assignment and recent trajectory. | Ceiling. Expected to suffer dilution. |
| **P5** | P1 + a directive recovery route: adapt / queue / serialize / abandon, with a one-line refinement hint. | **Modeled on ATM.** Orthogonal to richness — *less* information, more actionable. |
| **P1-pad** | P1 padded with conflict-irrelevant repo text, token-matched to P3. | **Control for H3.** |

Two comparisons carry most of the practical weight. **P2 vs P3** is a cost-structure question: intent is a fixed cost paid once by the writer, a reasoning trace is a per-recipient cost that scales with contention. **P3 vs P5** is the information-versus-direction question, and is the reason ATM's appearance improves this study rather than threatening it.

### 5.3 Independent variable 2 — staleness

Primary knob is **edit-distance staleness**: buffer the refused agent's notification until *k* other writes have landed, k ∈ {1, 2, 4, 8}. Chosen over wall-clock because it is model-speed-invariant and exactly reproducible under replay. A secondary temporal arm (τ ∈ {0s, 30s, 2min}) checks external validity.

Every episode additionally records all three natural measures, so H4 is testable observationally inside the injected design:

- **s_temporal** — seconds from A's last read of the conflicting file to refusal.
- **s_semantic** — Palantír's severity metric (non-comment lines changed / total non-comment lines in A's read set), plus a binary for whether changed symbols intersect symbols A referenced. Reproduces Palantír's direct/indirect distinction.
- **s_invest** — tokens generated and tool calls issued by A between that read and the refused write.

### 5.4 Two-tier structure (what makes 3 months possible)

A naive grid — 7 payloads × 4 staleness levels × seeds, each a full multi-agent run — is unaffordable. STORM reports **$199–$429 per configuration** and ~13 hours wall-clock for 16 repos.

**Tier 1 — Episode replay. Large N, cheap, primary instrument.** Harvest a *refusal episode corpus* from natural runs. Each episode snapshots: repo state at A's read, repo state at refusal, A's full trajectory and context, B's edit with intent and reasoning trace, and all three staleness measures. Then replay only the recovery — restore A's context to the instant of refusal, inject payload P_i, continue until A produces a next write attempt or gives up (cap ~20 iterations). Each cell becomes one ~15k-in / 3k-out continuation. Target corpus: **250–300 episodes.**

**Tier 2 — End-to-end live runs. Small N, validity check.** Full sessions on 6 Commit0-Lite repos under three conditions: P1, the Tier-1 winner, and the adaptive policy. Confirms Tier-1 rankings move repo-level pass rate and wall-clock. **Now planned rather than stretch,** thanks to the harness time freed by forking STORM.

**Stated limitation, up front:** Tier 1 measures immediate recovery quality, not the counterfactual end-to-end outcome, because a changed decision cannot be cheaply propagated forward through the rest of a session. Tier 2 exists to test whether that shortcut is safe. Tier-1-only claims must be scoped to recovery quality.

### 5.5 Dependent variables

**Primary (mechanical, no judge):**

- *Recovery success* — the next write validates **and** the touched region's tests pass. (Tier 1)
- *Repo pass rate* — Score_w and Score_macro, STORM's definitions, for direct comparability. (Tier 2)

**Secondary:**

- *Recovery cost* — tokens and tool calls from refusal to accepted write.
- *Repeat-refusal rate* — fraction of episodes whose recovery write is *also* refused. Direct measure of feedback sufficiency; expected to be where P0 collapses.
- *Action-type correctness* — adapt / abandon / escalate against a rubric. Tests H5.
- *Redundant implementation rate* — two agents implement the same symbol with different signatures. STORM's named unsolved failure; a payload that reduces it is a concrete win.
- *Net efficiency* — Cost_eff and Time_eff, STORM's definitions.

### 5.6 Confound controls

1. **Token volume** → P1-pad, length-matched to P3.
2. **Difficulty ↔ staleness confound** → staleness is *injected*, not observed; design is within-episode paired, so episode difficulty is held constant by construction.
3. **Judge bias** → mechanical outcomes primary; the LLM judge labels action-type only, is blind to condition, and is validated against ~100 human-labeled episodes with reported agreement.
4. **Model idiosyncrasy** → full grid on two model families. STORM uses **LiteLLM identifiers**, so a local vLLM OpenAI-compatible endpoint drops in with a config change — this arm is now cheap to add, which is the main reason it moves from stretch to plan.
5. **Order effects** → randomized episode presentation, seeds recorded.

### 5.7 Statistical plan

Within-episode paired design, mixed-effects models:

```
recovery_success ~ payload * staleness + (1 | episode) + (1 | repo)      # logistic
recovery_cost    ~ payload * staleness + (1 | episode) + (1 | repo)      # linear
```

H2 is the **payload × staleness interaction term**, pre-registered before the full grid. τ\* estimated from the crossover of fitted payload curves with bootstrap CIs. H4 compares model fit across staleness operationalizations. H6 is a planned contrast P5 vs P3 at the top staleness level, with a token-cost-adjusted secondary comparison.

With a paired design and ~250 episodes, detecting a 10-percentage-point payload difference at high staleness is comfortably powered. Final power analysis on Stage C's observed variance, not assumed now.

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
| **Payload strategy interface** | A seam at the refusal site so P0–P5 are swappable by config. This is the natural extension point; STORM already assembles a payload there. | 2–3 days |
| **Episode logger** | Extend the existing event log to a full replayable snapshot at each refusal. | 2–3 days |
| **Replay driver** | Restore agent context to a snapshot, inject payload, continue, capture outcome. **Still the hardest piece and the one most likely to overrun** — faithful context restoration is fiddly and getting it wrong silently invalidates Tier 1. | ~1 week |
| **Staleness scheduler** | Buffer notifications by k intervening writes; temporal arm. | 2–3 days |
| **Intent/reasoning capture** | Require a structured intent on write; retain the trace. | 1–2 days |
| **Bash mediation** *(optional)* | Close the write path STORM lists as bypassing its mediation layer. | 4–5 days |

**Revised estimate: ~1.5–2 weeks to a working instrumented pilot**, down from 3–4. That saving is what promotes Tier 2 and the second model family from stretch to plan — it should be spent there, not on new scope.

---

## 7. Timeline and gates

**Week 1 · Stage 0 — Reproduce and de-risk. (New, and the most important addition in v2.)**
Set up the fork, run `run_multi.sh` on 3 Commit0-Lite repos, and attempt to reproduce STORM's reported figures. Simultaneously open the licensing question with the authors.

> **Gate 0.** Multi-agent must beat single-agent on the 3-repo subset, in the direction and rough magnitude STORM reports (46.2% vs 20.7% weighted). If the baseline does not reproduce, you do not have the baseline you think you have — and every downstream number is uninterpretable. Fall back to reimplementing the mediation layer only (~300 LOC; the OCC idea is simple even if the system is not) and accept looser comparability. **Do not skip this gate to save a week.**

**Weeks 1–3 · Stage A — Observational analysis on AgenticFlict.** Runs in parallel, no harness needed. 29,609 conflicting agent PRs, 336,380 conflict regions, 59,412 repositories, public on Zenodo under CC-BY-4.0. Characterize the empirical distribution of conflict severity and locality; estimate what fraction of real agent-agent conflicts are high-staleness restructuring versus low-staleness local edits.

> **Gate A.** If under ~10% of real conflicts are high-severity or non-local, the crossover has little practical headroom. Narrow the claim, or pivot to the observational study as the standalone deliverable.

**Weeks 2–4 · Stage B — Instrumentation.** (Was weeks 2–6.)

> **Gate B.** ≥30 refusal episodes per wall-clock hour across 3 repos. Below that, cut to 4 payload conditions (P0, P1, P3, P5) and 2 staleness levels.

**Weeks 4–6 · Stage C — Episode corpus + pilot grid (~60 episodes, local model).**

> **Gate C — the important one.** Test P0 vs P3 at k=8: maximum contrast. If no effect is detectable at the extremes, the full grid will not find one. Stop and write the null. Placed early and cheap deliberately; it is the main defense against spending the budget to discover nothing.

**Weeks 6–9 · Stage D — Full Tier 1 grid, both model families.**

**Weeks 9–11 · Stage E — Tier 2 end-to-end confirmation on 6 repos.**

**Weeks 11–12 · Stage F — Analysis, adaptive-policy prototype if H2 holds, writeup.**

### Honest assessment

Forking makes 3 months workable rather than merely optimistic. The plan now has genuine slack in weeks 4–6, which should absorb replay-driver overrun rather than fund new scope. The realistic downside outcome is Stage A plus Tier 1 on one model family — still a defensible result. The staging preserves that: Stage A is fully independent of the harness, and Tier 1 alone answers RQ1 for recovery quality.

---

## 8. Budget

**API inference**

| Item | Estimate |
|---|---|
| Gate 0 reproduction, 3 repos | $50–120 |
| Corpus generation (~6 repos, several runs) | $300–600 |
| Tier 1 — ~300 episodes × 7 payloads × 3 seeds ≈ 6,300 continuations at ~$0.09 | ~$570 |
| Tier 2 — 6 repos × 3 conditions × 2 seeds | $150–350 |
| Pilots, re-runs, failed configurations | 2× reserve |
| **Total** | **~$2,000–3,500** |

The two-tier structure is what produces this number; a single-tier design over the same grid is roughly an order of magnitude more. Adding P5 costs about $80 — the ATM-derived condition is nearly free because replay dominates the grid.

**Local GPU.** The open-weight arm needs a coder model strong enough for non-trivial agent behavior — Qwen-class at 32B+ under vLLM. Below that, agents fail for reasons unrelated to payload and the experiment measures nothing. LiteLLM configuration makes the integration itself trivial.

**Wall-clock is the binding constraint, not dollars.** STORM needed ~13 hours for 16 repos with 4 agents. Corpus generation is the bottleneck; replay is cheap and parallel.

---

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **STORM's licensing is unresolved.** No license file; default copyright applies. | **High (near-term)** | Contact authors week 1. If no grant: keep the fork private and internal, or fall back to a clean-room mediation layer. Never publish an artifact built on it without written permission. |
| **Baseline fails to reproduce.** 8 commits, 6 stars, 0 forks — untested by anyone outside the authors. | **High** | Gate 0, week 1, before any dependent work. Fallback path specified. |
| **Too few refusal episodes.** A well-partitioning manager makes conflicts rare — exactly Co-Coder's thesis (+14.0% pass rate, 2.10× speedup, conflicts "avoided by construction"). | High | Deliberately overlapping assignments as a *documented manipulation*, reported separately from natural-assignment runs with the external-validity caveat stated. See §11.1. |
| **Effect too small to detect.** | High | Gate C, early and cheap, at maximum contrast. |
| **Replay infidelity** silently invalidates Tier 1. | High | Validate by replaying with the *original* payload and confirming the original action reproduces above a threshold rate. Report that rate. |
| **ATM or a follow-up runs the ablation first.** | Medium | ATM is a governance/feasibility paper on a bespoke benchmark that disclaims comparative superiority — it is not positioned to ablate. Monitor, but do not redesign around it. Our differentiator is the staleness interaction, which neither system studies. |
| **Judge unreliability** on recovery quality. | Medium | Mechanical outcomes primary; judge for action-type only, validated against ~100 human labels. |
| **Crossover appears in one model family only.** | Medium | Report as a model property; reframe the contribution. |

---

## 10. What each outcome buys

**Crossover confirmed (H2).** Refusal payload should be staleness-adaptive: cheap notification by default, escalate when measured staleness crosses τ\*. Deployable protocol, direct answer to Chun and Ahmed's stated open problem, concrete improvement path for both STORM- and ATM-class systems.

**P5 ≈ P3 (H6).** The lesson is "send a conclusion, not a transcript" — cheaper than the reasoning-sharing literature assumes, and an empirical vindication of ATM's directive design over STORM's informational one.

**No crossover, richness always wins.** Contradicts the token-cost intuition current systems are built around, and pushes against the context-pruning result specifically in agentic coordination.

**No crossover, richness never wins.** A well-powered null against the "send more reasoning" prior, from a setting with mechanical ground truth rather than benchmark deltas. Arguably the most useful outcome for the field and the one most likely to go unreported by others.

All four are publishable. That property is the main reason to prefer this over the alternative case study.

---

## 11. Open decisions before Stage B

1. **Overlapping assignments — yes or no?** Deliberate overlap makes conflicts frequent enough to measure at reasonable N, but risks measuring a regime no sensible orchestrator would create. *Recommendation: natural assignment for the corpus; induce overlap only if Gate B fails on episode yield, then report it as a separate clearly-labeled arm.*
2. **Licensing.** Blocking for anything public. *Recommendation: email the authors in week 1; proceed internally in parallel; do not let it block Gate 0.*
3. **Which local model.** Determines whether the open-weight arm is a real replication or a weak-agent artifact. Qwen-class 32B+ is the floor.
4. **Build bash mediation, or inherit STORM's hole?** *Recommendation: skip it initially — it is not on the critical path for the payload question. Instead log which refusals *would* have been missed, quantify the leak, and build it only if the leak is large enough to bias results.* (Changed from v1, where the harness was being written anyway and the marginal cost was lower.)
5. **Reasoning-trace cap N.** Too small and P3 collapses into P2; too large and it collapses into P4. Set from the Stage C pilot, not guessed.

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
