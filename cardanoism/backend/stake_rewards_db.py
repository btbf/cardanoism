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


_VALID_REWARD_TYPES = ("member", "leader", "other")


def _normalize_reward_type(t: str | None) -> str:
    """Koios の type を 'member' / 'leader' / 'other' の 3 値に正規化。"""
    if t in ("member", "leader"):
        return t
    return "other"


def bulk_upsert_stake_rewards(
    rewards: Iterable[tuple[str, int, int, str | None, str | None]],
) -> int:
    """報酬データを一括 upsert する。

    Args:
        rewards: (stake_address, epoch_no, amount_lovelace, pool_id_or_None, reward_type) の iterable
                 reward_type は 'member' / 'leader' / 'other' のいずれか。
                 None または未対応値は 'other' に正規化される。

    Returns:
        影響行数（INSERT + UPDATE 合算）
    """
    rows = [
        (addr, int(epoch), int(amount or 0), pool_id, _normalize_reward_type(rt))
        for addr, epoch, amount, pool_id, rt in rewards
        if addr and epoch is not None
    ]
    if not rows:
        return 0
    sql = (
        "INSERT INTO stake_rewards (stake_address, epoch_no, amount_lovelace, pool_id, reward_type) "
        "VALUES (?, ?, ?, ?, ?) "
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

    戻り値: 1 行 = 1 (stake, epoch, type)。同じ epoch でも member / leader が別行で返る。
    epoch_no DESC, stake_address ASC, reward_type ASC でソート済み。

    注: stake_rewards テーブルには「報酬を受け取った epoch」しか行が無いため、
    報酬が飛び飛びのアドレスでは古い epoch が混ざる。
    「直近 N エポックの連続値 (0 補完)」が必要なら get_rewards_for_epochs を使う。
    """
    if not stake_addresses:
        return []
    placeholders = ",".join(["?"] * len(stake_addresses))
    sql = (
        f"SELECT stake_address, epoch_no, amount_lovelace, pool_id, reward_type "
        f"FROM stake_rewards "
        f"WHERE stake_address IN ({placeholders}) "
        f"ORDER BY epoch_no DESC, stake_address ASC, reward_type ASC "
        f"LIMIT {int(n_epochs) * len(stake_addresses) * 3}"
    )
    try:
        with get_db() as (cursor, _):
            cursor.execute(sql, stake_addresses)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:  # noqa: BLE001
        logger.exception("get_recent_rewards failed: %s", e)
        return []


def get_rewards_for_epochs(stake_addresses: list[str], epochs: list[int]) -> list[dict]:
    """指定アドレス × 指定 epoch のみの報酬行を返す。

    戻り値: 1 行 = 1 (stake, epoch, type)。stake_rewards に行が存在する分だけ返る。
    呼び出し側で 0 補完して連続エポック表示に整える。
    """
    if not stake_addresses or not epochs:
        return []
    addr_ph = ",".join(["?"] * len(stake_addresses))
    ep_ph   = ",".join(["?"] * len(epochs))
    sql = (
        f"SELECT stake_address, epoch_no, amount_lovelace, pool_id, reward_type "
        f"FROM stake_rewards "
        f"WHERE stake_address IN ({addr_ph}) AND epoch_no IN ({ep_ph})"
    )
    params = list(stake_addresses) + [int(e) for e in epochs]
    try:
        with get_db() as (cursor, _):
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:  # noqa: BLE001
        logger.exception("get_rewards_for_epochs failed: %s", e)
        return []


def get_total_rewards(stake_addresses: list[str]) -> dict[str, int]:
    """指定アドレスの累積報酬 (lovelace) を返す (type 区別せず合算)。

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


def get_total_rewards_by_type(stake_addresses: list[str]) -> dict[str, dict[str, int]]:
    """指定アドレスの累積報酬を type 別に返す。

    戻り値: {stake_address: {"member": N, "leader": N, "other": N}}
    """
    if not stake_addresses:
        return {}
    placeholders = ",".join(["?"] * len(stake_addresses))
    sql = (
        f"SELECT stake_address, reward_type, SUM(amount_lovelace) AS total "
        f"FROM stake_rewards "
        f"WHERE stake_address IN ({placeholders}) "
        f"GROUP BY stake_address, reward_type"
    )
    out: dict[str, dict[str, int]] = {
        addr: {"member": 0, "leader": 0, "other": 0} for addr in stake_addresses
    }
    try:
        with get_db() as (cursor, _):
            cursor.execute(sql, stake_addresses)
            for row in cursor.fetchall():
                addr = str(row["stake_address"])
                rtype = str(row["reward_type"] or "other")
                if rtype not in _VALID_REWARD_TYPES:
                    rtype = "other"
                out.setdefault(addr, {"member": 0, "leader": 0, "other": 0})[rtype] = int(row["total"] or 0)
    except Exception as e:  # noqa: BLE001
        logger.exception("get_total_rewards_by_type failed: %s", e)
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
