#!/bin/bash

# 检测并关闭正在运行的mineru_service进程
PID=$(ps aux | grep "python src/mineru_service.py" | grep -v grep | awk '{print $2}')
if [ ! -z "$PID" ]; then
    echo "发现正在运行的mineru_service进程(PID: $PID)，正在停止..."
    kill -9 s$PID
    sleep 2
fi

# 使用nohup和poetry run启动服务，并将日志输出到output.log
poetry run python src/mineru_service.py