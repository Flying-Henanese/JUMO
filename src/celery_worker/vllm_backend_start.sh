#!/usr/bin/env bash
set -euo pipefail

MODEL="Qwen/Qwen2-VL-7B-Instruct"
COMMON_OPTS=(
  --model "$MODEL"
  --host "0.0.0.0"
  --tensor-parallel-size 1
  --gpu-memory-utilization 0.5
  --trust-remote-code
)

# GPU 0 → 端口 8000
CUDA_VISIBLE_DEVICES=0 python -m vllm.entrypoints.openai.api_server \
  "${COMMON_OPTS[@]}" \
  --port 8000

# GPU 1 → 端口 8001
CUDA_VISIBLE_DEVICES=1 python -m vllm.entrypoints.openai.api_server \
  "${COMMON_OPTS[@]}" \
  --port 8001

# GPU 2 → 端口 8002
CUDA_VISIBLE_DEVICES=2 python -m vllm.entrypoints.openai.api_server \
  "${COMMON_OPTS[@]}" \
  --port 8002

