"""
mempool_db.py
mempool_state テーブル (id=1 固定) の読み書き。
ogmios_listener.py の mempool poller が upsert し、
ダッシュボードがポーリングで読む。
"""
from __future__ import annotations

import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


def upsert_mempool_state(tx_count: int, byte_size: int, capacity_bytes: int | None) -> None:
    """id=1 固定の単一行を更新。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO mempool_state (id, tx_count, byte_size, capacity_bytes)
            VALUES (1, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                tx_count       = VALUES(tx_count),
                byte_size      = VALUES(byte_size),
                capacity_bytes = COALESCE(VALUES(capacity_bytes), capacity_bytes)
            """,
            (int(tx_count or 0), int(byte_size or 0),
             int(capacity_bytes) if capacity_bytes is not None else None),
        )
        conn.commit()


def get_mempool_state() -> dict[str, Any] | None:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT id, tx_count, byte_size, capacity_bytes, updated_at FROM mempool_state WHERE id = 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None
