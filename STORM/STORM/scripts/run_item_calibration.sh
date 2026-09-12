#!/usr/bin/env bash
# Run one exact-token P1 item-calibration and retain its local-server log.

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
PORT=${PORT:-8102}
ENDPOINT=${ENDPOINT:-http://127.0.0.1:${PORT}/v1}
START_VLLM=${START_VLLM:-1}
EPISODES=${EPISODES:?Set EPISODES to an audited candidate JSONL file}
OUTPUT_DIR=${OUTPUT_DIR:?Set OUTPUT_DIR to a unique calibration directory}
SEEDS=${SEEDS:-0,1,2,3,4,5,6,7,8,9}
CONCURRENCY=${CONCURRENCY:-8}
CONTEXT_LENGTH=${CONTEXT_LENGTH:-8000}
TEMPERATURE=${TEMPERATURE:-0.4}
TOP_P=${TOP_P:-0.8}
MAX_TOKENS=${MAX_TOKENS:-700}
TOKENIZER_PATH=${TOKENIZER_PATH:-${MODEL_PATH}/tokenizer.json}

if [[ -e "$OUTPUT_DIR/replay_results.csv" ]]; then
    echo "Refusing to overwrite completed calibration: $OUTPUT_DIR" >&2
    exit 1
fi
if [[ ! -f "$EPISODES" ]]; then
    echo "Candidate corpus not found: $EPISODES" >&2
    exit 1
fi
if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    conda env create -f environment.staleness.yml -n "$CONDA_ENV"
fi
if ! conda run -n "$CONDA_ENV" python -c 'import tokenizers' >/dev/null 2>&1; then
    conda run -n "$CONDA_ENV" python -m pip install tokenizers==0.22.2
fi

conda run --no-capture-output -n "$CONDA_ENV" \
    python -m unittest discover -s tests/staleness_adaptive -p 'test_*.py'

mkdir -p "$OUTPUT_DIR"
server_pid=""
cleanup() {
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid"
        wait "$server_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

if [[ "$START_VLLM" == "1" ]]; then
    CUDA_VISIBLE_DEVICES="$STALENESS_GPUS" "$VLLM_BIN" serve "$MODEL_PATH" \
        --served-model-name "$SERVED_MODEL_NAME" \
        --host 127.0.0.1 \
        --port "$PORT" \
        --tensor-parallel-size "$TP_SIZE" \
        --max-model-len "$MAX_MODEL_LEN" \
        --max-num-seqs 64 \
        --gpu-memory-utilization 0.85 \
        --reasoning-parser qwen3 \
        >"$OUTPUT_DIR/vllm_server.log" 2>&1 &
    server_pid=$!

    ready=0
    for _ in $(seq 1 120); do
        if ! kill -0 "$server_pid" 2>/dev/null; then
            echo "vLLM exited during startup; inspect $OUTPUT_DIR/vllm_server.log" >&2
            exit 1
        fi
        if curl -fsS --max-time 2 "${ENDPOINT%/v1}/health" >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 5
    done
    if [[ "$ready" != "1" ]]; then
        echo "Timed out waiting for vLLM" >&2
        exit 1
    fi
fi

conda run --no-capture-output -n "$CONDA_ENV" \
    python -m staleness_adaptive.calibration_experiment \
    --episodes "$EPISODES" \
    --output-dir "$OUTPUT_DIR" \
    --endpoint "$ENDPOINT" \
    --model "$SERVED_MODEL_NAME" \
    --tokenizer-path "$TOKENIZER_PATH" \
    --seeds "$SEEDS" \
    --context-length "$CONTEXT_LENGTH" \
    --workers "$CONCURRENCY" \
    --temperature "$TEMPERATURE" \
    --top-p "$TOP_P" \
    --max-tokens "$MAX_TOKENS"
