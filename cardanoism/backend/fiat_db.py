"""
fiat_db.py
ADA 法定通貨レートの DB キャッシュ（fiat_rate テーブル）。
"""
from __future__ import annotations

import logging

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


def upsert_fiat_rate(ada_jpy: float, ada_usd: float, source: str = "coingecko") -> None:
    """id=1 固定で上書き。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO fiat_rate (id, ada_jpy, ada_usd, source)
            VALUES (1, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              ada_jpy = VALUES(ada_jpy),
              ada_usd = VALUES(ada_usd),
              source  = VALUES(source)
            """,
            (float(ada_jpy), float(ada_usd), source),
        )
        conn.commit()


def get_fiat_rate() -> dict | None:
    """戻り値: {"ada_jpy": float, "ada_usd": float, "updated_at": datetime} or None"""
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT ada_jpy, ada_usd, source, updated_at FROM fiat_rate WHERE id = 1"
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "ada_jpy": float(row["ada_jpy"]),
            "ada_usd": float(row["ada_usd"]),
            "source": row.get("source") or "",
            "updated_at": row.get("updated_at"),
        }
