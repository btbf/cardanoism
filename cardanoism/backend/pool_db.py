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
                meta_url, meta_hash, ticker, pool_name, description, homepage,
                pool_icon_url, pool_logo_url, extended_about,
                twitter_handle, telegram_handle, youtube_handle, github_handle
            ) VALUES (
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?
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
                homepage         = VALUES(homepage),
                pool_icon_url    = COALESCE(VALUES(pool_icon_url),    pool_icon_url),
                pool_logo_url    = COALESCE(VALUES(pool_logo_url),    pool_logo_url),
                extended_about   = COALESCE(VALUES(extended_about),   extended_about),
                twitter_handle   = COALESCE(VALUES(twitter_handle),   twitter_handle),
                telegram_handle  = COALESCE(VALUES(telegram_handle),  telegram_handle),
                youtube_handle   = COALESCE(VALUES(youtube_handle),   youtube_handle),
                github_handle    = COALESCE(VALUES(github_handle),    github_handle)
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
                _truncate(data.get("meta_hash"), 128),
                _truncate(data.get("ticker"), 64),
                _truncate(data.get("pool_name"), 255),
                data.get("description"),
                data.get("homepage"),
                data.get("pool_icon_url"),
                data.get("pool_logo_url"),
                data.get("extended_about"),
                _truncate(data.get("twitter_handle"), 128),
                _truncate(data.get("telegram_handle"), 128),
                _truncate(data.get("youtube_handle"), 255),
                _truncate(data.get("github_handle"), 128),
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
    random_seed: int | None = None,
) -> list[dict]:
    """SPO 一覧。search は ticker / pool_name / pool_id_bech32 の部分一致。

    sort="random" のときは random_seed を MariaDB の RAND(seed) に渡す。
    呼び出し側でセッション内固定の seed を渡すことでページングが安定する。
    """
    where = ["1=1"]
    params: list = []
    if only_active:
        # registered と retiring (これから退役) は表示する。retired は除外。
        where.append("(pool_status IS NULL OR pool_status <> 'retired')")
    if search:
        # 入力値が pool1 で始まるときだけ pool_id_bech32 を検索対象にする。
        # それ以外は ticker / pool_name のみ (Pool ID 文字列のノイズマッチを避ける)。
        if search.lower().startswith("pool1"):
            where.append("pool_id_bech32 LIKE ?")
            params.append(f"%{search}%")
        else:
            where.append("(ticker LIKE ? OR pool_name LIKE ?)")
            sv = f"%{search}%"
            params.extend([sv, sv])

    if sort == "random":
        # int キャストで SQL インジェクションを防ぐ（識別子位置のため ? バインドが効かない）
        seed = int(random_seed) if random_seed is not None else 0
        base_order = f"RAND({seed}), pool_id_bech32"
    else:
        base_order = _SORT_CLAUSES.get(sort, _SORT_CLAUSES["stake_desc"])
    # リレー応答なし (relay_alive = 0) のプールを最下位へ。未確認 (NULL) は alive 扱いにして上位に残す。
    order = f"COALESCE(relay_alive, 1) DESC, {base_order}"

    sql = (
        "SELECT pool_id_bech32, pool_id_hex, pool_status, active_epoch_no, retiring_epoch, "
        "pledge, margin, fixed_cost, "
        "active_stake, live_stake, live_pledge, live_delegators, live_saturation, sigma, block_count, "
        "ticker, pool_name, description, homepage, pool_icon_url, pool_logo_url, "
        "extended_about, twitter_handle, telegram_handle, youtube_handle, github_handle, "
        "relay_alive, relay_checked_at, block_history_5ep, apy_history_7ep, "
        "meta_url, updated_at "
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
        # pools_list と同じ条件分岐 (pool1 始まりのみ pool_id_bech32 を対象に)
        if search.lower().startswith("pool1"):
            where.append("pool_id_bech32 LIKE ?")
            params.append(f"%{search}%")
        else:
            where.append("(ticker LIKE ? OR pool_name LIKE ?)")
            sv = f"%{search}%"
            params.extend([sv, sv])
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
    return get_pools(only_active=True, sort="stake_desc", limit=limit, offset=0, random_seed=None)


def get_pools_with_relays(only_active: bool = True) -> list[dict]:
    """リレー疎通確認用に pool_id_bech32 と relays JSON だけ返す。"""
    where = "(pool_status IS NULL OR pool_status <> 'retired')" if only_active else "1=1"
    with get_db() as (cursor, _):
        cursor.execute(f"SELECT pool_id_bech32, relays FROM pools WHERE {where}")
        return [dict(r) for r in cursor.fetchall()]


def bulk_update_relay_alive(updates: list[tuple]) -> int:
    """[(pool_id_bech32, alive_bool), ...] を一括で UPDATE。relay_checked_at も同時更新。"""
    if not updates:
        return 0
    with get_db() as (cursor, conn):
        for pid, alive in updates:
            cursor.execute(
                "UPDATE pools SET relay_alive = ?, relay_checked_at = NOW() WHERE pool_id_bech32 = ?",
                (1 if alive else 0, pid),
            )
        conn.commit()
    return len(updates)


def bulk_update_block_history(updates: list[tuple]) -> int:
    """[(pool_id_bech32, block_json, apy_json), ...] を一括 UPDATE。

    block_json は "[12,8,15,11,9]" 形式。
    apy_json は "[3.42,3.21,3.55,3.33,3.61,3.40,3.74]" 形式 (epoch_ros が確定している
    値のみ、newest 順)。値が 1 つも無いプールは "[]" or None で渡す。
    """
    if not updates:
        return 0
    with get_db() as (cursor, conn):
        for row in updates:
            pid, block_json, apy_json = row
            cursor.execute(
                """
                UPDATE pools
                   SET block_history_5ep = ?,
                       apy_history_7ep   = ?
                 WHERE pool_id_bech32    = ?
                """,
                (block_json, apy_json, pid),
            )
        conn.commit()
    return len(updates)


def get_pool_ids_for_block_history(only_active: bool = True) -> list[str]:
    """ブロック履歴フェッチ対象の pool_id_bech32 一覧。"""
    where = "(pool_status IS NULL OR pool_status <> 'retired')" if only_active else "1=1"
    with get_db() as (cursor, _):
        cursor.execute(f"SELECT pool_id_bech32 FROM pools WHERE {where} ORDER BY live_stake DESC")
        return [r["pool_id_bech32"] for r in cursor.fetchall() if r.get("pool_id_bech32")]


def get_pools_for_heatmap() -> list[dict]:
    """ヒートマップ用: アクティブプール全件の pool_id / ticker / block_history_5ep を返す。
    block_history_5ep は JSON 文字列。呼び出し側で sum を取って合計を出す。
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT pool_id_bech32, ticker, block_history_5ep
            FROM pools
            WHERE pool_status IS NULL OR pool_status <> 'retired'
            """
        )
        return [dict(r) for r in cursor.fetchall()]


def get_network_summary(saturated_threshold_lovelace: int | None = None) -> dict:
    """ダッシュボード用のネットワーク集計。

    saturated_threshold_lovelace: 「飽和判定」とみなす live_stake の閾値 (lovelace)。
      None の場合は飽和プール数 = 0 を返す（呼び出し側でソフトキャップ取得に失敗した時用のフォールバック）。
      通常はソフトキャップ÷500の 80% を渡す（= 1プール飽和点の 80% を超えたものを「警戒以上」とする）。

    返却:
      {
        "total_pools":      登録プール総数,
        "active_pools":     現在アクティブ (status != retired),
        "retiring_pools":   退役予告中 (status = retiring),
        "retired_pools":    退役済み,
        "total_live_stake": 全プール live_stake 合計 (lovelace),
        "total_active_stake": 全プール active_stake 合計 (lovelace),
        "total_delegators": 全プール委任者数の合計,
        "saturated_pools":  saturated_threshold_lovelace を超える live_stake を持つプール数,
      }
    """
    threshold = int(saturated_threshold_lovelace) if saturated_threshold_lovelace else 0
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
                SUM(CASE WHEN ? > 0 AND live_stake > ? THEN 1 ELSE 0 END) AS saturated_pools
            FROM pools
            """,
            (threshold, threshold),
        )
        row = cursor.fetchone() or {}
        return {k: int(v or 0) for k, v in dict(row).items()}
