#!/bin/bash
set -euo pipefail

# 获取脚本所在目录（项目根目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$SCRIPT_DIR"

# ==========================================
# 配置区域 (Configuration)
# ==========================================
# 在这里定义的环境变量会被子脚本继承
# 你可以在这里修改模型名称、镜像地址等

# 设置 MinerU 使用的模型名称
export MODEL="${MODEL:-opendatalab/MinerU2.5-2509-1.2B}"

# 设置 HuggingFace 镜像地址
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

# 设置 RPC 超时时间
export VLLM_RPC_TIMEOUT="${VLLM_RPC_TIMEOUT:-120000}"

# 设置使用的 GPU 设备 ID (逗号分隔)
# vLLM 启动脚本会根据这里的 ID 数量自动启动对应数量的实例
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2}"

# 设置API服务端口
export API_SERVICE_PORT="${API_SERVICE_PORT:-5116}"

# 设置 Python 和 Celery 解释器路径
# 如果环境变量未设置（例如在宿主机），默认使用项目目录下的虚拟环境
export PYTHON_PATH="${PYTHON_PATH:-$REPO_ROOT/.venv/bin/python}"
export CELERY_PATH="${CELERY_PATH:-$REPO_ROOT/.venv/bin/celery}"

# ==========================================

# 定义日志输出函数，带时间戳
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# 定义子脚本的绝对路径
VLLM_START_SCRIPT="$REPO_ROOT/src/celery_worker/vllm_backend_start.sh"
VLLM_STOP_SCRIPT="$REPO_ROOT/src/celery_worker/vllm_backend_stop.sh"
CELERY_SCRIPT="$REPO_ROOT/start_celery_workers.sh"
SERVICE_START_SCRIPT="$REPO_ROOT/start_service.sh"

# 停止 MinerU 主服务的函数
# 原 stop_service.sh 是交互式的，这里改为自动执行以便集成
stop_mineru_service() {
    log "正在停止 MinerU Service..."
    # 查找进程ID
    pids=$(ps -ef | grep 'src/mineru_service.py' | grep -v grep | awk '{print $2}')
    
    if [ -n "$pids" ]; then
        for pid in $pids; do
            log "终止 MinerU Service 进程 ID: $pid"
            kill -9 $pid
        done
        log "MinerU Service 已停止"
    else
        log "未发现正在运行的 MinerU Service 进程"
    fi
}

# 捕获系统信号 (SIGTERM, SIGINT) 以便优雅退出
trap 'stop_all; exit 0' SIGTERM SIGINT

# 启动所有服务
start_all() {
    log ">>> 开始按顺序启动所有服务..."

    # 1. 启动 vLLM Backend (推理后端)
    log "步骤 1/3: 启动 vLLM Backend..."
    if [ -f "$VLLM_START_SCRIPT" ]; then
        bash "$VLLM_START_SCRIPT"
        # vLLM 脚本中有 sleep，但为了保险起见，这里可以再稍作等待确保端口监听就绪
        sleep 2
    else
        log "错误: 未找到 vLLM 启动脚本: $VLLM_START_SCRIPT"
        exit 1
    fi

    # 2. 启动 Celery Workers (任务队列处理)
    log "步骤 2/3: 启动 Celery Workers..."
    if [ -f "$CELERY_SCRIPT" ]; then
        bash "$CELERY_SCRIPT" start
    else
        log "错误: 未找到 Celery 脚本: $CELERY_SCRIPT"
        exit 1
    fi

    # 3. 启动 MinerU Main Service (Web 服务入口)
    log "步骤 3/3: 启动 MinerU Main Service..."
    if [ -f "$SERVICE_START_SCRIPT" ]; then
        bash "$SERVICE_START_SCRIPT"
    else
        log "错误: 未找到服务启动脚本: $SERVICE_START_SCRIPT"
        exit 1
    fi
    
    log ">>> 所有服务启动序列已完成"

    # 如果存在 /.dockerenv 文件，说明在容器内，需要挂起主进程
    if [ -f /.dockerenv ]; then
        log "Running inside Docker container. Keeping process alive..."
        # 挂起进程，直到接收到信号
        tail -f /dev/null &
        wait $!
    else
        log "Running on Host machine. Services started in background."
    fi
}

# 停止所有服务
stop_all() {
    log ">>> 开始按相反顺序停止所有服务..."

    # 1. 停止 MinerU Main Service
    # 最先停止入口，不再接收新请求
    log "步骤 1/3: 停止 MinerU Main Service..."
    stop_mineru_service

    # 2. 停止 Celery Workers
    log "步骤 2/3: 停止 Celery Workers..."
    if [ -f "$CELERY_SCRIPT" ]; then
        bash "$CELERY_SCRIPT" stop
    else
        log "警告: 未找到 Celery 脚本: $CELERY_SCRIPT"
    fi

    # 3. 停止 vLLM Backend
    # 最后停止底层的推理服务
    log "步骤 3/3: 停止 vLLM Backend..."
    if [ -f "$VLLM_STOP_SCRIPT" ]; then
        bash "$VLLM_STOP_SCRIPT"
    else
        log "警告: 未找到 vLLM 停止脚本: $VLLM_STOP_SCRIPT"
    fi
    
    log ">>> 所有服务已停止"
}

# 主逻辑：根据命令行参数执行相应操作
case "${1:-}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        # 等待几秒钟，确保端口释放和进程完全清理
        log "等待 5 秒以确保进程完全退出..."
        sleep 5
        start_all
        ;;
    *)
        echo "用法: $0 {start|stop|restart}"
        exit 1
        ;;
esac