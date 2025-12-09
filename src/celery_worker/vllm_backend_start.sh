#!/usr/bin/env bash
set -euo pipefail

# 指定HF_ENDPOINT，使用镜像加速，解决国内无法访问HuggingFace的问题
# 修改点：使用 ${HF_ENDPOINT:-...} 语法
# 如果没有从外部获取HF_ENDPOINT，那么使用一个默认值
# 其实在外面已经设置了这些环境变量，但是作为防御性措施，这里再设置一次
export HF_ENDPOINT=${HF_ENDPOINT:-https://hf-mirror.com}
# 增加 RPC 超时时间 (毫秒)，防止多实例启动时 CPU 争抢导致握手超时
# 这个问题是vllm的v1引擎引入的问题
export VLLM_RPC_TIMEOUT=${VLLM_RPC_TIMEOUT:-120000}

# 定义日志目录 (项目根目录/logs)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# 基础临时目录，用于存放隔离的 Socket 文件
BASE_TMP_DIR="/tmp/vllm_sockets"
mkdir -p "$BASE_TMP_DIR"

# MinerU的vlm模型名称
# 允许外部环境变量 MODEL 覆盖默认模型
MODEL="${MODEL:-opendatalab/MinerU2.5-2509-1.2B}"
COMMON_OPTS=(
  --model "$MODEL"
  --host "0.0.0.0"
  --tensor-parallel-size 1
  --gpu-memory-utilization 0.5
  --trust-remote-code
)

# 默认使用 GPU 0, 1, 2 (兼容旧逻辑)
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
echo "Detected CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"

# 将逗号分隔的字符串转换为数组
# 替换逗号为空格，然后转为数组
IFS=',' read -r -a GPU_IDS <<< "$CUDA_VISIBLE_DEVICES"

# 遍历每个 GPU ID 启动 vLLM 实例
for i in "${!GPU_IDS[@]}"; do
  GPU_ID="${GPU_IDS[$i]}"
  PORT=$((8000 + i)) # 端口从 8000 开始递增
  
  echo "Starting vLLM on GPU $GPU_ID (Port: $PORT)..."
  
  # 为每个实例创建独立的临时目录
  INSTANCE_TMP_DIR="$BASE_TMP_DIR/gpu$GPU_ID"
  mkdir -p "$INSTANCE_TMP_DIR"
  
  # 启动 vLLM
  # 注意：这里重新设置 CUDA_VISIBLE_DEVICES 为单个 ID，确保 vLLM 只看到这一张卡
  nohup env CUDA_VISIBLE_DEVICES="$GPU_ID" TMPDIR="$INSTANCE_TMP_DIR" poetry run python -m vllm.entrypoints.openai.api_server \
    "${COMMON_OPTS[@]}" \
    --port "$PORT" > "$LOG_DIR/vllm_gpu$GPU_ID.log" 2>&1 &
    
  # 如果不是最后一个实例，等待一段时间错峰启动
  if [ "$i" -lt $((${#GPU_IDS[@]} - 1)) ]; then
      echo "Waiting 10s before starting next instance..."
      sleep 10
  fi
done

echo "vLLM servers started on GPUs: ${GPU_IDS[*]}. Logs are in $LOG_DIR"