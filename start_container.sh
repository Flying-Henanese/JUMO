#!/bin/bash
set -e

# ==============================================================================
# 自动启动 MinerU Service 容器脚本
# 功能：自动查找最新 mineru-service 镜像并启动，挂载所有模型缓存目录
# ==============================================================================

# 1. 查找 mineru-service 镜像 (获取当前宿主机中最新的一个)
IMAGE_NAME="mineru-service"
# 使用 -q 获取 ID，head -n 1 获取最新的那个 (按创建时间排序)
IMAGE_ID=$(docker images -q "$IMAGE_NAME" | head -n 1)

if [ -z "$IMAGE_ID" ]; then
    echo "错误: 未找到名称为 $IMAGE_NAME 的镜像。"
    echo "请先构建镜像: docker build -t $IMAGE_NAME ."
    exit 1
fi

echo "找到最新的镜像 $IMAGE_NAME ID: $IMAGE_ID"

# 2. 定义容器名称
CONTAINER_NAME="mineru_service_pequod"

# 3. 如果容器已存在，先停止并删除，避免名称冲突
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "发现旧容器 $CONTAINER_NAME，正在停止并删除..."
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
fi

echo "正在启动新容器 $CONTAINER_NAME ..."

# 4. 启动容器
# -d: 后台运行
# --gpus all: 开启 GPU 支持（这里只是让GPU可见，并不是实际使用GPU，具体还是要通过cuda_visible_devices指定）
# --shm-size 16g: 增加共享内存防止 OOM (vLLM/PyTorch 需要)
# -p 5116:5116: 映射 API 端口
# -p 30000:30000: 映射辅助端口
# -v: 挂载宿主机缓存目录 (复用模型文件，避免重复下载)
docker run -d \
    --gpus all \
    --name "$CONTAINER_NAME" \
    --shm-size 16g \
    -p 5116:5116 \
    -p 30000:30000 \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -v ~/.cache/modelscope:/root/.cache/modelscope \
    -v ~/.cache/vllm:/root/.cache/vllm \
    -v ~/nltk_data:/root/nltk_data \
    -v "$(pwd)/logs:/app/logs" \
    -v "$(pwd)/src:/app/src" \
    "$IMAGE_ID"

echo "--------------------------------------------------"
echo "容器启动成功！"
echo "容器名称: $CONTAINER_NAME"
echo "镜像 ID : $IMAGE_ID"
echo "查看日志: docker logs -f $CONTAINER_NAME"
echo "停止容器: docker stop $CONTAINER_NAME"
echo "--------------------------------------------------"