"""
drep_db.py
dreps テーブルの CRUD。同期は notify_worker.py --event drep_sync で行う。
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

def upsert_drep(data: dict[str, Any]) -> None:
    """
    dreps 1 行を UPSERT (CIP-119 metadata 取り込みあり)。
    data は /drep_info + /drep_metadata の merge 結果を想定。

    注意:
      - amount は ON DUPLICATE KEY UPDATE で更新しない。
        live amount は別経路 (update_drep_amount via /drep_delegators) で管理する。
        新規 INSERT 時のみ data["amount"] (= 0 想定) が入る。
      - meta_fetched_hash は data["meta_hash"] を自動で同期する。
        この関数を呼ぶ = 実際に CIP-119 を取り込んだ という意味。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO dreps (
                drep_id, hex, has_script, registered, drep_status, active,
                deposit, expires_epoch_no, amount,
                given_name, image_url, payment_address,
                motivations, objectives, qualifications,
                references_json, meta_url, meta_hash, meta_is_valid,
                meta_fetched_hash
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?
            )
            ON DUPLICATE KEY UPDATE
                hex               = VALUES(hex),
                has_script        = VALUES(has_script),
                registered        = VALUES(registered),
                drep_status       = VALUES(drep_status),
                active            = VALUES(active),
                deposit           = VALUES(deposit),
                expires_epoch_no  = VALUES(expires_epoch_no),
                given_name        = VALUES(given_name),
                image_url         = VALUES(image_url),
                payment_address   = VALUES(payment_address),
                motivations       = VALUES(motivations),
                objectives        = VALUES(objectives),
                qualifications    = VALUES(qualifications),
                references_json   = VALUES(references_json),
                meta_url          = VALUES(meta_url),
                meta_hash         = VALUES(meta_hash),
                meta_is_valid     = VALUES(meta_is_valid),
                meta_fetched_hash = VALUES(meta_fetched_hash)
            """,
            (
                data.get("drep_id"),
                data.get("hex"),
                int(bool(data.get("has_script"))),
                int(bool(data.get("registered"))),
                data.get("drep_status"),
                int(bool(data.get("active"))),
                int(data["deposit"]) if data.get("deposit") is not None else None,
                data.get("expires_epoch_no"),
                int(data.get("amount") or 0),
                (data.get("given_name") or None),
                (data.get("image_url") or None),
                (data.get("payment_address") or None),
                (data.get("motivations") or None),
                (data.get("objectives") or None),
                (data.get("qualifications") or None),
                (data.get("references_json") or None),
                (data.get("meta_url") or None),
                (data.get("meta_hash") or None),
                int(bool(data["meta_is_valid"])) if data.get("meta_is_valid") is not None else None,
                (data.get("meta_hash") or None),
            ),
        )
        conn.commit()


def update_drep_info(data: dict[str, Any]) -> None:
    """
    dreps の info 列 (drep_status / active / deposit / expires_epoch_no /
    meta_url / meta_hash) のみを更新する。

    用途: CIP-119 metadata に変化が無いことが確認できた DRep を refresh する場合。
    meta_fetched_hash は触らない (= metadata 本体は古いまま保持)。
    amount も触らない (live は別経路)。

    対象 drep_id が DB に存在しない場合は何もしない (新規行は upsert_drep 経由)。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            UPDATE dreps SET
                drep_status      = ?,
                active           = ?,
                deposit          = ?,
                expires_epoch_no = ?,
                meta_url         = ?,
                meta_hash        = ?
            WHERE drep_id = ?
            """,
            (
                data.get("drep_status"),
                int(bool(data.get("active"))),
                int(data["deposit"]) if data.get("deposit") is not None else None,
                data.get("expires_epoch_no"),
                (data.get("meta_url") or None),
                (data.get("meta_hash") or None),
                data.get("drep_id"),
            ),
        )
        conn.commit()


def update_drep_amount(drep_id: str, amount: int) -> None:
    """dreps.amount のみを更新 (live amount sync 用)。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            "UPDATE dreps SET amount = ? WHERE drep_id = ?",
            (int(amount), drep_id),
        )
        conn.commit()


def get_drep_meta_fetched_hashes() -> dict[str, str | None]:
    """全 DRep の {drep_id: meta_fetched_hash} を返す (差分判定用)。"""
    with get_db() as (cursor, _conn):
        cursor.execute("SELECT drep_id, meta_fetched_hash FROM dreps")
        return {row["drep_id"]: row.get("meta_fetched_hash") for row in cursor.fetchall()}


def get_active_drep_ids() -> list[str]:
    """active かつ registered な DRep の drep_id 一覧 (live amount sync 対象)。"""
    with get_db() as (cursor, _conn):
        cursor.execute(
            "SELECT drep_id FROM dreps WHERE registered = 1 AND drep_status = 'active'"
        )
        return [row["drep_id"] for row in cursor.fetchall()]


def bulk_upsert_dreps(records: list[dict]) -> int:
    count = 0
    for r in records:
        try:
            upsert_drep(r)
            count += 1
        except Exception as e:
            logger.exception("upsert_drep failed (drep_id=%s): %s", r.get("drep_id"), e)
    return count


# ============================================================
# 読み込み
# ============================================================

_SORT_CLAUSES = {
    "amount_desc":   "amount DESC, drep_id ASC",
    "amount_asc":    "amount ASC, drep_id ASC",
    "name_asc":      "COALESCE(given_name, drep_id) ASC",
    "name_desc":     "COALESCE(given_name, drep_id) DESC",
    "active":        "active DESC, amount DESC",
}


def get_dreps(
    search: str = "",
    only_registered: bool = True,
    sort: str = "amount_desc",
    limit: int = 30,
    offset: int = 0,
) -> list[dict]:
    """DRep 一覧を取得する。search は given_name / drep_id の部分一致。"""
    where = ["1=1"]
    params: list = []
    if only_registered:
        where.append("registered = 1")
    if search:
        where.append("(given_name LIKE ? OR drep_id LIKE ?)")
        sv = f"%{search}%"
        params.extend([sv, sv])
    order = _SORT_CLAUSES.get(sort, _SORT_CLAUSES["amount_desc"])
    sql = (
        "SELECT drep_id, hex, drep_status, active, amount, "
        "given_name, image_url, references_json, meta_url, meta_is_valid, "
        "expires_epoch_no, updated_at "
        "FROM dreps "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {order} "
        f"LIMIT {int(limit)} OFFSET {int(offset)}"
    )
    with get_db() as (cursor, _):
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]


def count_dreps(search: str = "", only_registered: bool = True) -> int:
    where = ["1=1"]
    params: list = []
    if only_registered:
        where.append("registered = 1")
    if search:
        where.append("(given_name LIKE ? OR drep_id LIKE ?)")
        sv = f"%{search}%"
        params.extend([sv, sv])
    sql = f"SELECT COUNT(*) AS cnt FROM dreps WHERE {' AND '.join(where)}"
    with get_db() as (cursor, _):
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return int((row or {}).get("cnt", 0))


def sum_total_delegation(only_registered: bool = True) -> int:
    """全 DRep の委任量合計（lovelace）。"""
    where = "registered = 1" if only_registered else "1=1"
    with get_db() as (cursor, _):
        cursor.execute(f"SELECT COALESCE(SUM(amount), 0) AS total FROM dreps WHERE {where}")
        row = cursor.fetchone()
        return int((row or {}).get("total", 0))


def get_drep(drep_id: str) -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute("SELECT * FROM dreps WHERE drep_id = ?", (drep_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
