"""
telegram_bot.py
Telegram Bot Webhook ハンドラー（FastAPI APIRouter）

エンドポイント:
  POST /telegram/webhook  - Telegram からのアップデートを受信
  GET  /telegram/setup    - Webhook URL を登録（管理者用）

フロー:
  1. ユーザーが /start TOKEN を Bot に送信
  2. Webhook が TOKEN を検証 → user_id を取得
  3. chat_id を notification_channels に保存
  4. 確認メッセージをユーザーに送信 (users.language があれば優先、なければ
     Telegram の from.language_code から判定)
"""
import os
import logging

from fastapi import APIRouter, Request, Response
from starlette.responses import JSONResponse
from cardanoism.backend.telegram_notify import send_telegram, set_webhook
from cardanoism.backend.auth_db import (
    consume_telegram_token,
    upsert_notification_channel,
    get_user_by_id,
)

logger = logging.getLogger(__name__)
router = APIRouter()

CARDANOISM_URL = os.getenv("CARDANOISM_URL", "https://cardanoism.com")


def _detect_lang(message: dict) -> str:
    """Telegram クライアントの language_code から JA / EN を判定。
    ja で始まる場合のみ JA、それ以外は EN にフォールバック。
    """
    code = (message.get("from", {}).get("language_code") or "").lower()
    return "ja" if code.startswith("ja") else "en"


# ── メッセージ定数 (JA / EN) ──

_MSG_NO_TOKEN = {
    "ja": (
        "Cardanoism のマイページから連携を開始してください。\n\n"
        "<a href='{url}/mypage?tab=notification'>マイページを開く</a>"
    ),
    "en": (
        "Please start the connection from your Cardanoism My Page.\n\n"
        "<a href='{url}/mypage?tab=notification'>Open My Page</a>"
    ),
}

_MSG_TOKEN_INVALID = {
    "ja": (
        "⚠️ 連携リンクが無効または期限切れです。\n"
        "マイページから再度連携を開始してください。"
    ),
    "en": (
        "⚠️ The connection link is invalid or has expired.\n"
        "Please start the connection again from your My Page."
    ),
}

_MSG_SERVER_ERROR = {
    "ja": "⚠️ サーバーエラーが発生しました。しばらく後にお試しください。",
    "en": "⚠️ A server error occurred. Please try again later.",
}

_MSG_SUCCESS = {
    "ja": (
        "✅ <b>Cardanoism との Telegram 連携が完了しました!</b>\n\n"
        "マイページで通知イベントを設定してください。\n"
        "<a href='{url}/mypage?tab=notification'>通知設定を開く</a>"
    ),
    "en": (
        "✅ <b>Telegram is now connected to Cardanoism!</b>\n\n"
        "Configure which events to receive from your My Page.\n"
        "<a href='{url}/mypage?tab=notification'>Open notification settings</a>"
    ),
}


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Telegram からのアップデートを処理する。"""
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)

    message = data.get("message") or data.get("edited_message")
    if not message:
        return Response(status_code=200)

    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "")
    tg_lang = _detect_lang(message)

    if not text.startswith("/start"):
        return Response(status_code=200)

    parts = text.strip().split(maxsplit=1)
    token = parts[1] if len(parts) > 1 else ""

    if not token:
        logger.info("telegram /start with no token from chat_id=%s lang=%s", chat_id, tg_lang)
        send_telegram(chat_id, _MSG_NO_TOKEN[tg_lang].format(url=CARDANOISM_URL))
        return Response(status_code=200)

    logger.info(
        "telegram /start with token chat_id=%s token_prefix=%s len=%d lang=%s",
        chat_id, token[:8], len(token), tg_lang,
    )
    user_id = consume_telegram_token(token)
    if user_id is None:
        logger.warning(
            "telegram token rejected (not found / expired): chat_id=%s token_prefix=%s",
            chat_id, token[:8],
        )
        send_telegram(chat_id, _MSG_TOKEN_INVALID[tg_lang])
        return Response(status_code=200)
    logger.info("telegram token accepted: chat_id=%s user_id=%s", chat_id, user_id)

    try:
        upsert_notification_channel(user_id, "telegram", chat_id)
    except Exception as e:
        logger.error("telegram channel upsert failed: %s", e)
        send_telegram(chat_id, _MSG_SERVER_ERROR[tg_lang])
        return Response(status_code=200)

    # 連携成功後の言語: ユーザーがサイト側で選んだ users.language を優先。
    # 取得失敗時は Telegram の language_code にフォールバック。
    success_lang = tg_lang
    try:
        user = get_user_by_id(user_id)
        if user and user.get("language") in ("ja", "en"):
            success_lang = user["language"]
    except Exception as e:
        logger.debug("get_user_by_id failed (fallback to tg_lang): %s", e)

    send_telegram(chat_id, _MSG_SUCCESS[success_lang].format(url=CARDANOISM_URL))
    return Response(status_code=200)


@router.get("/telegram/setup")
async def telegram_setup(request: Request):
    """Webhook URL を Telegram に登録する（管理者用エンドポイント）。"""
    webhook_url = f"{CARDANOISM_URL}/telegram/webhook"
    ok = set_webhook(webhook_url)
    return JSONResponse({"ok": ok, "webhook_url": webhook_url})
