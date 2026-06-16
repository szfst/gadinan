"""
闽南话语音识别服务端
基于 FunASR 1.x + Fun-ASR-Nano 模型，支持闽语（闽南话）方言识别
"""

import argparse
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="闽南话语音识别 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEVICE = "cpu"
ASR_MODEL = None
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

MODEL_CONFIG = {
    "model": "FunAudioLLM/Fun-ASR-Nano-2512",
    "hub": "ms",
    "trust_remote_code": True,
    "vad_model": "fsmn-vad",
    "vad_kwargs": {"max_single_segment_time": 30000},
}


def resolve_device(requested: str) -> str:
    """无 GPU 时自动回退到 CPU。"""
    import torch

    if requested in ("auto", ""):
        if torch.cuda.is_available():
            logger.info("检测到 GPU，使用 CUDA 加速")
            return "cuda:0"
        logger.info("未检测到 GPU，使用 CPU 模式（适合低配机器）")
        return "cpu"

    if requested.startswith("cuda"):
        if torch.cuda.is_available():
            return requested if ":" in requested else "cuda:0"
        logger.warning("指定了 GPU 但当前不可用，已自动切换为 CPU")
        return "cpu"

    return requested


def apply_cpu_optimizations():
    """低配 CPU 机器：限制线程数，降低内存占用。"""
    import torch

    threads = min(4, os.cpu_count() or 4)
    torch.set_num_threads(threads)
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(threads))
    logger.info("CPU 优化：推理线程数=%d", threads)


def load_asr_model():
    global ASR_MODEL
    if ASR_MODEL is not None:
        return ASR_MODEL

    from funasr import AutoModel

    if DEVICE == "cpu":
        apply_cpu_optimizations()

    cfg = {**MODEL_CONFIG, "device": DEVICE, "disable_update": True}
    logger.info("正在加载 Fun-ASR-Nano 模型（%s，支持闽语/闽南话）...", DEVICE)
    t0 = time.time()
    ASR_MODEL = AutoModel(**cfg)
    logger.info("模型加载完成，耗时 %.1f 秒", time.time() - t0)
    return ASR_MODEL


def clean_text(text: str) -> str:
    return re.sub(r"<\|[^|]*\|>", "", text).strip()


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    dialect: Optional[str] = Form(default="minnan"),
):
    """
    接收音频文件，识别闽南话并返回文字结果。
    dialect: 方言类型，默认 minnan（闽南话/闽语）
    """
    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        model = load_asr_model()
        t0 = time.time()

        # Fun-ASR-Nano 支持 7 大方言（含闽语），设置 language="中文" 即可识别闽南话
        result = model.generate(
            input=tmp_path,
            batch_size=1,
            language="中文",
            itn=True,
        )
        elapsed = time.time() - t0
        text = clean_text(result[0]["text"])

        return JSONResponse(
            {
                "text": text,
                "dialect": dialect,
                "duration": round(elapsed, 3),
                "model": "Fun-ASR-Nano-2512",
            }
        )
    except Exception as e:
        logger.error("识别失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        os.unlink(tmp_path)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "model_loaded": ASR_MODEL is not None,
        "dialect_support": ["minnan", "闽语", "闽南话"],
    }


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")


def main():
    parser = argparse.ArgumentParser(description="闽南话语音识别服务")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--device", default="auto", help="auto / cpu / cuda（无 GPU 自动用 CPU）")
    parser.add_argument("--preload", action="store_true", help="启动时预加载模型")
    args = parser.parse_args()

    global DEVICE
    DEVICE = resolve_device(args.device)

    if args.preload:
        load_asr_model()

    logger.info("服务启动: http://%s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
