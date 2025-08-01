#!/bin/bash

# 重启 MinerU 服务脚本
# 功能：1. 终止旧进程 2. 重新启动服务（后台运行）

# 定义变量（可修改）
export SGLANG_USE_MODELSCOPE=true
export MINERU_MODEL_SOURCE=modelscope
export CUDA_VISIBLE_DEVICES=6
PORT=30000
MODEL_PATH="OpenDataLab/MinerU2.0-2505-0.9B"
LOG_FILE="mineru_sglang_server.log"

# 1. 终止现有服务
echo "正在停止 MinerU 服务..."
pids=$(pgrep -f "mineru-sglang-server.*--port $PORT")
if [ -n "$pids" ]; then
    echo "找到运行中的进程(PID): $pids"
    # 先尝试正常终止
    kill -15 $pids 2>/dev/null
    sleep 5
    # 检查是否仍有残留进程
    remaining=$(pgrep -f "mineru-sglang-server.*--port $PORT")
    if [ -n "$remaining" ]; then
        echo "强制终止残留进程..."
        kill -9 $remaining
    fi
    echo "服务已停止"
else
    echo "没有找到运行中的 MinerU 服务"
fi

# 2. 启动新服务（后台运行）
echo "启动 MinerU 服务..."
nohup poetry run mineru-sglang-server --port $PORT --model-path $MODEL_PATH > $LOG_FILE 2>&1 &

# 3. 验证服务状态
sleep 30
new_pid=$(pgrep -f "mineru-sglang-server.*--port $PORT")
if [ -n "$new_pid" ]; then
    echo "✅ 服务启动成功！"
    echo "PID: $new_pid"
    echo "日志文件: $LOG_FILE"
    echo "端口: $PORT"
    echo "GPU: $CUDA_VISIBLE_DEVICES"
else
    echo "❌ 服务启动失败，请检查日志: $LOG_FILE"
    exit 1
fi
