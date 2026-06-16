#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "========================================"
echo "  拉取最新代码"
echo "========================================"

echo "[1/3] 撤销本地修改..."
git checkout .

echo "[2/3] 拉取远程代码..."
git pull

echo "[3/3] 设置启动脚本权限..."
chmod +x ./start.sh

echo "========================================"
echo "  完成，可执行 ./start.sh 启动服务"
echo "========================================"
