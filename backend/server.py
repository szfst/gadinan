"""
闽南话语音助手服务端
语音识别（FunASR）+ 普通话翻译 + DeepSeek 对话
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

from llm import (
    ENV_LOADED_FROM,
    ask_question,
    is_configured,
    log_llm_config,
    translate_to_mandarin,
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="闽南话语音助手 API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEVICE = "cpu"
ASR_MODEL = None
ASR_MODEL_NAME = ""
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

ASR_MODELS = {
    "fun-asr-nano": {
        "label": "Fun-ASR-Nano-2512",
        "min_ram_gb": 4,
        "config": {
            "model": "FunAudioLLM/Fun-ASR-Nano-2512",
            "hub": "ms",
            "trust_remote_code": True,
            "vad_model": "fsmn-vad",
            "vad_kwargs": {"max_single_segment_time": 30000},
        },
        "generate": {"batch_size": 1, "language": "中文", "itn": True},
    },
    "sensevoice": {
        "label": "SenseVoiceSmall",
        "min_ram_gb": 2,
        "config": {
            "model": "iic/SenseVoiceSmall",
            "vad_model": "fsmn-vad",
            "vad_kwargs": {"max_single_segment_time": 30000},
        },
        "generate": {"batch_size": 1},
    },
}


def get_total_ram_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 0.0


def pick_asr_model_name() -> str:
    requested = os.getenv("FUNASR_ASR_MODEL", "fun-asr-nano").strip().lower()
    if requested in ASR_MODELS:
        return requested
    logger.warning("未知模型 %s，使用默认 fun-asr-nano", requested)
    return "fun-asr-nano"


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
    global ASR_MODEL, ASR_MODEL_NAME
    if ASR_MODEL is not None:
        return ASR_MODEL

    from funasr import AutoModel

    ASR_MODEL_NAME = pick_asr_model_name()
    spec = ASR_MODELS[ASR_MODEL_NAME]

    if DEVICE == "cpu":
        apply_cpu_optimizations()

    cfg = {**spec["config"], "device": DEVICE, "disable_update": True}
    logger.info("正在加载 %s 模型（%s）...", spec["label"], DEVICE)
    t0 = time.time()
    ASR_MODEL = AutoModel(**cfg)
    logger.info("模型加载完成，耗时 %.1f 秒", time.time() - t0)
    return ASR_MODEL


def clean_text(text: str) -> str:
    return re.sub(r"<\|[^|]*\|>", "", text).strip()


async def transcribe_audio(content: bytes, suffix: str) -> tuple[str, float]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        model = load_asr_model()
        t0 = time.time()
        gen_kwargs = {"input": tmp_path, **ASR_MODELS[ASR_MODEL_NAME]["generate"]}
        result = model.generate(**gen_kwargs)
        elapsed = time.time() - t0
        return clean_text(result[0]["text"]), elapsed
    finally:
        os.unlink(tmp_path)


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    dialect: Optional[str] = Form(default="minnan"),
):
    """仅语音识别，不调用大模型。"""
    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    content = await file.read()

    try:
        text, elapsed = await transcribe_audio(content, suffix)
        return JSONResponse(
            {
                "text": text,
                "dialect": dialect,
                "duration": round(elapsed, 3),
                "model": ASR_MODELS.get(ASR_MODEL_NAME, {}).get("label", ASR_MODEL_NAME),
            }
        )
    except Exception as e:
        logger.error("识别失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/voice-chat")
async def voice_chat(file: UploadFile = File(...)):
    """
    完整语音对话流程：
    闽南语语音 → 转写 → 翻译普通话 → DeepSeek 回答
    """
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置 DEEPSEEK_API_KEY，请复制 .env.example 为 .env 并填入 Key",
        )

    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    content = await file.read()

    try:
        t0 = time.time()
        dialect_text, asr_duration = await transcribe_audio(content, suffix)
        if not dialect_text:
            raise HTTPException(status_code=400, detail="未识别到语音内容，请重新录音")

        mandarin_text = await translate_to_mandarin(dialect_text)
        answer = await ask_question(mandarin_text)
        total = time.time() - t0

        return JSONResponse(
            {
                "dialect_text": dialect_text,
                "mandarin_text": mandarin_text,
                "answer": answer,
                "asr_duration": round(asr_duration, 3),
                "total_duration": round(total, 3),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("语音对话失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/health")
async def health():
    ram_gb = get_total_ram_gb()
    return {
        "status": "ok",
        "device": DEVICE,
        "asr_model": ASR_MODEL_NAME or pick_asr_model_name(),
        "ram_gb": round(ram_gb, 1) if ram_gb else None,
        "model_loaded": ASR_MODEL is not None,
        "llm_configured": is_configured(),
        "env_file": ENV_LOADED_FROM,
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
    parser = argparse.ArgumentParser(description="闽南话语音助手服务")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--device", default="auto", help="auto / cpu / cuda（无 GPU 自动用 CPU）")
    parser.add_argument("--preload", action="store_true", help="启动时预加载模型")
    args = parser.parse_args()

    global DEVICE
    DEVICE = resolve_device(args.device)

    log_llm_config()

    if args.preload:
        load_asr_model()

    logger.info("服务启动: http://%s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
