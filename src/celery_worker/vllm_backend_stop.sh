#!/usr/bin/env bash
set -euo pipefail

echo "Stopping vLLM API servers..."
# 匹配完整命令行防止误杀
# 使用pattern kill来匹配所有的该名称的进程，实现安全和覆盖所有实例的进程终止
pkill -f "vllm.entrypoints.openai.api_server" || echo "No vLLM servers found."

echo "All vLLM servers stopped."