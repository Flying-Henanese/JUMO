#!/bin/bash

# 查找并终止所有包含指定路径的进程
echo "正在查找包含 '/opt/mineru-service/mineru-service/' 的进程..."

# 获取进程ID列表
pids=$(ps -ef | grep '/opt/mineru-service/mineru-service/' | grep -v grep | awk '{print $2}')

if [ -z "$pids" ]; then
	    echo "没有找到相关进程"
	        exit 0
fi

echo "找到以下进程:"
ps -ef | grep '/opt/mineru-service/mineru-service/' | grep -v grep

# 确认是否终止
read -p "确定要终止这些进程吗? [y/N] " confirm
confirm=${confirm:-N}

if [[ $confirm =~ ^[Yy]$ ]]; then
    echo "正在终止进程..."
    for pid in $pids; do
	echo "终止进程ID: $pid"
	kill -9 $pid
    done
    echo "操作完成"
else
    echo "取消操作"
fi
