#!/usr/bin/env bash
set -e  # 出现错误则退出

# 1. 确保在项目根目录执行
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

echo "📦 配置 Poetry 在项目目录创建虚拟环境…"
poetry config virtualenvs.in-project true

echo "🧩 安装依赖（如果首次运行，会创建 .venv）…"
poetry install

echo "⚙️ 构建项目分发包…"
poetry build

echo "🎯 执行项目测试…"
poetry run pytest

echo "✅ 构建完成！虚拟环境路径为："
poetry env info --path

# 如果需要进入虚拟环境：
# eval "$(poetry env info --path)/bin/activate"
