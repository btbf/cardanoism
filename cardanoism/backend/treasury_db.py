"""
treasury_db.py
トレジャリーページ用テーブル（treasury_snapshot / treasury_withdrawal / ncl_active）の CRUD。

同期は notify_worker.py --event treasury_sync で行う。
ページ側は常に DB を読むだけで、Koios は叩かない。
"""
from __future__ import annotations

import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


# ============================================================
# treasury_snapshot
# ============================================================

def upsert_treasury_snapshot(epoch_no: int, treasury: int,
                             reserves: int | None = None,
                             supply: int | None = None) -> None:
    """id=1 固定の単一行を常に上書き。ネットワーク切り替えにも追従する。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO treasury_snapshot (id, epoch_no, treasury, reserves, supply)
            VALUES (1, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              epoch_no = VALUES(epoch_no),
              treasury = VALUES(treasury),
              reserves = VALUES(reserves),
              supply   = VALUES(supply)
            """,
            (int(epoch_no), int(treasury), reserves, supply),
        )
        conn.commit()


def get_latest_treasury_snapshot() -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT epoch_no, treasury, reserves, supply, updated_at "
            "FROM treasury_snapshot WHERE id = 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# ============================================================
# treasury_withdrawal
# ============================================================

def insert_treasury_withdrawals(records: list[dict]) -> int:
    """新規の引き出し履歴を INSERT IGNORE で追加。戻り値は挿入件数。"""
    if not records:
        return 0
    rows = []
    for r in records:
        try:
            rows.append((
                r["stake_address"],
                int(r["amount_lovelace"]),
                int(r["earned_epoch"]),
                int(r["spendable_epoch"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        return 0
    with get_db() as (cursor, conn):
        cursor.executemany(
            """
            INSERT IGNORE INTO treasury_withdrawal
              (stake_address, amount_lovelace, earned_epoch, spendable_epoch)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        inserted = cursor.rowcount or 0
        conn.commit()
        return inserted


def get_withdrawals_recent(limit: int = 100) -> list[dict]:
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT stake_address, amount_lovelace, earned_epoch, spendable_epoch
            FROM treasury_withdrawal
            ORDER BY earned_epoch DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        return [dict(r) for r in cursor.fetchall()]


def sum_withdrawals_in_epoch_range(start_epoch: int, end_epoch: int) -> int:
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT COALESCE(SUM(amount_lovelace), 0) AS total
            FROM treasury_withdrawal
            WHERE earned_epoch BETWEEN ? AND ?
            """,
            (int(start_epoch), int(end_epoch)),
        )
        row = cursor.fetchone()
        if not row:
            return 0
        return int(row["total"] or 0)


# ============================================================
# NCL 期間内の TreasuryWithdrawals 提案（governance_actions ベース）
# ============================================================

def sum_enacted_withdrawals_in_epoch_range(start_epoch: int, end_epoch: int) -> int:
    """
    NCL 期間内に施行された TreasuryWithdrawals の合計 lovelace。
    実際に treasury_withdrawal に記録される前の「予定」額の計算に使う。
    """
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT COALESCE(SUM(withdrawal_total_lovelace), 0) AS total
            FROM governance_actions
            WHERE proposal_type = 'TreasuryWithdrawals'
              AND enacted_epoch IS NOT NULL
              AND enacted_epoch BETWEEN ? AND ?
            """,
            (int(start_epoch), int(end_epoch)),
        )
        row = cursor.fetchone()
        if not row:
            return 0
        return int(row["total"] or 0)


def get_treasury_proposals_in_epoch_range(start_epoch: int, end_epoch: int) -> list[dict]:
    """
    NCL 期間に関係する TreasuryWithdrawals 提案のリスト。
    - proposed_epoch が期間内、または
    - enacted_epoch が期間内
    のいずれかを含む（＝ステータスを問わず期間内に登場した提案）。
    最新順。
    """
    from cardanoism.backend.db_connect import _GA_STATUS_SQL  # 循環 import 回避のため関数内
    with get_db() as (cursor, _):
        cursor.execute(
            f"""
            SELECT proposal_id, proposal_tx_hash, proposal_index,
                   title, title_ja, proposed_epoch,
                   ratified_epoch, enacted_epoch, dropped_epoch, expired_epoch,
                   withdrawal_total_lovelace,
                   {_GA_STATUS_SQL} AS ga_status
            FROM governance_actions
            WHERE proposal_type = 'TreasuryWithdrawals'
              AND (
                    (proposed_epoch BETWEEN ? AND ?)
                 OR (enacted_epoch  BETWEEN ? AND ?)
              )
            ORDER BY proposed_epoch DESC, id DESC
            """,
            (int(start_epoch), int(end_epoch), int(start_epoch), int(end_epoch)),
        )
        return [dict(r) for r in cursor.fetchall()]


# ============================================================
# ncl_active
# ============================================================

def upsert_active_ncl(ncl: dict[str, Any]) -> None:
    """直近のDRep過半数賛成 NCL を 1 レコードとして保存（id=1 固定）。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO ncl_active
              (id, limit_ada, start_epoch, end_epoch, title,
               proposal_tx_hash, proposal_id, drep_yes_pct)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              limit_ada        = VALUES(limit_ada),
              start_epoch      = VALUES(start_epoch),
              end_epoch        = VALUES(end_epoch),
              title            = VALUES(title),
              proposal_tx_hash = VALUES(proposal_tx_hash),
              proposal_id      = VALUES(proposal_id),
              drep_yes_pct     = VALUES(drep_yes_pct)
            """,
            (
                int(ncl["limit_ada"]),
                int(ncl["start_epoch"]),
                int(ncl["end_epoch"]),
                str(ncl.get("title", ""))[:500],
                str(ncl.get("proposal_tx_hash", ""))[:64],
                str(ncl.get("proposal_id", ""))[:128],
                float(ncl.get("drep_yes_pct", 0.0)),
            ),
        )
        conn.commit()


def get_active_ncl() -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute(
            "SELECT limit_ada, start_epoch, end_epoch, title, "
            "proposal_tx_hash, proposal_id, drep_yes_pct, updated_at "
            "FROM ncl_active WHERE id = 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None
