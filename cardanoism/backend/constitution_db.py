"""
constitution_db.py
constitution_cache テーブル（憲法本文 + 日本語訳）の読み書き。

- notify_worker.py --event constitution_sync が IPFS から本文を取得 + 翻訳 → upsert
- /constitution ページが get_constitution で読み込み
"""
from __future__ import annotations

import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


def get_constitution() -> dict[str, Any] | None:
    """憲法キャッシュを取得（id=1 固定の単一行）。なければ None。"""
    with get_db() as (cursor, _):
        cursor.execute("SELECT * FROM constitution_cache WHERE id = 1 LIMIT 1")
        row = cursor.fetchone()
    return dict(row) if row else None


def upsert_constitution(
    *,
    proposal_id: str | None,
    enacted_epoch: int | None,
    source_url: str | None,
    original_text: str | None,
    translated_text: str | None = None,
    update_translation: bool = False,
) -> None:
    """憲法キャッシュを upsert する（id=1 固定）。

    - update_translation=False: 原文と取得タイムスタンプのみ更新（翻訳は別途）
    - update_translation=True:  翻訳テキスト + translated_at もまとめて更新
    """
    with get_db() as (cursor, conn):
        cursor.execute("SELECT id FROM constitution_cache WHERE id = 1")
        existed = cursor.fetchone() is not None

        if not existed:
            cursor.execute(
                """
                INSERT INTO constitution_cache
                    (id, proposal_id, enacted_epoch, source_url, original_text,
                     translated_text, fetched_at, translated_at)
                VALUES
                    (1, ?, ?, ?, ?, ?, NOW(), ?)
                """,
                (
                    proposal_id,
                    int(enacted_epoch) if enacted_epoch is not None else None,
                    source_url,
                    original_text,
                    translated_text if update_translation else None,
                    "NOW()" if update_translation else None,
                ),
            )
            # NOW() は文字列として渡せないので translated_at だけ別 UPDATE
            if update_translation:
                cursor.execute(
                    "UPDATE constitution_cache SET translated_at = NOW() WHERE id = 1"
                )
        else:
            if update_translation:
                cursor.execute(
                    """
                    UPDATE constitution_cache
                    SET proposal_id = ?,
                        enacted_epoch = ?,
                        source_url = ?,
                        original_text = ?,
                        translated_text = ?,
                        fetched_at = NOW(),
                        translated_at = NOW()
                    WHERE id = 1
                    """,
                    (
                        proposal_id,
                        int(enacted_epoch) if enacted_epoch is not None else None,
                        source_url,
                        original_text,
                        translated_text,
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE constitution_cache
                    SET proposal_id = ?,
                        enacted_epoch = ?,
                        source_url = ?,
                        original_text = ?,
                        fetched_at = NOW()
                    WHERE id = 1
                    """,
                    (
                        proposal_id,
                        int(enacted_epoch) if enacted_epoch is not None else None,
                        source_url,
                        original_text,
                    ),
                )
        conn.commit()
