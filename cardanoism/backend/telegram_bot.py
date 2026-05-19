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
  4. 確認メッセージをユーザーに送信
"""
import os
import logging

from fastapi import APIRouter, Request, Response
from starlette.responses import JSONResponse
from cardanoism.backend.telegram_notify import send_telegram, set_webhook
from cardanoism.backend.auth_db import (
    consume_telegram_token,
    upsert_notification_channel,
)

logger = logging.getLogger(__name__)
router = APIRouter()

CARDANOISM_URL = os.getenv("CARDANOISM_URL", "https://cardanoism.com")


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

    if not text.startswith("/start"):
        return Response(status_code=200)

    parts = text.strip().split(maxsplit=1)
    token = parts[1] if len(parts) > 1 else ""

    if not token:
        logger.info("telegram /start with no token from chat_id=%s", chat_id)
        send_telegram(chat_id, "Cardanoism のマイページから連携を開始してください。\n\n<a href='" + CARDANOISM_URL + "/mypage?tab=notification'>マイページを開く</a>")
        return Response(status_code=200)

    logger.info(
        "telegram /start with token chat_id=%s token_prefix=%s len=%d",
        chat_id, token[:8], len(token),
    )
    user_id = consume_telegram_token(token)
    if user_id is None:
        logger.warning(
            "telegram token rejected (not found / expired): chat_id=%s token_prefix=%s",
            chat_id, token[:8],
        )
        send_telegram(chat_id, "⚠️ 連携リンクが無効または期限切れです。\nマイページから再度連携を開始してください。")
        return Response(status_code=200)
    logger.info("telegram token accepted: chat_id=%s user_id=%s", chat_id, user_id)

    try:
        upsert_notification_channel(user_id, "telegram", chat_id)
    except Exception as e:
        logger.error("telegram channel upsert failed: %s", e)
        send_telegram(chat_id, "⚠️ サーバーエラーが発生しました。しばらく後にお試しください。")
        return Response(status_code=200)

    send_telegram(
        chat_id,
        "✅ <b>Cardanoism との Telegram 連携が完了しました！</b>\n\n"
        "マイページで通知イベントを設定してください。\n"
        f"<a href='{CARDANOISM_URL}/mypage?tab=notification'>通知設定を開く</a>",
    )
    return Response(status_code=200)


@router.get("/telegram/setup")
async def telegram_setup(request: Request):
    """Webhook URL を Telegram に登録する（管理者用エンドポイント）。"""
    webhook_url = f"{CARDANOISM_URL}/telegram/webhook"
    ok = set_webhook(webhook_url)
    return JSONResponse({"ok": ok, "webhook_url": webhook_url})
