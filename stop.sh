#!/bin/bash

# 查找并终止所有包含指定路径的进程
echo "正在查找包含 'src/mineru_service.py' 的进程..."

# 获取进程ID列表
# 语法点：$() 是命令替换，会执行括号内的命令并将输出结果作为字符串赋值给变量 pids
# 语法点：| 是管道符，将前一个命令的输出作为下一个命令的输入
# ps -ef: 列出所有进程的详细信息
# grep '...': 过滤（保留）包含指定字符串的行
# grep -v grep: 排除掉包含 'grep' 自身的进程行，防止误杀自己
# awk '{print $2}': 使用 awk 提取每行的第二列（通常是 PID 进程ID）
# 输出形式：用户ID|进程ID|父进程ID|CPU使用率|启动时间|终端|累计CPU时间|命令
pids=$(ps -ef | grep 'src/mineru_service.py' | grep -v grep | awk '{print $2}')

# 语法点：if [ condition ]; then ... fi 是条件判断结构
# 语法点：-z 用于检查字符串长度是否为0（即是否为空）
# 注意：变量 $pids 最好用双引号包围，防止因空格或空值导致的语法错误
if [ -z "$pids" ]; then
	    echo "没有找到相关进程"
        # 语法点：exit 0 表示脚本正常退出，返回状态码 0
	    exit 0
fi

echo "找到以下相关进程:"
# 再次执行查找命令，这次是为了展示给用户看具体的进程信息
ps -ef | grep 'src/mineru_service.py' | grep -v grep

# 确认是否终止
# 语法点：read -p "prompt" variable 读取用户输入并存入 confirm 这个变量，-p指定提示信息
read -p "确定要终止这些进程吗? [y/N] " confirm

# 语法点：${var:-default} 是参数扩展语法
# 如果 confirm 变量为空（用户直接回车），则将其设置为默认值 'N'
confirm=${confirm:-N}

# 语法点：[[ ... ]] 是 Bash 的增强测试命令，支持更多功能
# 语法点：=~ 是正则匹配操作符
# ^[Yy]$ 表示匹配以 Y 或 y 开头且结尾的字符串（即精确匹配 Y 或 y）
# 检查用户输入的确认信息是否为"y"或"Y"，如果是则执行终止进程的操作。
if [[ $confirm =~ ^[Yy]$ ]]; then
    echo "正在终止进程..."
    # 语法点：for var in list; do ... done 是循环结构
    # 这里遍历 pids 变量中的每一个 PID
    for pid in $pids; do
        # 使用 $pid 引用变量的值
        echo "终止进程ID: $pid"
        # 语法点：kill -9 发送 SIGKILL 信号，强制杀死进程
        kill -9 $pid
    # 语法点：done 结束 for 循环，等于是do后面行为的休止符
    done
    echo "操作完成"
else
    echo "取消操作"
fi