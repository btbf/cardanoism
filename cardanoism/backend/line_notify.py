"""
line_notify.py
LINE Messaging API プッシュ送信ヘルパー

事前準備:
  - LINE Developers で Messaging API チャンネルを作成
  - LINE Login チャンネルと同一プロバイダー配下に置く（userId が共通になる）
  - 環境変数 LINE_MESSAGING_TOKEN にチャンネルアクセストークン（長期）を設定
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_MESSAGING_TOKEN = os.getenv("LINE_MESSAGING_TOKEN", "")


def send_line_flex(line_id: str, alt_text: str, contents: dict) -> bool:
    """
    LINE Flex Message を送信する。
    alt_text: 通知バナーに表示されるテキスト（Flex非対応環境でも表示）
    contents: Flex Message の contents オブジェクト（bubble / carousel）
    """
    if not LINE_MESSAGING_TOKEN:
        logger.warning("LINE_MESSAGING_TOKEN が設定されていません")
        return False
    if not line_id:
        logger.warning("line_id が空のためスキップ")
        return False
    try:
        resp = requests.post(
            PUSH_URL,
            headers={
                "Authorization": f"Bearer {LINE_MESSAGING_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "to": line_id,
                "messages": [
                    {
                        "type": "flex",
                        "altText": alt_text,
                        "contents": contents,
                    }
                ],
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        logger.warning("LINE flex 失敗 %s %s (line_id=%s)", resp.status_code, resp.text[:200], line_id[:8])
        return False
    except Exception as e:
        logger.error("LINE flex 例外: %s", e)
        return False


def send_line_push(line_id: str, message: str) -> bool:
    """
    LINE プッシュメッセージを送信する。

    ユーザーが公式アカウントを友だち追加していない場合は 400 エラーになる。
    成功時 True、失敗時 False を返す。
    """
    if not LINE_MESSAGING_TOKEN:
        logger.warning("LINE_MESSAGING_TOKEN が設定されていません")
        return False
    if not line_id:
        logger.warning("line_id が空のためスキップ")
        return False
    try:
        resp = requests.post(
            PUSH_URL,
            headers={
                "Authorization": f"Bearer {LINE_MESSAGING_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "to": line_id,
                "messages": [{"type": "text", "text": message}],
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        # 400: 友だち未追加 / トークン無効など
        logger.warning("LINE push 失敗 %s %s (line_id=%s)", resp.status_code, resp.text[:200], line_id[:8])
        return False
    except Exception as e:
        logger.error("LINE push 例外: %s", e)
        return False
