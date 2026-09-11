# Staleness-adaptive communication baseline

This directory adds a dependency-light Tier-1 baseline around STORM's optimistic
concurrency-control refusal seam. It implements the proposal's P0–P5 and P1-pad
payloads, an adaptive P1/P5 threshold policy, refusal episode logging, three
staleness measurements, edit-distance/temporal notification scheduling, replay
orchestration, and controlled code-conflict cases.

P5 is a two-stage condition: a routing policy predicts an action from observable
task and file state, then the recovery agent receives P1 plus that route and a
one-line hint. `P5-oracle` is retained only as a diagnostic upper bound and is
never used by the adaptive policy.

The package does not replace STORM's manager. `storm_adapter.py` converts the
existing SDK `WriteResponse` at `_conflict_observation` into a replayable episode;
`PayloadRenderer` supplies the text returned to an engineer. The checked-out
vendored `software-agent-sdk` is currently absent from this working tree, so the
adapter intentionally uses structural typing and can be tested without importing
OpenHands. Restore that dependency before wiring the adapter into live Commit0
runs.

## One-command run

From `STORM/STORM`:

```bash
bash scripts/run_staleness_baseline.sh
```

The script is commented and performs the complete pilot workflow:

1. creates the `storm-staleness` conda environment if needed;
2. runs unit tests and the deterministic mechanism check;
3. starts `/shared/models/hf/Qwen3.5-35B-A3B` with vLLM on two GPUs;
4. replays all four cases under P0, P1, P2, P3, P5, P1-pad, and adaptive;
5. stops only the server process it started and writes reports.

Configuration is through environment variables. Common overrides are:

```bash
STALENESS_GPUS=2,3 PORT=8201 bash scripts/run_staleness_baseline.sh
START_VLLM=0 ENDPOINT=http://127.0.0.1:8000/v1 bash scripts/run_staleness_baseline.sh
RUN_LOCAL_MODEL=0 bash scripts/run_staleness_baseline.sh
```

If `VLLM_BIN` is not auto-detected, point it at the vLLM executable. `MODEL_PATH`,
`SERVED_MODEL_NAME`, `TP_SIZE`, `MAX_MODEL_LEN`, and both output directories are
also configurable at the top of the script.

## Run components separately

```bash
conda env create -f environment.staleness.yml
conda run -n storm-staleness python -m unittest discover -s tests/staleness_adaptive -v
conda run -n storm-staleness python -m staleness_adaptive.case_studies
conda run -n storm-staleness python -m staleness_adaptive.local_model_case_studies \
  --endpoint http://127.0.0.1:8101/v1 \
  --model qwen3.5-35b-a3b
```

## Outputs and scope

- `case_study_results/`: scripted mechanism check and replay fixtures.
- `local_model_case_study_results/`: real Qwen responses, per-cell CSV, summary,
  and the H2 low-versus-high staleness diagnostic.

These four controlled cases show whether the instrument can expose the proposed
crossover; they are not a powered hypothesis test. The next empirical step is to
capture natural Commit0 refusal episodes through `episode_from_storm_refusal`,
validate faithful replay with the original P1 action, and run the paired grid on
that corpus.

## Paired crossover experiment

The leakage-safe local-Qwen experiment uses eight scenario families, every
edit-distance level from 1 through 16, nine payload strategies (including
P5-oracle), and three sampling seeds. P3 rationales are rejected before inference
if they contain recovery directives, and adapted code must pass behavioral checks
while preserving every concurrent revision marker:

```bash
bash scripts/run_crossover_experiment.sh
```

Its checked-in results and self-contained rerun command are under
`crossover_experiment_qwen35_leakage_safe_k16_20260909/`.
