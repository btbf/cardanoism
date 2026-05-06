"""統合通知ディスパッチャ。

addr (channel ID 含むユーザー / stake_address dict) と event_type, ctx, template を
受け取り、設定された全チャンネル (LINE / メール / Telegram) に同じ ctx で送信する。

各チャンネルの送信は dedup_key + already_sent ガードで重複防止する。

Why: 既存の各 event handler に LINE / email / Telegram ブロックが inline で散在
しており、ワーディング変更が 3 箇所に必要だった。これを「ctx (データ) → 3 つの
render_*() (表現) → channel 単位送信」の構造に集約する。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# event_type → template module のレジストリ。各テンプレートモジュールが
# 自身を register() で登録する想定だが、明示的な lazy import でも可。
EVENT_TEMPLATES: dict[str, Any] = {}


def register(event_type: str, template_module: Any) -> None:
    """event_type と template モジュールを紐付ける。"""
    EVENT_TEMPLATES[event_type] = template_module


def get_template(event_type: str) -> Any | None:
    return EVENT_TEMPLATES.get(event_type)


def merge_user_channels(
    line_users: list[dict],
    email_users: list[dict],
    telegram_users: list[dict] | None = None,
) -> list[dict]:
    """ユーザー単位の 3 種チャンネル一覧を merge して 1 ユーザー = 1 dict にまとめる。

    deliver() に渡せる形式に揃える。各 dict は以下を持つ:
      user_id / language / line_notify_id / email_addr / telegram_chat_id (NULL 可)
    """
    merged: dict[int, dict] = {}
    for u in line_users or []:
        uid = u.get("id")
        if uid is None:
            continue
        merged.setdefault(uid, {
            "user_id":  uid,
            "language": u.get("language", "ja"),
            "line_notify_id":   None,
            "email_addr":       None,
            "telegram_chat_id": None,
        })
        merged[uid]["line_notify_id"] = u.get("line_notify_id")
    for u in email_users or []:
        uid = u.get("id")
        if uid is None:
            continue
        merged.setdefault(uid, {
            "user_id":  uid,
            "language": u.get("language", "ja"),
            "line_notify_id":   None,
            "email_addr":       None,
            "telegram_chat_id": None,
        })
        merged[uid]["email_addr"] = u.get("email_addr")
    for u in telegram_users or []:
        uid = u.get("id")
        if uid is None:
            continue
        merged.setdefault(uid, {
            "user_id":  uid,
            "language": u.get("language", "ja"),
            "line_notify_id":   None,
            "email_addr":       None,
            "telegram_chat_id": None,
        })
        merged[uid]["telegram_chat_id"] = u.get("telegram_chat_id")
    return list(merged.values())


def deliver(
    addr: dict,
    event_type: str,
    ctx: dict,
    dedup_base: str,
    template: Any | None = None,
) -> None:
    """指定 addr の有効チャンネル全てに通知を送信する。

    Args:
        addr: line_notify_id / email_addr / telegram_chat_id / user_id / language
              を含む dict。`_merge_stake_channels` の戻り値想定。
        event_type: stake_notification_settings.event_type と一致する文字列
        ctx: テンプレートが render_* で使う共通データ
        dedup_base: 各チャネル dedup_key の prefix。実際は
                    "_line" / "_email" / "_telegram" を suffix する
        template: 明示的に渡せる template モジュール。None なら EVENT_TEMPLATES から解決
    """
    # lazy import: notify_worker が定義する低レベル送信ヘルパに依存するため、
    # モジュール初期化時の循環 import を避ける。
    from notify_worker import (
        already_sent, flex_and_log, email_and_log, telegram_and_log,
    )
    from cardanoism.backend.mail_notify import build_html, build_text

    if template is None:
        template = get_template(event_type)
    if template is None:
        logger.warning("deliver: template 未登録 event_type=%s", event_type)
        return

    user_id = addr.get("user_id")
    if user_id is None:
        return
    lang = addr.get("language", "ja")

    # ── LINE Flex ──────────────────────────────────────────────
    line_id = addr.get("line_notify_id")
    if line_id:
        dk = dedup_base + "_line"
        if not already_sent(user_id, event_type, dk):
            try:
                alt = template.alt_text(ctx, lang)
                contents = template.render_flex(ctx, lang)
                flex_and_log(line_id, user_id, event_type, dk, alt, contents)
            except Exception as e:  # noqa: BLE001
                logger.exception("deliver(LINE) %s 失敗: %s", event_type, e)

    # ── メール ──────────────────────────────────────────────────
    email_addr = addr.get("email_addr")
    if email_addr:
        dk = dedup_base + "_email"
        if not already_sent(user_id, event_type, dk):
            try:
                subject, lines, cta_url, cta_label = template.render_email(ctx, lang)
                email_and_log(
                    email_addr, user_id, event_type, dk, subject,
                    build_html(subject, lines, cta_url, cta_label, lang),
                    build_text(subject, lines, cta_url, lang),
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("deliver(email) %s 失敗: %s", event_type, e)

    # ── Telegram ───────────────────────────────────────────────
    chat_id = addr.get("telegram_chat_id")
    if chat_id:
        dk = dedup_base + "_telegram"
        if not already_sent(user_id, event_type, dk):
            try:
                tg_text = template.render_telegram(ctx, lang)
                telegram_and_log(chat_id, user_id, event_type, dk, tg_text)
            except Exception as e:  # noqa: BLE001
                logger.exception("deliver(telegram) %s 失敗: %s", event_type, e)
