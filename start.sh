#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"

echo "========================================"
echo "  闽南话语音识别 - 编译与启动"
echo "========================================"

# ---------- Python 虚拟环境 ----------
if [ ! -f "$VENV_DIR/bin/activate" ]; then
  if [ -d "$VENV_DIR" ]; then
    echo "[1/4] 虚拟环境不完整，正在重建..."
    rm -rf "$VENV_DIR"
  else
    echo "[1/4] 创建 Python 虚拟环境..."
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "错误: 未找到 python3，请先安装: apt install python3 python3-venv python3-pip"
    exit 1
  fi
  python3 -m venv "$VENV_DIR"
else
  echo "[1/4] Python 虚拟环境已存在，跳过创建"
fi

echo "[2/4] 安装 Python 依赖（FunASR 1.x，CPU 版 PyTorch）..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install -q --upgrade pip
pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -q -r "$BACKEND_DIR/requirements.txt"

# ---------- 前端构建 ----------
echo "[3/4] 安装前端依赖并构建..."
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
  npm install
else
  echo "      node_modules 已存在，跳过 npm install"
fi
npm run build

# ---------- 启动服务 ----------
echo "[4/4] 启动后端服务..."
cd "$BACKEND_DIR"

DEVICE="${FUNASR_DEVICE:-auto}"
PORT="${FUNASR_PORT:-8000}"
HOST="${FUNASR_HOST:-0.0.0.0}"

echo ""
echo "  设备: $DEVICE（无 GPU 时自动使用 CPU）"
echo "  地址: http://localhost:$PORT"
echo "  首次识别会自动下载模型，CPU 模式下请耐心等待"
echo "========================================"

exec "$VENV_DIR/bin/python" server.py --host "$HOST" --port "$PORT" --device "$DEVICE" --preload
