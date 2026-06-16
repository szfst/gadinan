import os

import httpx

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def is_configured() -> bool:
    return bool(DEEPSEEK_API_KEY)


async def _chat(messages: list[dict]) -> str:
    if not DEEPSEEK_API_KEY:
        raise ValueError("未配置 DEEPSEEK_API_KEY，请在 .env 文件中设置")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
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
                "你是翻译助手。用户输入的是闽南语语音转写文本，"
                "请将其准确翻译为标准普通话。只输出普通话翻译，不要解释。"
            ),
        },
        {"role": "user", "content": dialect_text},
    ]
    return await _chat(messages)


async def ask_question(mandarin_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "你是一个有帮助的 AI 助手。请用简洁清晰的中文回答用户的问题。",
        },
        {"role": "user", "content": mandarin_text},
    ]
    return await _chat(messages)
