#!/bin/bash

# 检测并关闭正在运行的mineru_service进程
PID=$(ps aux | grep "python src/mineru_service.py" | grep -v grep | awk '{print $2}')
if [ ! -z "$PID" ]; then
    echo "发现正在运行的mineru_service进程(PID: $PID)，正在停止..."
    kill -9 s$PID
    sleep 2
fi

# 使用nohup和poetry run启动服务，并将日志输出到output.log
nohup poetry run python src/mineru_service.py > output.log 2>&1 &

# 显示进程信息和日志文件路径
echo "服务已启动，PID: $!"
echo "日志输出到: /output.log"