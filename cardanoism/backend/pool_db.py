"""
pool_db.py
pools テーブルの CRUD。同期は notify_worker.py --event pool_sync で行う。
ページ側はこのモジュール経由で DB を読むだけ。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


# ============================================================
# 書き込み
# ============================================================

def upsert_pool(data: dict[str, Any]) -> None:
    """pools 1 行を UPSERT。Koios /pool_list + /pool_info をマージした dict を想定。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO pools (
                pool_id_bech32, pool_id_hex,
                pool_status, active_epoch_no, retiring_epoch,
                op_cert, op_cert_counter, vrf_key_hash,
                pledge, margin, fixed_cost,
                active_stake, live_stake, live_pledge, live_delegators,
                live_saturation, sigma, block_count,
                reward_addr, owners, relays,
                meta_url, meta_hash, ticker, pool_name, description, homepage
            ) VALUES (
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            ON DUPLICATE KEY UPDATE
                pool_id_hex      = VALUES(pool_id_hex),
                pool_status      = VALUES(pool_status),
                active_epoch_no  = VALUES(active_epoch_no),
                retiring_epoch   = VALUES(retiring_epoch),
                op_cert          = VALUES(op_cert),
                op_cert_counter  = VALUES(op_cert_counter),
                vrf_key_hash     = VALUES(vrf_key_hash),
                pledge           = VALUES(pledge),
                margin           = VALUES(margin),
                fixed_cost       = VALUES(fixed_cost),
                active_stake     = VALUES(active_stake),
                live_stake       = VALUES(live_stake),
                live_pledge      = VALUES(live_pledge),
                live_delegators  = VALUES(live_delegators),
                live_saturation  = VALUES(live_saturation),
                sigma            = VALUES(sigma),
                block_count      = VALUES(block_count),
                reward_addr      = VALUES(reward_addr),
                owners           = VALUES(owners),
                relays           = VALUES(relays),
                meta_url         = VALUES(meta_url),
                meta_hash        = VALUES(meta_hash),
                ticker           = VALUES(ticker),
                pool_name        = VALUES(pool_name),
                description      = VALUES(description),
                homepage         = VALUES(homepage)
            """,
            (
                data.get("pool_id_bech32"),
                data.get("pool_id_hex"),
                data.get("pool_status"),
                _int_or_none(data.get("active_epoch_no")),
                _int_or_none(data.get("retiring_epoch")),
                data.get("op_cert"),
                _int_or_none(data.get("op_cert_counter")),
                data.get("vrf_key_hash"),
                _int_or_zero(data.get("pledge")),
                _decimal_or_none(data.get("margin")),
                _int_or_zero(data.get("fixed_cost")),
                _int_or_zero(data.get("active_stake")),
                _int_or_zero(data.get("live_stake")),
                _int_or_zero(data.get("live_pledge")),
                _int_or_zero(data.get("live_delegators")),
                _decimal_or_none(data.get("live_saturation")),
                _decimal_or_none(data.get("sigma")),
                _int_or_zero(data.get("block_count")),
                data.get("reward_addr"),
                _json_or_none(data.get("owners")),
                _json_or_none(data.get("relays")),
                data.get("meta_url"),
                data.get("meta_hash"),
                _truncate(data.get("ticker"), 64),
                _truncate(data.get("pool_name"), 255),
                data.get("description"),
                data.get("homepage"),
            ),
        )
        conn.commit()


def bulk_upsert_pools(records: list[dict]) -> int:
    count = 0
    for r in records:
        try:
            upsert_pool(r)
            count += 1
        except Exception as e:
            logger.exception("upsert_pool failed (pool=%s): %s", r.get("pool_id_bech32"), e)
    return count


def _int_or_none(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _int_or_zero(v):
    return _int_or_none(v) or 0


def _decimal_or_none(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _json_or_none(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


def _truncate(v, n: int):
    if v is None:
        return None
    s = str(v)
    return s[:n] if len(s) > n else s


# ============================================================
# 読み込み
# ============================================================

# 並び順は SPO リスト UI のセレクタと対応。
_SORT_CLAUSES = {
    "stake_desc":      "live_stake DESC, pool_id_bech32 ASC",
    "stake_asc":       "live_stake ASC, pool_id_bech32 ASC",
    "pledge_desc":     "live_pledge DESC, pool_id_bech32 ASC",
    "saturation_desc": "live_saturation DESC, pool_id_bech32 ASC",
    "saturation_asc":  "live_saturation ASC, pool_id_bech32 ASC",
    "fee_asc":         "margin ASC, fixed_cost ASC",
    "blocks_desc":     "block_count DESC, pool_id_bech32 ASC",
    "delegators_desc": "live_delegators DESC, pool_id_bech32 ASC",
    "ticker_asc":      "COALESCE(ticker, pool_id_bech32) ASC",
}


def get_pools(
    search: str = "",
    only_active: bool = True,
    sort: str = "stake_desc",
    limit: int = 30,
    offset: int = 0,
) -> list[dict]:
    """SPO 一覧。search は ticker / pool_name / pool_id_bech32 の部分一致。"""
    where = ["1=1"]
    params: list = []
    if only_active:
        # registered と retiring (これから退役) は表示する。retired は除外。
        where.append("(pool_status IS NULL OR pool_status <> 'retired')")
    if search:
        where.append("(ticker LIKE ? OR pool_name LIKE ? OR pool_id_bech32 LIKE ?)")
        sv = f"%{search}%"
        params.extend([sv, sv, sv])
    order = _SORT_CLAUSES.get(sort, _SORT_CLAUSES["stake_desc"])
    sql = (
        "SELECT pool_id_bech32, pool_id_hex, pool_status, active_epoch_no, retiring_epoch, "
        "pledge, margin, fixed_cost, "
        "active_stake, live_stake, live_pledge, live_delegators, live_saturation, sigma, block_count, "
        "ticker, pool_name, description, homepage, meta_url, updated_at "
        "FROM pools "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {order} "
        f"LIMIT {int(limit)} OFFSET {int(offset)}"
    )
    with get_db() as (cursor, _):
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]


def count_pools(search: str = "", only_active: bool = True) -> int:
    where = ["1=1"]
    params: list = []
    if only_active:
        where.append("(pool_status IS NULL OR pool_status <> 'retired')")
    if search:
        where.append("(ticker LIKE ? OR pool_name LIKE ? OR pool_id_bech32 LIKE ?)")
        sv = f"%{search}%"
        params.extend([sv, sv, sv])
    sql = f"SELECT COUNT(*) AS cnt FROM pools WHERE {' AND '.join(where)}"
    with get_db() as (cursor, _):
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return int((row or {}).get("cnt", 0))


def get_pool(pool_id_bech32: str) -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute("SELECT * FROM pools WHERE pool_id_bech32 = ?", (pool_id_bech32,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_top_pools(limit: int = 20) -> list[dict]:
    """live_stake 上位プール（ダッシュボードの飽和率バー用）。"""
    return get_pools(only_active=True, sort="stake_desc", limit=limit, offset=0)


def get_network_summary() -> dict:
    """ダッシュボード用のネットワーク集計。

    返却:
      {
        "total_pools":      登録プール総数,
        "active_pools":     現在アクティブ (status != retired),
        "retiring_pools":   退役予告中 (status = retiring),
        "retired_pools":    退役済み,
        "total_live_stake": 全プール live_stake 合計 (lovelace),
        "total_active_stake": 全プール active_stake 合計 (lovelace),
        "total_delegators": 全プール委任者数の合計,
        "saturated_pools":  live_saturation > 0.8 のプール数,
      }
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_pools,
                SUM(CASE WHEN pool_status IS NULL OR pool_status <> 'retired' THEN 1 ELSE 0 END) AS active_pools,
                SUM(CASE WHEN pool_status = 'retiring' THEN 1 ELSE 0 END) AS retiring_pools,
                SUM(CASE WHEN pool_status = 'retired'  THEN 1 ELSE 0 END) AS retired_pools,
                COALESCE(SUM(CASE WHEN pool_status IS NULL OR pool_status <> 'retired' THEN live_stake   ELSE 0 END), 0) AS total_live_stake,
                COALESCE(SUM(CASE WHEN pool_status IS NULL OR pool_status <> 'retired' THEN active_stake ELSE 0 END), 0) AS total_active_stake,
                COALESCE(SUM(CASE WHEN pool_status IS NULL OR pool_status <> 'retired' THEN live_delegators ELSE 0 END), 0) AS total_delegators,
                SUM(CASE WHEN live_saturation IS NOT NULL AND live_saturation > 0.8 THEN 1 ELSE 0 END) AS saturated_pools
            FROM pools
            """
        )
        row = cursor.fetchone() or {}
        return {k: int(v or 0) for k, v in dict(row).items()}
