#!/usr/bin/env bash
# Run the full paired Qwen crossover experiment and save every artifact together.
#
# Default result folder:
#   crossover_experiment_qwen35_leakage_safe_k16_20260909/
#
# Useful overrides:
#   STALENESS_GPUS=1,3 OUTPUT_DIR=my_run bash scripts/run_crossover_experiment.sh
#   START_VLLM=0 ENDPOINT=http://127.0.0.1:8000/v1 bash scripts/run_crossover_experiment.sh

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_DIR"

CONDA_ENV=${CONDA_ENV:-storm-staleness}
MODEL_PATH=${MODEL_PATH:-/shared/models/hf/Qwen3.5-35B-A3B}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-qwen3.5-35b-a3b}
VLLM_BIN=${VLLM_BIN:-/home/wentao/miniconda3/envs/vllm/bin/vllm}
STALENESS_GPUS=${STALENESS_GPUS:-0,2}
TP_SIZE=${TP_SIZE:-2}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-16384}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-64}
PORT=${PORT:-8102}
ENDPOINT=${ENDPOINT:-http://127.0.0.1:${PORT}/v1}
START_VLLM=${START_VLLM:-1}
OUTPUT_DIR=${OUTPUT_DIR:-crossover_experiment_qwen35_leakage_safe_k16_20260909}
SEEDS=${SEEDS:-0,1,2}
STALENESS_LEVELS=${STALENESS_LEVELS:-1-16}
TEMPERATURE=${TEMPERATURE:-0.4}
TOP_P=${TOP_P:-0.8}
POLICY_TEMPERATURE=${POLICY_TEMPERATURE:-0.0}
POLICY_SEED=${POLICY_SEED:-0}
POLICY_MAX_TOKENS=${POLICY_MAX_TOKENS:-160}
CONCURRENCY=${CONCURRENCY:-8}
ADAPTIVE_THRESHOLD=${ADAPTIVE_THRESHOLD:-4}
MAX_TOKENS=${MAX_TOKENS:-400}
SERVER_LOG=${SERVER_LOG:-${OUTPUT_DIR}/vllm_server.log}

# Create the small experiment-client environment if the baseline setup was not run.
if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    conda env create -f environment.staleness.yml -n "$CONDA_ENV"
fi

# Guard the experiment with the focused framework tests.
conda run --no-capture-output -n "$CONDA_ENV" \
    python -m unittest discover -s tests/staleness_adaptive -v

server_pid=""
cleanup() {
    # Stop only the server process created by this command.
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid"
        wait "$server_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

if [[ "$START_VLLM" == "1" ]]; then
    if [[ ! -d "$MODEL_PATH" ]]; then
        echo "Model directory not found: $MODEL_PATH" >&2
        exit 1
    fi
    if [[ ! -x "$VLLM_BIN" ]]; then
        echo "vLLM executable not found: $VLLM_BIN (set VLLM_BIN)" >&2
        exit 1
    fi

    mkdir -p "$(dirname -- "$SERVER_LOG")"
    CUDA_VISIBLE_DEVICES="$STALENESS_GPUS" "$VLLM_BIN" serve "$MODEL_PATH" \
        --served-model-name "$SERVED_MODEL_NAME" \
        --host 127.0.0.1 \
        --port "$PORT" \
        --tensor-parallel-size "$TP_SIZE" \
        --max-model-len "$MAX_MODEL_LEN" \
        --max-num-seqs "$MAX_NUM_SEQS" \
        --gpu-memory-utilization 0.85 \
        --reasoning-parser qwen3 \
        >"$SERVER_LOG" 2>&1 &
    server_pid=$!

    # Model load and graph capture can take several minutes on a cold filesystem.
    ready=0
    for _ in $(seq 1 120); do
        if ! kill -0 "$server_pid" 2>/dev/null; then
            echo "vLLM exited during startup; inspect $SERVER_LOG" >&2
            exit 1
        fi
        if ENDPOINT="$ENDPOINT" conda run -n "$CONDA_ENV" python -c \
            'import os, urllib.request; urllib.request.urlopen(os.environ["ENDPOINT"].removesuffix("/v1") + "/health", timeout=2)' \
            >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 5
    done
    if [[ "$ready" != "1" ]]; then
        echo "Timed out waiting for vLLM; inspect $SERVER_LOG" >&2
        exit 1
    fi
fi

# The experiment writes its configuration, exact rerun command, raw responses,
# per-k curves, paired bootstrap effects, threshold sweep, and Markdown report.
conda run --no-capture-output -n "$CONDA_ENV" \
    python -m staleness_adaptive.crossover_experiment \
    --endpoint "$ENDPOINT" \
    --model "$SERVED_MODEL_NAME" \
    --model-path "$MODEL_PATH" \
    --output-dir "$OUTPUT_DIR" \
    --seeds "$SEEDS" \
    --staleness-levels "$STALENESS_LEVELS" \
    --temperature "$TEMPERATURE" \
    --top-p "$TOP_P" \
    --policy-temperature "$POLICY_TEMPERATURE" \
    --policy-seed "$POLICY_SEED" \
    --policy-max-tokens "$POLICY_MAX_TOKENS" \
    --workers "$CONCURRENCY" \
    --adaptive-threshold "$ADAPTIVE_THRESHOLD" \
    --max-tokens "$MAX_TOKENS"

echo "Experiment report: $OUTPUT_DIR/report.md"
echo "Exact rerun command: $OUTPUT_DIR/run_command.sh"
