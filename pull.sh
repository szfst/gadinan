#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "========================================"
echo "  拉取最新代码"
echo "========================================"

echo "[1/4] 撤销本地修改..."
git checkout .

echo "[2/3] 拉取远程代码..."
git pull

echo "[3/4] 修复脚本换行符并设置权限..."
sed -i 's/\r$//' ./start.sh ./pull.sh 2>/dev/null || true
chmod +x ./start.sh ./pull.sh

echo "[4/4] 完成"

echo "========================================"
echo "  完成，可执行 ./start.sh 启动服务"
echo "========================================"
