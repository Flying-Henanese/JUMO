#!/usr/bin/env bash
set -euo pipefail

PY_BIN="${PYTHON_PATH:-python}"
exec "$PY_BIN" -u /app/src/celery_worker/vllm_backend_start.py