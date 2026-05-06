"""listener_db.py
Ogmios listener が DB を直接更新する設計 (Phase 0〜4) の共通ヘルパ。

責務:
  - listener が書き込む各テーブルの last_event_slot を一元管理
  - chain rollback (re-org) 通知時に slot > rollback_slot の行を巻き戻す
  - listener が登録するテーブルは LISTENER_MANAGED_TABLES に追記する

行動方針:
  - "delete": INSERT-only テーブル。rollback で単純削除
  - "skip"  : 状態列を listener が UPDATE するテーブル。rollback は次回 *_sync で復旧

Phase 0 では LISTENER_MANAGED_TABLES は雛形のみ。後続フェーズで追加していく。
"""
from __future__ import annotations

import logging
from typing import Literal

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


# rollback_slot より大きい slot で書かれた行をどう扱うか
RollbackAction = Literal["delete", "skip"]


# (table_name, slot_column, rollback_action)
# Phase ごとに行を追加していく。
LISTENER_MANAGED_TABLES: list[tuple[str, str, RollbackAction]] = [
    # Phase 1: GA / 投票 (新規 INSERT がメインなので rollback で DELETE 可)
    ("governance_actions", "last_event_slot", "delete"),
    ("proposal_votes",     "last_event_slot", "delete"),
    # Phase 2: DRep cert (Koios sync 由来の行を listener が UPDATE するケースが多いので skip)
    ("dreps",              "last_event_slot", "skip"),
    # Phase 3: Pool cert (同上。動的列は Koios sync で復旧)
    ("pools",              "last_event_slot", "skip"),
    # Phase 4: 委任 cert (ユーザー所有データなので DELETE 不可。Koios sync で復旧)
    ("stake_addresses",    "last_event_slot", "skip"),
]


def delete_rows_after_slot(table: str, slot_column: str, rollback_slot: int) -> int:
    """指定テーブルで slot_column > rollback_slot の行を DELETE して件数を返す。

    インデックスが効いていれば数千件規模でも数十ミリ秒で終わる。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            f"DELETE FROM {table} WHERE {slot_column} > ?",
            (int(rollback_slot),),
        )
        deleted = cursor.rowcount or 0
        conn.commit()
    return int(deleted)


def rollback_listener_state(rollback_slot: int) -> dict[str, int]:
    """全 listener 管理テーブルを rollback_slot 以降で巻き戻す。

    戻り値: {table_name: deleted_count}
    skip 指定のテーブルは戻り値に含まれない。
    """
    result: dict[str, int] = {}
    for table, slot_column, action in LISTENER_MANAGED_TABLES:
        if action != "delete":
            continue
        try:
            n = delete_rows_after_slot(table, slot_column, rollback_slot)
            result[table] = n
            if n > 0:
                logger.info(
                    "rollback: %s から %d 件削除 (%s > %d)",
                    table, n, slot_column, rollback_slot,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("rollback: %s の削除失敗: %s", table, e)
    return result
