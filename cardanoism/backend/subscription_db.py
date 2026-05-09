"""subscription_db.py
サブスクリプション基盤の DB ヘルパー (Phase 0)。

このモジュールは tier 名 / 機能配分に依存しない汎用 CRUD を提供する。
tier ↔ 機能のマッピングは feature_gates.py で別管理する。

ベータ期間中の運用想定:
  - 新規ユーザー登録時に tier="standard" のサブスク行を auto-create
  - Stripe 連携前なので status は "active" 固定
  - tier を変更するときはこのモジュールの upsert / set_tier を使う
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


# ベータ期間中、新規ユーザーに自動付与する tier。本番開始時に "free" に変える。
DEFAULT_TIER_FOR_NEW_USER = "standard"
DEFAULT_TIER_NOTE = "beta_grandfather"


def get_user_subscription(user_id: int) -> dict[str, Any] | None:
    """ユーザーの現在のサブスク情報を返す。なければ None。"""
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT id, user_id, tier, status, billing_cycle, started_at, "
            "       current_period_end, canceled_at, stripe_customer_id, "
            "       stripe_subscription_id, stripe_price_id, note, "
            "       created_at, updated_at "
            "  FROM subscriptions WHERE user_id = ?",
            (int(user_id),),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_tier(user_id: int) -> str:
    """ユーザーの現在の tier を返す。サブスク行が無ければ "free"。

    feature_gates.can_use() の前段で必ず通るパスなので軽量に保つ。
    """
    sub = get_user_subscription(user_id)
    if not sub:
        return "free"
    # 期限切れキャンセルや past_due は実装後に "free" 扱いするロジックを追加
    if sub.get("status") in ("canceled", "expired"):
        return "free"
    return str(sub.get("tier") or "free")


def ensure_subscription(
    user_id: int,
    *,
    tier: str = DEFAULT_TIER_FOR_NEW_USER,
    status: str = "active",
    note: str | None = DEFAULT_TIER_NOTE,
) -> None:
    """サブスク行が無ければ作る (新規ユーザー登録時に呼ぶ想定)。

    既に行があれば何もしない。tier の昇格などは set_tier() で明示的に。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            "INSERT IGNORE INTO subscriptions (user_id, tier, status, note) "
            "VALUES (?, ?, ?, ?)",
            (int(user_id), tier, status, note),
        )
        conn.commit()


def set_tier(
    user_id: int,
    *,
    tier: str,
    status: str = "active",
    billing_cycle: str | None = None,
    current_period_end: datetime | None = None,
    note: str | None = None,
) -> None:
    """ユーザーの tier を変更 (UPSERT)。

    Stripe Webhook 側からの呼び出しを想定。Phase 0 では手動運用 / マイグレーション
    用のみ。引数に渡された値だけ更新し、それ以外は維持する。
    """
    with get_db() as (cursor, conn):
        # まず行を確実にする
        cursor.execute(
            "INSERT IGNORE INTO subscriptions (user_id, tier, status) "
            "VALUES (?, ?, ?)",
            (int(user_id), tier, status),
        )
        # 必要カラムを更新
        sets = ["tier = ?", "status = ?"]
        params: list[Any] = [tier, status]
        if billing_cycle is not None:
            sets.append("billing_cycle = ?")
            params.append(billing_cycle)
        if current_period_end is not None:
            sets.append("current_period_end = ?")
            params.append(current_period_end)
        if note is not None:
            sets.append("note = ?")
            params.append(note)
        params.append(int(user_id))
        cursor.execute(
            f"UPDATE subscriptions SET {', '.join(sets)} WHERE user_id = ?",
            tuple(params),
        )
        conn.commit()


def cancel_subscription(user_id: int, *, at: datetime | None = None) -> None:
    """サブスクをキャンセル状態にする (現期間終了まで使えるが更新しない)。"""
    when = at or datetime.utcnow()
    with get_db() as (cursor, conn):
        cursor.execute(
            "UPDATE subscriptions SET status = 'canceled', canceled_at = ? "
            "WHERE user_id = ?",
            (when, int(user_id)),
        )
        conn.commit()


def attach_stripe_customer(user_id: int, customer_id: str) -> None:
    """Stripe Customer ID を紐付ける (Checkout 開始時等)。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            "INSERT IGNORE INTO subscriptions (user_id, tier, status) "
            "VALUES (?, 'free', 'active')",
            (int(user_id),),
        )
        cursor.execute(
            "UPDATE subscriptions SET stripe_customer_id = ? WHERE user_id = ?",
            (customer_id, int(user_id)),
        )
        conn.commit()
