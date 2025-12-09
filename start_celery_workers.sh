#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(realpath "$DIR")"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/celery_worker.log"
PID_FILE="$LOG_DIR/celery_worker.pid"

stop_workers() {
  local PID=""
  if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE" || true)"
  fi
  pkill -TERM -f 'celery.*-A src.celery_worker.pdf_process_worker' || true
  pkill -TERM -f 'python.*src/celery_worker/pdf_process_worker.py' || true
  for i in $(seq 1 20); do
    if pgrep -f 'celery.*-A src.celery_worker.pdf_process_worker' >/dev/null || \
       pgrep -f 'python.*src/celery_worker/pdf_process_worker.py' >/dev/null; then
      sleep 0.5
    else
      break
    fi
  done
  pkill -KILL -f 'celery.*-A src.celery_worker.pdf_process_worker' || true
  pkill -KILL -f 'python.*src/celery_worker/pdf_process_worker.py' || true
}

start_workers() {
  mkdir -p "$LOG_DIR"
  cd "$REPO_ROOT"
  export MINERU_MODEL_SOURCE="modelscope"
  export MINERU_VLM_FORMULA_ENABLE="true"
  export MINERU_VLM_TABLE_ENABLE="true"
  nohup setsid poetry run python src/celery_worker/pdf_process_worker.py >>"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
}

case "${1:-}" in
  start)
    stop_workers
    start_workers
    ;;
  stop)
    stop_workers
    ;;
  restart)
    stop_workers
    start_workers
    ;;
  *)
    echo "Usage: $0 {start|stop|restart}" >&2
    exit 1
    ;;
esac