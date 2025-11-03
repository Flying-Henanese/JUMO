#!/bin/bash

# 检测并关闭正在运行的mineru_service进程
PID=$(ps aux | grep "python src/mineru_service.py" | grep -v grep | awk '{print $2}')
if [ ! -z "$PID" ]; then
    echo "发现正在运行的mineru_service进程(PID: $PID)，正在停止..."
    kill -9 $PID
    sleep 2
fi

# 设置HuggingFace镜像站点（用于国内访问）
export HF_ENDPOINT=https://hf-mirror.com

# 设置MinerU模型下载源（使用ModelScope避免HuggingFace访问问题）
export MINERU_MODEL_SOURCE=modelscope
# 开启表格识别和公式识别
export MINERU_VLM_FORMULA_ENABLE=true
export MINERU_VLM_TABLE_ENABLE=true
# 指定要使用的CUDA设备编号
export CUDA_VISIBLE_DEVICES="3"
# 可选：设置MinerU设备模式（如果需要指定特定设备）
# 前面已经制定了cuda:7，这里可以指定为cuda:0
export MINERU_DEVICE_MODE=cuda:0

# 使用poetry run启动服务
nohup poetry run python src/mineru_service.py > output.log 2>&1 &
