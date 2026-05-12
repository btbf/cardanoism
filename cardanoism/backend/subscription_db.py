"""subscription_db.py
サブスクリプション基盤の DB ヘルパー (Phase 0)。

このモジュールは tier 名 / 機能配分に依存しない汎用 CRUD を提供する。
tier ↔ 機能のマッピングは feature_gates.py で別管理する。

ベータ期間中の運用想定:
  - plan_config.BETA_MODE=True の間は、ログイン済みユーザーは subscriptions 行
    の有無に関係なく BETA_AUTO_TIER を返す（実質的に全員 Pro 体験）
  - ベータ終了 (BETA_MODE=False) と同時に DB の実 tier に切り替わる
  - フィードバック特典としての Standard 3 ヶ月は別途 set_tier() で付与する
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.plan_config import BETA_MODE

logger = logging.getLogger(__name__)


# ベータ期間中、ログイン済みユーザー全員に与える tier。
# BETA_MODE が True の間は get_user_tier がこの値を返す（DB は触らない）。
BETA_AUTO_TIER = "pro"

# 新規ユーザー登録時に subscriptions 行を作る場合のデフォルト tier。
# 現状 ensure_subscription は呼ばれていないが、将来 Stripe 連携時のフォールバック。
DEFAULT_TIER_FOR_NEW_USER = "free"
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

    BETA_MODE が True の間は、ログイン済み (user_id > 0) なら BETA_AUTO_TIER を返す。
    feature_gates.can_use() の前段で必ず通るパスなので軽量に保つ。
    """
    if BETA_MODE and user_id and int(user_id) > 0:
        return BETA_AUTO_TIER
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
