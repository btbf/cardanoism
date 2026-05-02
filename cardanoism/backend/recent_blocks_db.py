"""
recent_blocks_db.py
recent_blocks テーブルの読み書き。
ogmios_listener.py がブロック確定時に insert_block を呼び、
ダッシュボードの LiveBlocksState が get_recent_blocks で読む。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


def insert_block(
    block_height: int,
    block_hash: str,
    slot_no: int,
    epoch_no: int,
    block_time: datetime,
    pool_id_hex: str | None = None,
    tx_count: int = 0,
    block_size: int = 0,
) -> None:
    """1ブロックを upsert。同じ block_height で別 hash が来た場合（chain rollback 後の再構築等）
    全フィールドを上書きして最新状態を維持する。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO recent_blocks
                (block_height, block_hash, slot_no, epoch_no, pool_id_hex, block_time, tx_count, block_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                block_hash  = VALUES(block_hash),
                slot_no     = VALUES(slot_no),
                epoch_no    = VALUES(epoch_no),
                pool_id_hex = VALUES(pool_id_hex),
                block_time  = VALUES(block_time),
                tx_count    = VALUES(tx_count),
                block_size  = VALUES(block_size),
                fetched_at  = CURRENT_TIMESTAMP
            """,
            (
                int(block_height),
                str(block_hash)[:128],
                int(slot_no),
                int(epoch_no),
                (str(pool_id_hex)[:64] if pool_id_hex else None),
                block_time,
                int(tx_count or 0),
                int(block_size or 0),
            ),
        )
        conn.commit()


def delete_blocks_after_slot(slot_no: int) -> int:
    """指定 slot より後 (slot_no > N) のブロックを削除。chain rollback で
    無効化されたブロックを recent_blocks から取り除くのに使う。返り値は削除件数。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            "DELETE FROM recent_blocks WHERE slot_no > ?",
            (int(slot_no),),
        )
        deleted = cursor.rowcount or 0
        conn.commit()
    return int(deleted)


def trim_old_blocks(keep: int = 100) -> int:
    """直近 keep 件だけ残し、それより古いブロックを削除。返り値は削除件数。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            DELETE FROM recent_blocks
            WHERE block_height NOT IN (
                SELECT block_height FROM (
                    SELECT block_height FROM recent_blocks
                    ORDER BY block_height DESC
                    LIMIT ?
                ) AS keep_set
            )
            """,
            (int(keep),),
        )
        deleted = cursor.rowcount or 0
        conn.commit()
    return int(deleted)


def get_recent_blocks(limit: int = 20) -> list[dict[str, Any]]:
    """直近 N 件のブロックを pools テーブル LEFT JOIN で ticker / 名前付きで返す。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT
                rb.block_height, rb.block_hash, rb.slot_no, rb.epoch_no,
                rb.pool_id_hex, rb.block_time, rb.tx_count, rb.block_size,
                p.ticker         AS pool_ticker,
                p.pool_name      AS pool_name,
                p.pool_id_bech32 AS pool_id_bech32,
                p.pool_icon_url  AS pool_icon_url
            FROM recent_blocks rb
            LEFT JOIN pools p ON p.pool_id_hex = rb.pool_id_hex
            ORDER BY rb.block_height DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        return [dict(r) for r in cursor.fetchall()]
