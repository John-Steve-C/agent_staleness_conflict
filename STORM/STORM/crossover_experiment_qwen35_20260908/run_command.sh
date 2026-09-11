#!/usr/bin/env bash
# Reproduce this complete experiment, including starting and stopping local vLLM.
set -euo pipefail
cd /home/wentao/Asyn_agent/STORM/STORM
OUTPUT_DIR=/home/wentao/Asyn_agent/STORM/STORM/crossover_experiment_qwen35_20260908 \
MODEL_PATH=/shared/models/hf/Qwen3.5-35B-A3B \
SERVED_MODEL_NAME=qwen3.5-35b-a3b \
SEEDS=0,1,2 \
TEMPERATURE=0.4 \
TOP_P=0.8 \
CONCURRENCY=8 \
ADAPTIVE_THRESHOLD=4 \
MAX_TOKENS=400 \
bash scripts/run_crossover_experiment.sh
