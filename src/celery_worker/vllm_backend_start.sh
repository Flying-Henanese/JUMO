#!/usr/bin/env bash
set -euo pipefail

# 指定HF_ENDPOINT，使用镜像加速，解决国内无法访问HuggingFace的问题
export HF_ENDPOINT=https://hf-mirror.com
# 增加 RPC 超时时间 (毫秒)，防止多实例启动时 CPU 争抢导致握手超时
export VLLM_RPC_TIMEOUT=120000

# 定义日志目录 (项目根目录/logs)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# 基础临时目录，用于存放隔离的 Socket 文件
BASE_TMP_DIR="/tmp/vllm_sockets"
mkdir -p "$BASE_TMP_DIR"

# MinerU的vlm模型名称
MODEL="opendatalab/MinerU2.5-2509-1.2B"
COMMON_OPTS=(
  --model "$MODEL"
  --host "0.0.0.0"
  --tensor-parallel-size 1
  --gpu-memory-utilization 0.5
  --trust-remote-code
)

# GPU 0 → 端口 8000
# 使用 TMPDIR 环境变量隔离 Socket 路径
echo "Starting vLLM on GPU 0..."
export TMPDIR="$BASE_TMP_DIR/gpu0"
mkdir -p "$TMPDIR"
nohup env CUDA_VISIBLE_DEVICES=0 TMPDIR="$TMPDIR" poetry run python -m vllm.entrypoints.openai.api_server \
  "${COMMON_OPTS[@]}" \
  --port 8000 > "$LOG_DIR/vllm_gpu0.log" 2>&1 &

# 错峰启动，减少 CPU 瞬时争抢
sleep 10

# GPU 1 → 端口 8001
echo "Starting vLLM on GPU 1..."
export TMPDIR="$BASE_TMP_DIR/gpu1"
mkdir -p "$TMPDIR"
nohup env CUDA_VISIBLE_DEVICES=1 TMPDIR="$TMPDIR" poetry run python -m vllm.entrypoints.openai.api_server \
  "${COMMON_OPTS[@]}" \
  --port 8001 > "$LOG_DIR/vllm_gpu1.log" 2>&1 &

sleep 10

# GPU 2 → 端口 8002
echo "Starting vLLM on GPU 2..."
export TMPDIR="$BASE_TMP_DIR/gpu2"
mkdir -p "$TMPDIR"
nohup env CUDA_VISIBLE_DEVICES=2 TMPDIR="$TMPDIR" poetry run python -m vllm.entrypoints.openai.api_server \
  "${COMMON_OPTS[@]}" \
  --port 8002 > "$LOG_DIR/vllm_gpu2.log" 2>&1 &

echo "vLLM servers started. Logs are in $LOG_DIR"

