"""
auth_db.py
ユーザー・セッション・お気に入り・ステークアドレス・通知設定のCRUD
既存の db_connect.py の get_db() パターンに従う
"""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)

SESSION_EXPIRE_DAYS = 30
STAKE_ADDRESS_LIMIT = 3

# ユーザー単位の通知イベント（アドレスに紐づかない全体通知）
NOTIFICATION_EVENT_TYPES = [
    "epoch_start",
    "treasury_withdrawal_enacted",
]

# ステークアドレス共通（プール委任者として）
POOL_NOTIFICATION_EVENT_TYPES = [
    "pool_retire",
    "pool_fee_change",
    "pool_saturation",
    "pool_pledge_shortage",
    "pool_reward_received",
    "pool_epoch_performance",
    "pool_delegation_reminder",
]

# DRep委任者のみ
DELEGATOR_NOTIFICATION_EVENT_TYPES = [
    "drep_new_governance_action",
    "drep_vote",
    "drep_status_change",
    "drep_delegation_reminder",
]

# DRep本人のみ
DREP_ONLY_NOTIFICATION_EVENT_TYPES = [
    "drep_new_governance_action",
    "drep_unvoted_1week",
    "drep_unvoted_2weeks",
]

# ステークアドレス単位の全イベント（stake_notification_settingsに保存）
STAKE_NOTIFICATION_EVENT_TYPES = list(dict.fromkeys(
    POOL_NOTIFICATION_EVENT_TYPES
    + DELEGATOR_NOTIFICATION_EVENT_TYPES
    + DREP_ONLY_NOTIFICATION_EVENT_TYPES
))

_USER_SELECT = "SELECT id, username, email, avatar_url, notification_frequency, language FROM users"

# ============================================================
# ユーザー基本操作
# ============================================================

def get_user_by_id(user_id: int) -> Optional[dict]:
    with get_db() as (cursor, _):
        cursor.execute(f"{_USER_SELECT} WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_user_profile(
    user_id: int,
    username: str,
    email: Optional[str],
    avatar_url: Optional[str],
) -> None:
    with get_db() as (cursor, conn):
        cursor.execute(
            "UPDATE users SET username = ?, email = ?, avatar_url = ? WHERE id = ?",
            (username, email, avatar_url, user_id),
        )
        conn.commit()


def _create_user(cursor, conn, username: str, avatar_url: str, email: str) -> int:
    """users テーブルに新規ユーザーを作成して user_id を返す内部ヘルパー。"""
    cursor.execute(
        "INSERT INTO users (username, email, avatar_url) VALUES (?, ?, ?)",
        (username, email or None, avatar_url or None),
    )
    conn.commit()
    user_id = cursor.lastrowid
    for event_type in NOTIFICATION_EVENT_TYPES:
        cursor.execute(
            "INSERT IGNORE INTO notification_settings (user_id, event_type, enabled) VALUES (?, ?, 1)",
            (user_id, event_type),
        )
    conn.commit()
    return user_id


# ============================================================
# プロバイダ管理（認証）
# ============================================================

def get_or_create_user_by_provider(
    provider: str,
    provider_id: str,
    username: str,
    avatar_url: str = "",
    email: str = "",
) -> dict:
    """
    provider/provider_id でユーザーを取得または新規作成する。
    LINE ログイン時は LINE 通知チャンネルも自動作成する。
    Google ログイン時はメール通知チャンネルも自動作成する。
    """
    with get_db() as (cursor, conn):
        # 既存プロバイダ検索
        cursor.execute(
            f"""
            {_USER_SELECT}
            WHERE id = (
              SELECT user_id FROM user_providers
              WHERE provider = ? AND provider_id = ?
            )
            """,
            (provider, provider_id),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)

        # 新規ユーザー作成
        user_id = _create_user(cursor, conn, username, avatar_url, email)

        # プロバイダ紐付け
        cursor.execute(
            "INSERT IGNORE INTO user_providers (user_id, provider, provider_id) VALUES (?, ?, ?)",
            (user_id, provider, provider_id),
        )

        # 通知チャンネル自動作成
        if provider == "line":
            cursor.execute(
                "INSERT IGNORE INTO notification_channels (user_id, channel_type, channel_value) VALUES (?, 'line', ?)",
                (user_id, provider_id),
            )
        elif provider == "google" and email:
            cursor.execute(
                "INSERT IGNORE INTO notification_channels (user_id, channel_type, channel_value) VALUES (?, 'email', ?)",
                (user_id, email),
            )

        conn.commit()
        cursor.execute(f"{_USER_SELECT} WHERE id = ?", (user_id,))
        return dict(cursor.fetchone())


def get_user_providers(user_id: int) -> list[dict]:
    """ユーザーに紐付いたプロバイダ一覧を返す。"""
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT provider, provider_id FROM user_providers WHERE user_id = ?",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# セッション
# ============================================================

def create_session(user_id: int) -> str:
    """セッショントークンを生成してDBに保存し、トークンを返す。"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=SESSION_EXPIRE_DAYS)
    with get_db() as (cursor, conn):
        cursor.execute(
            "INSERT INTO user_sessions (user_id, session_token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires_at.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    return token


def get_user_by_session(session_token: str) -> Optional[dict]:
    """有効なセッショントークンからユーザー情報を返す。期限切れは削除する。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            f"""
            {_USER_SELECT}
            WHERE id = (
              SELECT user_id FROM user_sessions
              WHERE session_token = ? AND expires_at > NOW()
            )
            """,
            (session_token,),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)

        cursor.execute(
            "DELETE FROM user_sessions WHERE session_token = ?",
            (session_token,),
        )
        conn.commit()
        return None


def delete_session(session_token: str) -> None:
    with get_db() as (cursor, conn):
        cursor.execute(
            "DELETE FROM user_sessions WHERE session_token = ?",
            (session_token,),
        )
        conn.commit()


# ============================================================
# 通知チャンネル管理
# ============================================================

def get_notification_channels(user_id: int) -> list[dict]:
    """ユーザーの通知チャンネル一覧を返す。"""
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT channel_type, channel_value, enabled FROM notification_channels WHERE user_id = ?",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def upsert_notification_channel(
    user_id: int,
    channel_type: str,
    channel_value: str,
    enabled: bool = True,
) -> None:
    """通知チャンネルを追加または更新する。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO notification_channels (user_id, channel_type, channel_value, enabled)
            VALUES (?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE channel_value = ?, enabled = ?
            """,
            (user_id, channel_type, channel_value, int(enabled),
             channel_value, int(enabled)),
        )
        conn.commit()


def set_channel_enabled(user_id: int, channel_type: str, enabled: bool) -> None:
    """通知チャンネルの有効/無効を切り替える。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            "UPDATE notification_channels SET enabled = ? WHERE user_id = ? AND channel_type = ?",
            (int(enabled), user_id, channel_type),
        )
        conn.commit()


def remove_notification_channel(user_id: int, channel_type: str) -> None:
    """通知チャンネルを削除する（LINE連携解除など）。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            "DELETE FROM notification_channels WHERE user_id = ? AND channel_type = ?",
            (user_id, channel_type),
        )
        conn.commit()


# ============================================================
# ステークアドレス
# ============================================================

def get_stake_addresses(user_id: int) -> list:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT id, address, wallet_address, nickname, role, delegated_drep_id, delegated_drep_name, delegated_pool_id, delegated_pool_name, created_at FROM stake_addresses WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall() if row is not None]


def add_stake_address(user_id: int, address: str, nickname: str, wallet_address: str | None = None) -> str:
    """追加する。成功時は "ok"、エラー時はエラー種別文字列を返す。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM stake_addresses WHERE user_id = ?",
            (user_id,),
        )
        if cursor.fetchone()["cnt"] >= STAKE_ADDRESS_LIMIT:
            return "limit"

        cursor.execute(
            "SELECT 1 FROM stake_addresses WHERE user_id = ? AND address = ?",
            (user_id, address),
        )
        if cursor.fetchone():
            return "duplicate"

        cursor.execute(
            "INSERT INTO stake_addresses (user_id, address, wallet_address, nickname) VALUES (?, ?, ?, ?)",
            (user_id, address, wallet_address, nickname),
        )
        stake_address_id = cursor.lastrowid

        for event_type in STAKE_NOTIFICATION_EVENT_TYPES:
            cursor.execute(
                "INSERT IGNORE INTO stake_notification_settings (stake_address_id, event_type, enabled) VALUES (?, ?, 1)",
                (stake_address_id, event_type),
            )
        conn.commit()
        return "ok"


def update_stake_address_role(
    address_id: int,
    role: str,
    drep_id: str | None = None,
    drep_name: str | None = None,
    pool_id: str | None = None,
    pool_name: str | None = None,
) -> None:
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            UPDATE stake_addresses
            SET role = ?, role_checked_at = NOW(),
                delegated_drep_id = ?, delegated_drep_name = ?,
                delegated_pool_id = ?, delegated_pool_name = ?
            WHERE id = ?
            """,
            (role, drep_id, drep_name, pool_id, pool_name, address_id),
        )
        conn.commit()


def delete_stake_address(address_id: int, user_id: int) -> None:
    with get_db() as (cursor, conn):
        cursor.execute(
            "DELETE FROM stake_addresses WHERE id = ? AND user_id = ?",
            (address_id, user_id),
        )
        conn.commit()


# ============================================================
# お気に入り
# ============================================================

def get_favorite_ids(user_id: int, type: str = "catalyst") -> list:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT proposal_uuid FROM favorites WHERE user_id = ? AND type = ?",
            (user_id, type),
        )
        return [
            row["proposal_uuid"]
            for row in cursor.fetchall()
            if row is not None and row["proposal_uuid"]
        ]


def get_favorites(user_id: int, type: str = "catalyst") -> list:
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT f.id, f.proposal_uuid, f.created_at,
                   p.title, p.title_ja, p.funding_status, p.amount_requested, p.currency_symbol,
                   fn.label as fund_label
            FROM favorites f
            JOIN proposals_new p ON f.proposal_uuid = p.uuid COLLATE utf8mb4_unicode_ci
            LEFT JOIN funds_new fn ON p.fund_uuid = fn.id
            WHERE f.user_id = ? AND f.type = ?
            ORDER BY f.created_at DESC
            """,
            (user_id, type),
        )
        return [dict(row) for row in cursor.fetchall()]


def add_favorite(user_id: int, proposal_uuid: str, type: str = "catalyst") -> None:
    with get_db() as (cursor, conn):
        cursor.execute(
            "INSERT IGNORE INTO favorites (user_id, proposal_uuid, type) VALUES (?, ?, ?)",
            (user_id, proposal_uuid, type),
        )
        conn.commit()


def remove_favorite(user_id: int, proposal_uuid: str, type: str = "catalyst") -> None:
    with get_db() as (cursor, conn):
        cursor.execute(
            "DELETE FROM favorites WHERE user_id = ? AND proposal_uuid = ? AND type = ?",
            (user_id, proposal_uuid, type),
        )
        conn.commit()


def is_favorite(user_id: int, proposal_uuid: str, type: str = "catalyst") -> bool:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND proposal_uuid = ? AND type = ?",
            (user_id, proposal_uuid, type),
        )
        return cursor.fetchone() is not None


def get_ga_favorites(user_id: int) -> list:
    """ガバナンスお気に入り一覧を取得（governance_actions JOIN）。
    favorites.proposal_uuid には proposal_id を保存している。
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT f.id, f.proposal_uuid, f.created_at,
                   g.title, g.title_ja, g.proposal_type,
                   g.proposed_epoch,
                   g.ratified_epoch, g.enacted_epoch,
                   g.dropped_epoch, g.expired_epoch
            FROM favorites f
            JOIN governance_actions g ON f.proposal_uuid = g.proposal_id
            WHERE f.user_id = ? AND f.type = 'governance'
            ORDER BY f.created_at DESC
            """,
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# 通知設定（イベントON/OFF）
# ============================================================

def get_notification_settings(user_id: int) -> dict:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT event_type, enabled FROM notification_settings WHERE user_id = ?",
            (user_id,),
        )
        rows = cursor.fetchall()
        settings = {row["event_type"]: bool(row["enabled"]) for row in rows if row is not None}
        for event_type in NOTIFICATION_EVENT_TYPES:
            if event_type not in settings:
                settings[event_type] = True
        return settings


def get_stake_notification_settings(stake_address_id: int) -> dict:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT event_type, enabled FROM stake_notification_settings WHERE stake_address_id = ?",
            (stake_address_id,),
        )
        rows = cursor.fetchall()
        settings = {row["event_type"]: bool(row["enabled"]) for row in rows if row is not None}
        for event_type in STAKE_NOTIFICATION_EVENT_TYPES:
            if event_type not in settings:
                settings[event_type] = True
        return settings


def update_stake_notification_setting(stake_address_id: int, event_type: str, enabled: bool) -> None:
    if event_type not in STAKE_NOTIFICATION_EVENT_TYPES:
        logger.warning("Unknown stake event_type: %s", event_type)
        return
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO stake_notification_settings (stake_address_id, event_type, enabled)
            VALUES (?, ?, ?)
            ON DUPLICATE KEY UPDATE enabled = ?
            """,
            (stake_address_id, event_type, int(enabled), int(enabled)),
        )
        conn.commit()


def update_notification_setting(user_id: int, event_type: str, enabled: bool) -> None:
    if event_type not in NOTIFICATION_EVENT_TYPES:
        logger.warning("Unknown event_type: %s", event_type)
        return
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO notification_settings (user_id, event_type, enabled)
            VALUES (?, ?, ?)
            ON DUPLICATE KEY UPDATE enabled = ?
            """,
            (user_id, event_type, int(enabled), int(enabled)),
        )
        conn.commit()


def update_notification_frequency(user_id: int, frequency: str) -> None:
    if frequency not in ("instant", "daily"):
        return
    with get_db() as (cursor, conn):
        cursor.execute(
            "UPDATE users SET notification_frequency = ? WHERE id = ?",
            (frequency, user_id),
        )
        conn.commit()


def update_language(user_id: int, language: str) -> None:
    if language not in ("ja", "en"):
        return
    with get_db() as (cursor, conn):
        cursor.execute(
            "UPDATE users SET language = ? WHERE id = ?",
            (language, user_id),
        )
        conn.commit()


# ============================================================
# Telegram 連携トークン
# ============================================================

TELEGRAM_TOKEN_EXPIRE_MINUTES = 15


def create_telegram_token(user_id: int) -> str:
    """一時トークンを生成してDBに保存し返す。"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=TELEGRAM_TOKEN_EXPIRE_MINUTES)
    with get_db() as (cursor, conn):
        cursor.execute(
            "DELETE FROM telegram_connect_tokens WHERE user_id = ?",
            (user_id,),
        )
        cursor.execute(
            "INSERT INTO telegram_connect_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        conn.commit()
    return token


def consume_telegram_token(token: str) -> Optional[int]:
    """トークンを検証して user_id を返す。使用済みトークンは削除する。期限切れ・不正は None。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            "SELECT user_id, expires_at FROM telegram_connect_tokens WHERE token = ?",
            (token,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        if datetime.utcnow() > row["expires_at"]:
            cursor.execute("DELETE FROM telegram_connect_tokens WHERE token = ?", (token,))
            conn.commit()
            return None
        user_id = row["user_id"]
        cursor.execute("DELETE FROM telegram_connect_tokens WHERE token = ?", (token,))
        conn.commit()
        return user_id
