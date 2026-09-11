# P3 implementation and leakage audit

## Verdict on the earlier 100% result

The earlier P3 result cannot support the claim that more information is always
better. Its synthetic `winner_reasoning` was selected from `correct_action` and
directly named the expected recovery behavior.

An audit of the 144 historical P3 continuations found a direct route cue in every
P3 rationale:

- 69/69 `adapt` examples said to rebase the proposed behavior;
- 51/51 `abandon` examples explicitly said `abandon` and 51 used the phrase
  `correct recovery`;
- 24/24 `escalate` examples explicitly said `escalate`.

The old revision scorer was also vulnerable to reward hacking. It accepted a
syntactically valid file containing only comments with the configured required
substrings. For example, comments containing `isinstance(name, str)` and
`.strip().lower()` were scored as a successful normalization implementation.

## Corrections applied before the new run

- P3 rationales now describe only why the winning code was changed. Recovery
  action words and oracle refinement hints are prohibited by a pre-run audit.
- Recovery prompts are checked for evaluator field names and ground-truth fields.
- Adapted code runs isolated scenario-level behavioral checks instead of receiving
  credit for substrings.
- Every increment of staleness adds a concrete concurrent assignment, and adapted
  code must preserve all of those assignments.
- Two always-adapt scenario families keep patch-repair examples present through
  `k=16`.
- Results are reported both overall and within the correct-action strata to expose
  action-mix confounding.

The corrected 128-episode audit is recorded in `leakage_audit.json`: zero P3
directive cues, zero forbidden evaluator fields, zero oracle hints, and eight
active behavioral validators.

## Interpretation boundary

The new experiment remains a controlled synthetic mechanism study. It removes the
identified implementation leaks and strengthens the scorer, but it does not replace
a natural STORM/Commit0 refusal corpus or a held-out end-to-end evaluation.
