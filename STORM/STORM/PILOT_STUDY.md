# Context-adaptive refusal pilot v1

This implements Priorities 1 and 2 of `../../staleness-consolidated-priority-plan.md`.
Historical crossover code and saved results are unchanged. No Priority 3 conditions
or fitted routing policy are included.

## Corpus and scoring specification (Priority 1)

`staleness_adaptive/pilot_corpus.py` is the versioned corpus source. Its twelve
families each specify requirements and behavioral examples before implementations.
Each supplies three distinct cases: compatible unfinished work, complete work,
and a conflicting protected contract. Labels are explicit, independent of write
count. k1/k8 change revision records and dependency versions, not task state or
required output length. Four straightforward families are completion controls;
eight contain partial/full completion pairs. This classification precedes model
sampling and is never selected using P1 performance. Three families include an
unchanged caller whose behavior is checked with the replacement implementation.

The public rule permits local implementation fixes but reserves waiver of a
conflicting protected input/output contract to a manager. Thus escalation follows
an explicit authority constraint, not merely a failing test. No one-step response
can demonstrate completed coordination.

| Outcome | Definition |
|---|---|
| Route correctness | Valid response action belongs to the case's acceptable set. |
| Verified recovery | On adapt/abandon cases, the resulting code passes task and peer behavior checks. Adapt checks the replacement; abandon checks the unchanged current state. A redundant but correct adaptation can pass behavior while failing route. |
| Justified escalation | Valid escalation on a specified contract-conflict case. |
| Completed coordination | Always null/unmeasured in this one-step study. |
| Equal-action composite | Verified recovery for adapt/abandon cases; justified escalation for escalation cases; equal action weights. This is not end-to-end task success. |

Responses must contain a supported action, a string explanation, and complete
`revised_content` for adapt or an empty string otherwise. Invalid or truncated
responses fail scored outcomes. Escalation cases have null verified recovery.
Report failed revisions, unnecessary abandonment (abandon on another route),
unjustified escalation, invalid responses, truncation, and abandon precision
(correct abandons / all predicted abandons), including its denominator.
Behavioral checks run restricted Python in a separate process with resource and
time limits. They are finite tests, not proof for all possible inputs or a general
hostile-code sandbox.

The split is fixed by family: bounded_percentage, batch_count, duration_millis
are development; the other nine families are evaluation. Setup calibration uses
only development cases. All twelve can appear in the explicitly exploratory pilot
summary; evaluation-only results are reported separately. New independent families
are required for confirmation. No corpus selection or prompt tuning on evaluation
responses is permitted.

Before inference: check balance, split isolation, k invariance, current-state
positive/negative controls, valid reference adaptations, rejection of replacements
that drop peer behavior, and prompt independence from evaluator fields. Only
`PublicCase` is accepted by prompt rendering. P1/P2/P3 add no route directive or
oracle field. This pilot has no P5 implementation and does not change the existing
deployable P5 policy.

## Primary study specification (Priority 2)

Freeze 36 cases × 2 lengths (1,024 / 12,288) × 2 histories (current /
superseded) × 3 payloads (P1/P2/P3) × seeds 0,1 = 864 continuations, at k4.
Use the saved Qwen3.5-35B-A3B model, temperature 0.4, top_p 0.8, thinking off,
and a common 2,048-token completion allowance. Token counts use the local model
tokenizer and its chat template, not whitespace words. Reference JSON responses
must fit the allowance. Input plus output must fit 16,384 tokens. Refuse to run
if essential short-context evidence does not fit; never truncate it.

Both history conditions contain two source-read observations at the same locations
in `main`: its None branch and final return. Current records reproduce current
source; superseded records contain a different earlier sentinel and expression.
Records carry a path, source location and version. Formatting whitespace matches
their token lengths to within one token. Both are constructed histories, not
restored natural executions. Long contexts add complete, unrelated documentation
read records without adding task-relevant facts. Relevant history begins halfway
through the tokenized input (within two percentage points); the authoritative
refusal is at the tail. Match each input target within 2%, and check the spread
across payloads within 2%. Log payload, relevant, obsolete-span and total tokens,
obsolete fraction, and position. Obsolete-span accounting covers the two affected
source-read records including provenance, excluding layout padding; it does not
claim every token in those records is independently false.

Predeclare P2−P1 and P3−P1 paired effects in each length/history cell, their
overall effects, and changes in those differences with length (long−short) and
history (superseded−current), averaging over the other factor. Report these for
each action and its appropriate outcome, pooled verified adapt/abandon recovery,
route accuracy and the equal-action composite. Average seeds within cases, then
form paired effects within families. Resample whole families for exploratory 95%
percentile bootstrap intervals; use family sign-flip tests under the symmetric
null, not continuation-level independent tests. Show all family effects, number
of families with positive/negative differences, and split-specific results.
Intervals/p-values are unadjusted exploratory diagnostics, not confirmatory tests.

A provisional practically meaningful effect is 10 percentage points. Report a
normal-approximation family-count estimate for 80% power at two-sided 5%, using
pilot paired family variance, before any confirmation is planned. This estimate
is unstable at twelve families (nine held out), and zero observed variance cannot
establish that no more families are needed. Do not train a threshold or claim a
deployable adaptive rule from these data. The study fixes k and cannot compare
contextual staleness against varying write counts.

Save corpus, gates, frozen configuration, tokenizer/source fingerprints, exact
requests and responses, row-level outcomes, grouped summaries, family contrasts
and a Markdown report. Checkpoint each response as it arrives; resume only with
identical configuration and prompts. Transport failures must be retried or
resolved before the grid is considered complete. Malformed model answers remain
outcomes and are not selectively resampled.

## Commands

From `STORM/STORM`, using an environment with the existing local Transformers
installation (for example `/home/wentao/miniconda3/envs/vllm/bin/python`):

```bash
python -m unittest discover -s tests/staleness_adaptive -q
python -m staleness_adaptive.pilot_corpus
python -m staleness_adaptive.context_study --output-dir outputs/context-pilot-UNIQUE --prepare-only
python -m staleness_adaptive.context_study --output-dir outputs/context-pilot-UNIQUE --resume
```

The inference server must serve the specified model at `http://127.0.0.1:8102/v1`
with a 16,384-token context limit. The runner checks tokenizer counts against a
six-call development calibration (three routes × two lengths) before the grid.
Use at most four concurrent calls. Repeated experiments need a unique output
directory; `--resume` is only for finishing the same frozen experiment.

## Observed pilot and next decision

The [completed September 12 run](outputs/context-pilot-v1-20260912-run1/report.md)
contains all 864 continuations, plus six separate development calibration calls.
All 37 tests passed, including the actual-tokenizer grid. Independent audits
recomputed every response score and 42 pooled recovery contrasts. There were
zero infrastructure errors and 18 truncated/invalid responses, retained as failures.

This pilot **does not establish reproducible context-dependent payload benefit**.
Verified adapt/abandon recovery was 185/192 for P1, 188/192 for P2, and 185/192 for
P3. On the nine evaluation families, the length interactions were −2.8 points
for P2−P1 (exploratory 95% interval −16.7 to +8.3) and −4.2 for P3−P1 (−13.9 to
+2.8). The small positive P2 history interaction in the full pilot came from one
development family and was absent from evaluation families. These observations
do not justify an adaptive rule or a claim of practically negligible effects.

Route behavior sharply limits interpretation: only 4/288 complete cases were
abandoned, and 0/288 contract-conflict cases were escalated. Among the 277
adaptations on complete cases, 210 were unchanged after normalizing layout and
`== None` versus `is None` comparisons (a descriptive post-run AST check).
Behaviorally correct redundant rewrites legitimately pass verified recovery but
fail the predeclared route criterion. All 265 valid conflict-case adaptations
retained the protected contracts without recognizing the incompatible task
requirement. This suggests investigating interpretation of the coordination
rules and unnecessary rewriting; it does not establish their cause.

The chosen next step is to **resolve uncertainty on this same question**, with
any revised instructions validated on new development families before independent
evaluation. Do not relabel or filter this saved run, claim that zero-width
bootstrap intervals at an observed floor establish precision, or launch Priority
3 from these results. Shared case structure, near-ceiling verified recovery,
repeated documentation-read padding, constructed histories, and the route floor
limit generalization. Completed coordination remains unmeasured.

The run directory includes the original source snapshot and a resume command
using that snapshot, so later source edits cannot silently change the experiment.
Raw responses, token costs, all family contrasts, provisional confirmation-size
estimates for a ten-point effect, and audit records are saved alongside the report.
