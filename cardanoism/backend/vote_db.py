"""
vote_db.py
proposal_votes テーブルの CRUD。同期は notify_worker.py --event vote_sync。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


def _to_dt(block_time) -> datetime | None:
    if block_time is None:
        return None
    try:
        return datetime.fromtimestamp(int(block_time), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def upsert_vote(data: dict[str, Any]) -> None:
    """
    1 件の投票を UPSERT。同一 voter が既に登録済みの場合、
    block_time が新しい（>= 既存）場合のみ上書きする。古いトランザクションの投票で
    新しい投票を上書きしないためのガード。
    """
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO proposal_votes (
                proposal_id, voter_role, voter_id, voter_hex, voter_has_script,
                vote, block_time, meta_url, meta_hash, last_event_slot
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            ON DUPLICATE KEY UPDATE
                voter_hex        = IF(VALUES(block_time) IS NOT NULL AND (block_time IS NULL OR VALUES(block_time) >= block_time), VALUES(voter_hex),        voter_hex),
                voter_has_script = IF(VALUES(block_time) IS NOT NULL AND (block_time IS NULL OR VALUES(block_time) >= block_time), VALUES(voter_has_script), voter_has_script),
                vote             = IF(VALUES(block_time) IS NOT NULL AND (block_time IS NULL OR VALUES(block_time) >= block_time), VALUES(vote),             vote),
                meta_url         = IF(VALUES(block_time) IS NOT NULL AND (block_time IS NULL OR VALUES(block_time) >= block_time), VALUES(meta_url),         meta_url),
                meta_hash        = IF(VALUES(block_time) IS NOT NULL AND (block_time IS NULL OR VALUES(block_time) >= block_time), VALUES(meta_hash),        meta_hash),
                block_time       = IF(VALUES(block_time) IS NOT NULL AND (block_time IS NULL OR VALUES(block_time) >= block_time), VALUES(block_time),       block_time),
                -- listener が書いた slot を保持 (Koios 由来 NULL で上書きしない)
                last_event_slot  = COALESCE(VALUES(last_event_slot), last_event_slot)
            """,
            (
                data.get("proposal_id"),
                data.get("voter_role") or "",
                data.get("voter_id") or "",
                data.get("voter_hex"),
                int(bool(data.get("voter_has_script"))),
                data.get("vote") or "",
                _to_dt(data.get("block_time")),
                data.get("meta_url"),
                data.get("meta_hash"),
                data.get("last_event_slot"),
            ),
        )
        conn.commit()


def bulk_upsert_votes(proposal_id: str, votes: list[dict]) -> int:
    inserted = 0
    for v in votes:
        v2 = dict(v)
        v2["proposal_id"] = proposal_id
        try:
            upsert_vote(v2)
            inserted += 1
        except Exception as e:
            logger.exception("upsert_vote failed: %s", e)
    return inserted


def get_votes_by_proposal(proposal_id: str) -> list[dict]:
    """指定 proposal の投票一覧を role 昇順, block_time 降順で返す。
    voter_role='DRep' の場合は dreps テーブルから given_name を LEFT JOIN で取得する。
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT v.id, v.proposal_id, v.voter_role, v.voter_id, v.voter_hex, v.voter_has_script,
                   v.vote, v.block_time, v.meta_url, v.meta_hash, v.rationale, v.rationale_ja,
                   CASE WHEN v.voter_role = 'DRep' THEN d.given_name ELSE NULL END AS drep_name
            FROM proposal_votes v
            LEFT JOIN dreps d ON d.drep_id = v.voter_id AND v.voter_role = 'DRep'
            WHERE v.proposal_id = ?
            ORDER BY v.voter_role ASC, v.block_time DESC
            """,
            (proposal_id,),
        )
        return [dict(r) for r in cursor.fetchall()]


def count_votes_by_proposal(proposal_id: str) -> int:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM proposal_votes WHERE proposal_id = ?",
            (proposal_id,),
        )
        row = cursor.fetchone()
        return int((row or {}).get("cnt", 0))


def get_votes_by_drep(drep_id: str, limit: int = 500) -> list[dict]:
    """指定 DRep の投票実績を返す。**未投票のGA も含めて** governance_actions を主軸に返す。
    投票が無い GA は vote が NULL で返る。並び順は GA の block_time 降順。
    """
    if not drep_id:
        return []
    from cardanoism.backend.db_connect import _GA_STATUS_SQL_GA
    with get_db() as (cursor, _):
        cursor.execute(
            f"""
            SELECT v.id AS vote_id, v.vote, v.block_time AS vote_time,
                   v.rationale, v.rationale_ja, v.meta_url,
                   ga.proposal_id, ga.proposal_tx_hash, ga.proposal_index,
                   ga.proposal_type, ga.title, ga.title_ja,
                   ga.proposed_epoch, ga.ratified_epoch, ga.enacted_epoch,
                   ga.dropped_epoch, ga.expired_epoch,
                   ga.block_time AS ga_block_time,
                   {_GA_STATUS_SQL_GA} AS ga_status
            FROM governance_actions ga
            LEFT JOIN proposal_votes v
                   ON v.proposal_id = ga.proposal_id
                  AND v.voter_role = 'DRep'
                  AND v.voter_id = ?
            ORDER BY ga.block_time DESC
            LIMIT ?
            """,
            (drep_id, int(limit)),
        )
        return [dict(r) for r in cursor.fetchall()]


def count_votes_by_drep(drep_id: str) -> dict:
    """DRep の投票集計（Yes/No/Abstain 各件数）。"""
    if not drep_id:
        return {"yes": 0, "no": 0, "abstain": 0, "total": 0}
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT vote, COUNT(*) AS cnt
            FROM proposal_votes
            WHERE voter_role = 'DRep' AND voter_id = ?
            GROUP BY vote
            """,
            (drep_id,),
        )
        result = {"yes": 0, "no": 0, "abstain": 0}
        total = 0
        for row in cursor.fetchall():
            v = str(row.get("vote") or "").lower()
            c = int(row.get("cnt") or 0)
            total += c
            if v == "yes":
                result["yes"] = c
            elif v == "no":
                result["no"] = c
            elif v == "abstain":
                result["abstain"] = c
        result["total"] = total
        return result


def update_rationale(vote_id: int, rationale: str | None, rationale_ja: str | None = None) -> None:
    """メタデータ取得後に rationale を更新する。Phase 4 で使用。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            UPDATE proposal_votes
            SET rationale = ?, rationale_ja = COALESCE(?, rationale_ja), meta_fetched_at = NOW()
            WHERE id = ?
            """,
            (rationale, rationale_ja, int(vote_id)),
        )
        conn.commit()
