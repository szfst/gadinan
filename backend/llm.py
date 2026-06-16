import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

ENV_LOADED_FROM: str | None = None


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def load_env() -> str | None:
    """加载 .env，返回实际使用的文件路径。"""
    global ENV_LOADED_FROM
    backend_dir = Path(__file__).parent
    for env_path in (backend_dir.parent / ".env", backend_dir / ".env"):
        if env_path.is_file():
            load_dotenv(env_path, override=True)
            ENV_LOADED_FROM = str(env_path.resolve())
            return ENV_LOADED_FROM
    ENV_LOADED_FROM = None
    return None


def log_llm_config() -> None:
    """启动时打印 DeepSeek 配置加载状态（Key 脱敏）。"""
    env_path = ENV_LOADED_FROM or load_env()
    api_key = _get_api_key()
    model = _get_model()
    base_url = _get_base_url()

    if env_path:
        logger.info("[DeepSeek] .env 已加载: %s", env_path)
    else:
        logger.warning("[DeepSeek] 未找到 .env 文件（请在项目根目录创建）")

    if api_key:
        logger.info(
            "[DeepSeek] API Key 加载成功 ✓  key=%s  model=%s  base_url=%s",
            _mask_key(api_key),
            model,
            base_url,
        )
    else:
        logger.warning(
            "[DeepSeek] API Key 未配置 ✗  请在 .env 中设置 DEEPSEEK_API_KEY=sk-..."
        )


def _get_api_key() -> str:
    return os.getenv("DEEPSEEK_API_KEY", "").strip()


def _get_base_url() -> str:
    return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")


def _get_model() -> str:
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()


def is_configured() -> bool:
    return bool(_get_api_key())


async def _chat(messages: list[dict]) -> str:
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("未配置 DEEPSEEK_API_KEY，请在项目根目录 .env 文件中设置")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{_get_base_url()}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _get_model(),
                "messages": messages,
                "stream": False,
            },
        )
        if resp.status_code != 200:
            detail = resp.text[:500]
            raise RuntimeError(f"DeepSeek API 错误 ({resp.status_code}): {detail}")
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def translate_to_mandarin(dialect_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是精通闽南语（闽南话、河洛话、潮汕近缘方言）的翻译专家。"
                "输入是闽南语语音识别转写，常有谐音字、同音别字，请按闽南语口语习惯还原原意，"
                "输出标准普通话。只输出翻译结果，不要解释。"
            ),
        },
        {"role": "user", "content": dialect_text},
    ]
    return await _chat(messages)


async def translate_to_minnan(mandarin_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是闽南语（闽南话）口语翻译专家，熟悉泉州、厦门、漳州腔。"
                "将下文翻译为地道闽南语口语，用汉字书写（如「食」「佮」「恁」「啥物」），"
                "避免书面文言文。只输出闽南语译文，不要 Markdown，不要解释。"
            ),
        },
        {"role": "user", "content": mandarin_text},
    ]
    return await _chat(messages)


def _parse_tagged_response(raw: str) -> tuple[str, str]:
    import re

    match = re.search(r"<<<MANDARIN>>>\s*(.*?)\s*<<<ANSWER>>>\s*(.*)", raw, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # 兼容旧格式
    match2 = re.search(r"普通话[：:]\s*(.+?)\s*回答[：:]\s*(.+)", raw, re.DOTALL)
    if match2:
        return match2.group(1).strip(), match2.group(2).strip()

    logger.warning("闽南语回复格式解析失败，回退为全文回答")
    return "", raw.strip()


async def ask_from_dialect(
    dialect_text: str, history: list[dict] | None = None
) -> tuple[str, str]:
    """
    一步完成：理解闽南语转写 + 生成普通话回答。
    比「先翻译再问答」更少误差累积，DeepSeek 直接理解闽南语。
    返回 (普通话理解, 回答)
    """
    messages = [
        {
            "role": "system",
            "content": (
                "你是精通闽南语（闽南话、河洛话）的语音助手。"
                "用户用闽南话与你对话，输入是语音识别转写，常有谐音字、错别字或夹杂普通话，"
                "请按闽南语语法和发音习惯理解真实意图，再结合对话历史回答。"
                "严格按以下格式输出，不要输出标记以外的多余说明：\n"
                "<<<MANDARIN>>>\n"
                "（用户这句话的普通话含义）\n"
                "<<<ANSWER>>>\n"
                "（用简洁清晰的中文回答，可使用 Markdown）"
            ),
        },
    ]
    if history:
        messages.extend(history[-20:])
    messages.append({"role": "user", "content": dialect_text})

    raw = await _chat(messages)
    mandarin, answer = _parse_tagged_response(raw)
    if not mandarin:
        mandarin = await translate_to_mandarin(dialect_text)
    if not answer:
        answer = raw
    return mandarin, answer


async def ask_question(mandarin_text: str, history: list[dict] | None = None) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个有帮助的 AI 助手。请用简洁清晰的中文回答用户的问题。"
                "用户可能连续多轮提问，请结合上下文理解。"
                "回答请使用 Markdown 格式（标题、列表、加粗等），让内容结构清晰。"
            ),
        },
    ]
    if history:
        messages.extend(history[-20:])
    messages.append({"role": "user", "content": mandarin_text})
    return await _chat(messages)


# 模块导入时加载 .env
load_env()
