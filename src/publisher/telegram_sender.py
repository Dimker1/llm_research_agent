import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_daily_digest(
    markdown_content: str,
    max_message_length: int = 3800,
    send_interval: float = 1.0,
) -> bool:
    """
    将 Markdown 日报分片发送到 Telegram。
    环境变量：TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    返回是否全部发送成功。
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("[telegram] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skipping")
        return False

    url = TELEGRAM_API.format(token=token)
    chunks = _split_by_section(markdown_content, max_message_length)

    success = True
    for i, chunk in enumerate(chunks, 1):
        try:
            resp = httpx.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            logger.info(f"[telegram] sent chunk {i}/{len(chunks)}")
        except Exception as e:
            logger.error(f"[telegram] failed to send chunk {i}: {e}")
            success = False

        if i < len(chunks):
            time.sleep(send_interval)

    return success


def _split_by_section(text: str, max_len: int) -> list[str]:
    """
    按 '## ' 段落标题切分消息，保证每块不超过 max_len 字符。
    如果单个段落本身超长，则按行进一步拆分。
    """
    if len(text) <= max_len:
        return [text]

    sections = []
    current = []
    current_len = 0

    for line in text.split("\n"):
        line_len = len(line) + 1  # +1 for newline
        # 遇到二级标题且当前块已有内容时，考虑切分
        if line.startswith("## ") and current_len > 0:
            if current_len + line_len > max_len:
                sections.append("\n".join(current))
                current = []
                current_len = 0
        current.append(line)
        current_len += line_len

        # 当前块超长时强制切分
        if current_len >= max_len:
            sections.append("\n".join(current))
            current = []
            current_len = 0

    if current:
        sections.append("\n".join(current))

    return [s for s in sections if s.strip()]
