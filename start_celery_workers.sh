#!/usr/bin/env bash

# -e: 如果任何命令执行失败（返回非零退出码），则立即退出脚本
# -u: 如果使用未定义的变量，则报错并退出
# -o pipefail: 如果管道中的任何命令失败，则整个管道命令被视为失败
# set命令用于设置脚本的运行环境，确保脚本在执行过程中符合预期的行为
set -euo pipefail

# 获取脚本所在目录的绝对路径
# $0: 脚本的名称或路径
# dirname "$0": 获取脚本所在目录的路径
# cd "$(dirname "$0")": 切换到脚本所在目录
# pwd: 获取当前工作目录的绝对路径
# 这里使用了&&逻辑与运算的短路性质，确保只有在dirname "$0"成功执行后，才会执行pwd命令
# 这是一种安全的路径获取方式，避免了在脚本所在目录不存在时，pwd命令返回错误结果的问题
DIR="$(cd "$(dirname "$0")" && pwd)"

# 获取仓库根目录的绝对路径
# realpath: 一个用于将相对路径转换为绝对路径的命令
# 这里使用realpath命令将脚本所在目录的路径转换为绝对路径
# 这是为了确保后续操作基于正确的目录路径进行
REPO_ROOT="$(realpath "$DIR")"

# 定义日志目录和文件路径
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/celery_worker.log"
PID_FILE="$LOG_DIR/celery_worker.pid"

# 定义停止worker进程的函数
# 在这个脚本中不同的行为使用不同的函数，如启动、停止、重启等
stop_workers() {
  # 声明局部变量，这个变量只在stop_workers函数中有效
  # 用于存储从PID文件中读取的进程ID
  local PID=""
  
  # 检查PID文件是否存在
  # -f: 测试文件是否存在且为普通文件
  if [[ -f "$PID_FILE" ]]; then
    # 读取PID文件内容，获取进程ID
    # || true: 即使cat命令失败（如文件为空），也不会导致脚本退出
    # 这里的逻辑或运算是一种保护机制
    PID="$(cat "$PID_FILE" || true)"
  fi
  
  # 如果PID不为空，则终止相关进程
  # -n: 测试字符串是否非空
  if [[ -n "$PID" ]]; then
    # pkill: 根据进程名或其他属性终止进程
    # -TERM: 发送TERM信号（请求进程优雅退出） 等效kill命令的-15信号
    # -g: 终止指定进程组中的所有进程
    # -f: 匹配完整的命令行
    # || true: 即使pkill失败（如进程不存在），也不会导致脚本退出
    pkill -TERM -g "$PID" -f 'vllm::enginecore' || true
  fi
  
  # 终止Celery worker进程
  pkill -TERM -f 'celery.*-A src.celery_worker.pdf_process_worker' || true
  pkill -TERM -f 'python.*src/celery_worker/pdf_process_worker.py' || true
  
  # 等待进程优雅退出，最多等待10秒（20次循环，每次0.5秒）
  # seq 1 20: 生成1到20的数字序列
  for i in $(seq 1 20); do
    # pgrep: 查找匹配条件的进程
    # >/dev/null: 将输出重定向到/dev/null，不显示在终端上
    # ||: 逻辑或，如果前一个命令成功，则不执行后一个命令
    # \: 行继续符，表示命令在下一行继续
    if pgrep -f 'celery.*-A src.celery_worker.pdf_process_worker' >/dev/null || \
       pgrep -f 'python.*src/celery_worker/pdf_process_worker.py' >/dev/null; then
      # 如果进程仍在运行，等待0.5秒
      sleep 0.5
    else
      # 如果进程已退出，跳出循环
      break
    fi
  done
  
  # 如果进程仍在运行，强制终止
  # -KILL: 发送KILL信号（强制进程立即退出，无法被忽略）
  pkill -KILL -f 'celery.*-A src.celery_worker.pdf_process_worker' || true
  pkill -KILL -f 'python.*src/celery_worker/pdf_process_worker.py' || true
  
  # 如果PID不为空，强制终止VLLM进程
  if [[ -n "$PID" ]]; then
    pkill -KILL -g "$PID" -f 'VLLM::EngineCore' || true
  fi
}

# 定义启动worker进程的函数
start_workers() {
  # 创建日志目录，如果目录已存在则不报错
  # -p: 创建父目录（如果需要）
  mkdir -p "$LOG_DIR"
  
  # 切换到仓库根目录
  cd "$REPO_ROOT"
  
  # 设置环境变量，类似于Python中的os.environ
  export MINERU_MODEL_SOURCE="modelscope"
  export MINERU_VLM_FORMULA_ENABLE="true"
  export MINERU_VLM_TABLE_ENABLE="true"
  
  # 在后台启动worker进程
  # nohup: 使进程在用户退出后继续运行
  # setsid: 在新的会话中运行进程，使其不受当前终端的影响
  # poetry run: 使用Poetry管理Python环境并运行命令
  # >>"$LOG_FILE": 将标准输出重定向到日志文件（追加模式）
  # 2>&1: 将标准错误重定向到标准输出（即也写入日志文件）
  # &: 在后台运行命令
  nohup setsid poetry run python src/celery_worker/pdf_process_worker.py >>"$LOG_FILE" 2>&1 &
  
  # 将后台进程的PID保存到文件
  # $!: 最后一个后台进程的PID
  echo $! > "$PID_FILE"
}

# 根据第一个命令行参数执行不同的操作
# ${1:-}: 获取第一个参数，如果未提供则为空字符串
case "${1:-}" in
  start)
    # 启动服务：先停止现有进程，然后启动新进程
    stop_workers
    start_workers
    ;;
  stop)
    # 停止服务
    stop_workers
    ;;
  restart)
    # 重启服务：先停止现有进程，然后启动新进程
    stop_workers
    start_workers
    ;;
  *)
    # 如果参数不是start、stop或restart，显示使用说明
    # >&2: 将输出重定向到标准错误（通常用于错误消息）
    echo "Usage: $0 {start|stop|restart}" >&2
    # 以非零状态码退出，表示错误
    exit 1
    ;;
esac