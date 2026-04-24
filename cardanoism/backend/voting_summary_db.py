"""
voting_summary_db.py
proposal_voting_summary テーブルの CRUD。
"""
from __future__ import annotations

import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


_COLUMNS = [
    "proposal_type", "epoch_no",
    "drep_yes_votes_cast", "drep_no_votes_cast", "drep_abstain_votes_cast",
    "drep_yes_pct", "drep_no_pct",
    "pool_yes_votes_cast", "pool_no_votes_cast", "pool_abstain_votes_cast",
    "pool_yes_pct", "pool_no_pct",
    "committee_yes_votes_cast", "committee_no_votes_cast", "committee_abstain_votes_cast",
    "committee_yes_pct", "committee_no_pct",
]


def upsert_voting_summary(proposal_id: str, data: dict[str, Any]) -> None:
    cols = _COLUMNS
    placeholders = ", ".join(["?"] * (len(cols) + 1))
    updates = ", ".join([f"{c} = VALUES({c})" for c in cols])
    values = [proposal_id] + [data.get(c) for c in cols]
    with get_db() as (cursor, conn):
        cursor.execute(
            f"""
            INSERT INTO proposal_voting_summary (proposal_id, {', '.join(cols)})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {updates}
            """,
            values,
        )
        conn.commit()


def get_voting_summary(proposal_id: str) -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT * FROM proposal_voting_summary WHERE proposal_id = ?",
            (proposal_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
