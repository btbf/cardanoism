"""
telegram_notify.py
Telegram Bot API 送信ヘルパー

環境変数:
  TELEGRAM_BOT_TOKEN - BotFather で取得したトークン
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_telegram(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    """Telegram にテキストメッセージを送信する。"""
    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN が設定されていません")
        return False
    if not chat_id:
        return False
    try:
        resp = requests.post(
            f"{_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        logger.warning("Telegram 送信失敗 %s %s (chat_id=%s)", resp.status_code, resp.text[:200], chat_id)
        return False
    except Exception as e:
        logger.error("Telegram 送信例外: %s", e)
        return False


def set_webhook(webhook_url: str) -> bool:
    """Bot の Webhook URL を登録する。デプロイ時に一度実行する。"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN が未設定です")
        return False
    resp = requests.post(
        f"{_BASE}/setWebhook",
        json={"url": webhook_url},
        timeout=10,
    )
    ok = resp.status_code == 200 and resp.json().get("ok")
    if ok:
        logger.info("Telegram Webhook 登録成功: %s", webhook_url)
    else:
        logger.error("Telegram Webhook 登録失敗: %s", resp.text)
    return ok
