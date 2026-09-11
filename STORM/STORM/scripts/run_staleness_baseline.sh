#!/usr/bin/env bash
# Run the complete staleness-adaptive baseline and local-model case study.
#
# Examples:
#   bash scripts/run_staleness_baseline.sh
#   STALENESS_GPUS=2,3 PORT=8201 bash scripts/run_staleness_baseline.sh
#   START_VLLM=0 ENDPOINT=http://127.0.0.1:8000/v1 bash scripts/run_staleness_baseline.sh
#   RUN_LOCAL_MODEL=0 bash scripts/run_staleness_baseline.sh

set -euo pipefail

# Resolve the runnable STORM directory no matter where the script is launched.
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_DIR"

# The experiment client uses only Python's standard library. vLLM remains in its
# existing GPU environment because copying that large environment is unnecessary.
CONDA_ENV=${CONDA_ENV:-storm-staleness}
MODEL_PATH=${MODEL_PATH:-/shared/models/hf/Qwen3.5-35B-A3B}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-qwen3.5-35b-a3b}
VLLM_BIN=${VLLM_BIN:-/home/wentao/miniconda3/envs/vllm/bin/vllm}
STALENESS_GPUS=${STALENESS_GPUS:-0,2}
TP_SIZE=${TP_SIZE:-2}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-16384}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-64}
PORT=${PORT:-8101}
ENDPOINT=${ENDPOINT:-http://127.0.0.1:${PORT}/v1}
RUN_LOCAL_MODEL=${RUN_LOCAL_MODEL:-1}
START_VLLM=${START_VLLM:-1}
CONTROLLED_OUTPUT_DIR=${CONTROLLED_OUTPUT_DIR:-case_study_results}
LOCAL_OUTPUT_DIR=${LOCAL_OUTPUT_DIR:-local_model_case_study_results}
SERVER_LOG=${SERVER_LOG:-local_model_case_study_results/vllm_server.log}

# Create the small, reproducible client/test environment on the first run.
if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    conda env create -f environment.staleness.yml -n "$CONDA_ENV"
fi

# Verify framework units before spending GPU time, then write the scripted
# mechanism-check artifacts used to validate the full payload/replay matrix.
conda run --no-capture-output -n "$CONDA_ENV" \
    python -m unittest discover -s tests/staleness_adaptive -v
conda run --no-capture-output -n "$CONDA_ENV" \
    python -m staleness_adaptive.case_studies --output-dir "$CONTROLLED_OUTPUT_DIR"

if [[ "$RUN_LOCAL_MODEL" != "1" ]]; then
    echo "Local-model replay skipped (RUN_LOCAL_MODEL=$RUN_LOCAL_MODEL)."
    exit 0
fi

server_pid=""
cleanup() {
    # Stop only the vLLM server started by this invocation.
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

    # Wait up to ten minutes for model loading. Each health probe is read-only.
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

# Run one paired local-model continuation per episode and payload. The raw model
# responses are retained alongside the aggregate diagnostic for manual auditing.
conda run --no-capture-output -n "$CONDA_ENV" \
    python -m staleness_adaptive.local_model_case_studies \
    --endpoint "$ENDPOINT" \
    --model "$SERVED_MODEL_NAME" \
    --output-dir "$LOCAL_OUTPUT_DIR"

echo "Controlled report: $CONTROLLED_OUTPUT_DIR/report.md"
echo "Local-model report: $LOCAL_OUTPUT_DIR/report.md"
