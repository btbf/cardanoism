"""stake_rewards_db.py
ステーキング報酬キャッシュ (`stake_rewards` テーブル) の CRUD。

notify_worker._check_pool_reward_received_batch から bulk_upsert され、
ダッシュボード (DashboardState) からは SELECT で参照される。
"""
from __future__ import annotations

import logging
from typing import Iterable

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


def bulk_upsert_stake_rewards(
    rewards: Iterable[tuple[str, int, int, str | None]],
) -> int:
    """報酬データを一括 upsert する。

    Args:
        rewards: (stake_address, epoch_no, amount_lovelace, pool_id_or_None) の iterable

    Returns:
        影響行数（INSERT + UPDATE 合算）
    """
    rows = [
        (addr, int(epoch), int(amount or 0), pool_id)
        for addr, epoch, amount, pool_id in rewards
        if addr and epoch is not None
    ]
    if not rows:
        return 0
    sql = (
        "INSERT INTO stake_rewards (stake_address, epoch_no, amount_lovelace, pool_id) "
        "VALUES (?, ?, ?, ?) "
        "ON DUPLICATE KEY UPDATE "
        "  amount_lovelace = VALUES(amount_lovelace), "
        "  pool_id         = COALESCE(VALUES(pool_id), pool_id)"
    )
    try:
        with get_db() as (cursor, conn):
            cursor.executemany(sql, rows)
            conn.commit()
            return cursor.rowcount or 0
    except Exception as e:  # noqa: BLE001
        logger.exception("bulk_upsert_stake_rewards failed: %s", e)
        return 0


def get_recent_rewards(stake_addresses: list[str], n_epochs: int = 5) -> list[dict]:
    """指定アドレスの直近 n エポック分の報酬を返す。

    戻り値は epoch_no DESC, stake_address ASC でソート済み。
    キャッシュが無いアドレスは含まれない。
    """
    if not stake_addresses:
        return []
    placeholders = ",".join(["?"] * len(stake_addresses))
    sql = (
        f"SELECT stake_address, epoch_no, amount_lovelace, pool_id "
        f"FROM stake_rewards "
        f"WHERE stake_address IN ({placeholders}) "
        f"ORDER BY epoch_no DESC, stake_address ASC "
        f"LIMIT {int(n_epochs) * len(stake_addresses)}"
    )
    try:
        with get_db() as (cursor, _):
            cursor.execute(sql, stake_addresses)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:  # noqa: BLE001
        logger.exception("get_recent_rewards failed: %s", e)
        return []


def get_total_rewards(stake_addresses: list[str]) -> dict[str, int]:
    """指定アドレスの累積報酬 (lovelace) を返す。

    戻り値: {stake_address: total_lovelace}
    キャッシュが無いアドレスは 0 として含まれる。
    """
    if not stake_addresses:
        return {}
    placeholders = ",".join(["?"] * len(stake_addresses))
    sql = (
        f"SELECT stake_address, SUM(amount_lovelace) AS total "
        f"FROM stake_rewards "
        f"WHERE stake_address IN ({placeholders}) "
        f"GROUP BY stake_address"
    )
    out: dict[str, int] = {addr: 0 for addr in stake_addresses}
    try:
        with get_db() as (cursor, _):
            cursor.execute(sql, stake_addresses)
            for row in cursor.fetchall():
                out[str(row["stake_address"])] = int(row["total"] or 0)
    except Exception as e:  # noqa: BLE001
        logger.exception("get_total_rewards failed: %s", e)
    return out


def has_rewards_for_addresses(stake_addresses: list[str]) -> set[str]:
    """指定アドレスのうち、1 件以上 報酬キャッシュがあるアドレス集合を返す。

    ダッシュボードで「キャッシュ未対応 (= 通知 OFF) のため非表示」を
    判定するために使う。
    """
    if not stake_addresses:
        return set()
    placeholders = ",".join(["?"] * len(stake_addresses))
    sql = (
        f"SELECT DISTINCT stake_address FROM stake_rewards "
        f"WHERE stake_address IN ({placeholders})"
    )
    try:
        with get_db() as (cursor, _):
            cursor.execute(sql, stake_addresses)
            return {str(row["stake_address"]) for row in cursor.fetchall()}
    except Exception as e:  # noqa: BLE001
        logger.exception("has_rewards_for_addresses failed: %s", e)
        return set()
