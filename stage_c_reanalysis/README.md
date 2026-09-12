# Stage-C action-stratified re-analysis

Inputs: `crossover_experiment_qwen35_leakage_safe_k16_20260909/replay_results.csv` and `crossover_experiment_qwen35_leakage_safe_k16_20260909/episodes.jsonl`.

Every non-P1 payload is compared with P1 separately within each correct-action stratum. Recovery seeds are averaged within an episode; confidence intervals resample scenario families; randomization tests flip the whole scenario family. The CSV tables carry the realised episode count, family-cluster count, and MDE for every contrast.

## Files

- `adapt_contrasts.csv`, `abandon_contrasts.csv`, and `escalate_contrasts.csv`: all action-stratified payload-vs-P1 contrasts.
- `action_summary.csv`: P1 rate, realised cluster count, and planning MDE by action.
- `mde.md`: MDE definition, estimates, and small-cluster limitations.
- `errata.md`: corrected interpretation of the Stage-C gate.
