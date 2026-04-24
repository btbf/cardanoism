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
    dreps 1 行を UPSERT。
    data は Koios レスポンスを merge して CIP-119 メタデータも含めた形を想定。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO dreps (
                drep_id, hex, has_script, registered, drep_status, active,
                deposit, expires_epoch_no, amount,
                given_name, image_url, payment_address,
                motivations, objectives, qualifications,
                references_json, meta_url, meta_hash, meta_is_valid
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?
            )
            ON DUPLICATE KEY UPDATE
                hex              = VALUES(hex),
                has_script       = VALUES(has_script),
                registered       = VALUES(registered),
                drep_status      = VALUES(drep_status),
                active           = VALUES(active),
                deposit          = VALUES(deposit),
                expires_epoch_no = VALUES(expires_epoch_no),
                amount           = VALUES(amount),
                given_name       = VALUES(given_name),
                image_url        = VALUES(image_url),
                payment_address  = VALUES(payment_address),
                motivations      = VALUES(motivations),
                objectives       = VALUES(objectives),
                qualifications   = VALUES(qualifications),
                references_json  = VALUES(references_json),
                meta_url         = VALUES(meta_url),
                meta_hash        = VALUES(meta_hash),
                meta_is_valid    = VALUES(meta_is_valid)
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
            ),
        )
        conn.commit()


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
