#!/bin/bash
set -euo pipefail

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$SCRIPT_DIR"

# Define log function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Paths to component scripts
VLLM_START_SCRIPT="$REPO_ROOT/src/celery_worker/vllm_backend_start.sh"
VLLM_STOP_SCRIPT="$REPO_ROOT/src/celery_worker/vllm_backend_stop.sh"
CELERY_SCRIPT="$REPO_ROOT/start_celery_workers.sh"
SERVICE_START_SCRIPT="$REPO_ROOT/start_service.sh"

# Function to stop MinerU Service (non-interactive version of stop_service.sh)
stop_mineru_service() {
    log "Stopping MinerU Service..."
    # Find process IDs
    # Using the same logic as stop_service.sh but non-interactive
    pids=$(ps -ef | grep 'src/mineru_service.py' | grep -v grep | awk '{print $2}')
    
    if [ -n "$pids" ]; then
        for pid in $pids; do
            log "Killing MinerU Service PID: $pid"
            kill -9 $pid
        done
        log "MinerU Service stopped."
    else
        log "No MinerU Service process found."
    fi
}

start_all() {
    log "Starting all services..."

    # 1. Start vLLM Backend
    log "Step 1/3: Starting vLLM Backend..."
    if [ -f "$VLLM_START_SCRIPT" ]; then
        # Check if vLLM is already running to avoid double start? 
        # The start script doesn't check, it just starts new ones.
        # But stop_all stops them.
        bash "$VLLM_START_SCRIPT"
    else
        log "Error: vLLM start script not found at $VLLM_START_SCRIPT"
        exit 1
    fi

    # 2. Start Celery Workers
    log "Step 2/3: Starting Celery Workers..."
    if [ -f "$CELERY_SCRIPT" ]; then
        bash "$CELERY_SCRIPT" start
    else
        log "Error: Celery script not found at $CELERY_SCRIPT"
        exit 1
    fi

    # 3. Start MinerU Main Service
    log "Step 3/3: Starting MinerU Main Service..."
    if [ -f "$SERVICE_START_SCRIPT" ]; then
        bash "$SERVICE_START_SCRIPT"
    else
        log "Error: Service start script not found at $SERVICE_START_SCRIPT"
        exit 1
    fi
    
    log "All services started successfully."
}

stop_all() {
    log "Stopping all services..."

    # Stop in reverse order of dependency
    
    # 1. Stop MinerU Main Service
    log "Step 1/3: Stopping MinerU Main Service..."
    stop_mineru_service

    # 2. Stop Celery Workers
    log "Step 2/3: Stopping Celery Workers..."
    if [ -f "$CELERY_SCRIPT" ]; then
        bash "$CELERY_SCRIPT" stop
    else
        log "Warning: Celery script not found at $CELERY_SCRIPT"
    fi

    # 3. Stop vLLM Backend
    log "Step 3/3: Stopping vLLM Backend..."
    if [ -f "$VLLM_STOP_SCRIPT" ]; then
        bash "$VLLM_STOP_SCRIPT"
    else
        log "Warning: vLLM stop script not found at $VLLM_STOP_SCRIPT"
    fi
    
    log "All services stopped."
}

# Main logic
case "${1:-}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        # Wait a moment to ensure ports are freed and processes are fully killed
        sleep 5
        start_all
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac