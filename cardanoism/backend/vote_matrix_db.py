"""vote_matrix_db.py
投票マトリクス（DRep / CC / SPO × GA）のデータ取得ヘルパー (読み取り専用)。

使用テーブル: governance_actions / proposal_votes / dreps / cc_members / pools
"""
from __future__ import annotations

from typing import Any

from cardanoism.backend.db_connect import get_db


VALID_GA_STATUSES = ("active", "ratified", "enacted", "dropped", "expired")


def _ga_status_where(status: str) -> str:
    """ステータス文字列から WHERE 句を生成 (LIMIT/OFFSET なし)。"""
    if status not in VALID_GA_STATUSES:
        status = "active"
    if status == "active":
        return (
            " WHERE ratified_epoch IS NULL"
            "   AND enacted_epoch  IS NULL"
            "   AND dropped_epoch  IS NULL"
            "   AND expired_epoch  IS NULL"
        )
    col = f"{status}_epoch"
    return f" WHERE {col} IS NOT NULL"


def count_gas_for_matrix(*, status: str = "active") -> int:
    """指定ステータスの GA 件数を返す (ページネーション用)。"""
    where = _ga_status_where(status)
    sql = f"SELECT COUNT(*) AS n FROM governance_actions {where}"
    with get_db() as (cursor, _):
        cursor.execute(sql)
        row = cursor.fetchone()
        if not row:
            return 0
        return int(dict(row).get("n") or 0)


def get_gas_for_matrix(
    *, status: str = "active", limit: int = 30, offset: int = 0,
    order: str = "asc",
) -> list[dict[str, Any]]:
    """指定ステータスの GA 一覧を返す。

    status:
      - "active":   ratified/enacted/dropped/expired すべて NULL（投票進行中）
      - "ratified": ratified_epoch が NOT NULL
      - "enacted":  enacted_epoch  が NOT NULL
      - "dropped":  dropped_epoch  が NOT NULL
      - "expired":  expired_epoch  が NOT NULL

    order:
      - "asc"  (デフォルト): 左 → 右 = 古い → 新しい (時系列順)。
                            同一 Tx 内は proposal_index ASC (小 → 大)
      - "desc":              左 → 右 = 新しい → 古い (新着順)。
                            同一 Tx 内は proposal_index DESC (大 → 小)

    戻り値要素: {proposal_id, title, title_ja, proposal_type, expiration, proposed_epoch}
    """
    where = _ga_status_where(status)
    direction = "DESC" if (order or "").lower() == "desc" else "ASC"
    sql = f"""
        SELECT proposal_id,
               title,
               title_ja,
               proposal_type,
               expiration,
               proposed_epoch
          FROM governance_actions
          {where}
         ORDER BY block_time {direction}, proposed_epoch {direction}, proposal_index {direction}
         LIMIT ? OFFSET ?
    """
    with get_db() as (cursor, _):
        cursor.execute(sql, (int(limit), int(offset)))
        return [dict(r) for r in cursor.fetchall()]


def get_active_gas() -> list[dict[str, Any]]:
    """後方互換のための薄いラッパー。新規コードは get_gas_for_matrix() を使う。"""
    return get_gas_for_matrix(status="active", limit=10000, offset=0)


def count_dreps_for_matrix(*, search: str = "") -> int:
    """マトリクス対象 DRep の総数。registered=1 のみ。"""
    where = "WHERE registered = 1"
    params: list = []
    if search:
        where += " AND (given_name LIKE ? OR drep_id LIKE ?)"
        like = f"%{search}%"
        params += [like, like]
    sql = f"SELECT COUNT(*) AS n FROM dreps {where}"
    with get_db() as (cursor, _):
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        if not row:
            return 0
        return int(dict(row).get("n") or 0)


def get_dreps_for_matrix(
    *, search: str = "", limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    """マトリクスの行 (DRep) を取得。registered=1 のみ、amount 降順。"""
    where = "WHERE registered = 1"
    params: list = []
    if search:
        where += " AND (given_name LIKE ? OR drep_id LIKE ?)"
        like = f"%{search}%"
        params += [like, like]
    sql = f"""
        SELECT drep_id, given_name, image_url, drep_status, active, amount
          FROM dreps
          {where}
         ORDER BY amount DESC
         LIMIT ? OFFSET ?
    """
    params += [int(limit), int(offset)]
    with get_db() as (cursor, _):
        cursor.execute(sql, tuple(params))
        return [dict(r) for r in cursor.fetchall()]


def get_votes_for_matrix(
    voter_ids: list[str], proposal_ids: list[str], voter_role: str = "DRep"
) -> dict[tuple[str, str], dict[str, Any]]:
    """指定 voter × GA の投票レコードを取得。

    voter_role: "DRep" / "ConstitutionalCommittee" / "SPO"
    戻り値: {(voter_id, proposal_id): {vote, rationale, rationale_ja}}
    投票レコードが存在しない組み合わせは含まれない。
    """
    if not voter_ids or not proposal_ids:
        return {}
    placeholders_v = ",".join(["?"] * len(voter_ids))
    placeholders_p = ",".join(["?"] * len(proposal_ids))
    sql = f"""
        SELECT voter_id,
               proposal_id,
               vote,
               rationale,
               rationale_ja
          FROM proposal_votes
         WHERE voter_role = ?
           AND voter_id    IN ({placeholders_v})
           AND proposal_id IN ({placeholders_p})
    """
    params = [voter_role] + list(voter_ids) + list(proposal_ids)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    with get_db() as (cursor, _):
        cursor.execute(sql, tuple(params))
        for r in cursor.fetchall():
            d = dict(r)
            out[(d["voter_id"], d["proposal_id"])] = {
                "vote":         d.get("vote") or "",
                "rationale":    d.get("rationale") or "",
                "rationale_ja": d.get("rationale_ja") or "",
            }
    return out


# ─── CC（憲法委員会）行 ──────────────────────────────────────────────────────

def count_cc_for_matrix(*, search: str = "") -> int:
    """マトリクス対象 CC メンバーの総数。authorized のみ。"""
    where = "WHERE status = 'authorized'"
    params: list = []
    if search:
        where += " AND display_name LIKE ?"
        params.append(f"%{search}%")
    sql = f"SELECT COUNT(*) AS n FROM cc_members {where}"
    with get_db() as (cursor, _):
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        return int(dict(row).get("n") or 0) if row else 0


def get_cc_for_matrix(
    *, search: str = "", limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    """マトリクスの行 (CC メンバー) を取得。authorized のみ。"""
    where = "WHERE status = 'authorized'"
    params: list = []
    if search:
        where += " AND display_name LIKE ?"
        params.append(f"%{search}%")
    sql = f"""
        SELECT cc_cold_id, cc_hot_id, display_name, status
          FROM cc_members
          {where}
         ORDER BY cc_cold_id
         LIMIT ? OFFSET ?
    """
    params += [int(limit), int(offset)]
    with get_db() as (cursor, _):
        cursor.execute(sql, tuple(params))
        return [dict(r) for r in cursor.fetchall()]


# ─── SPO（ステークプール）行 ────────────────────────────────────────────────

def _spo_where(search: str) -> tuple[str, list]:
    where = "WHERE (pool_status IS NULL OR pool_status <> 'retired')"
    params: list = []
    if search:
        if search.lower().startswith("pool1"):
            where += " AND pool_id_bech32 LIKE ?"
            params.append(f"%{search}%")
        else:
            where += " AND (ticker LIKE ? OR pool_name LIKE ?)"
            like = f"%{search}%"
            params += [like, like]
    return where, params


def count_spo_for_matrix(*, search: str = "") -> int:
    """マトリクス対象 SPO の総数（retired 除く）。"""
    where, params = _spo_where(search)
    sql = f"SELECT COUNT(*) AS n FROM pools {where}"
    with get_db() as (cursor, _):
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        return int(dict(row).get("n") or 0) if row else 0


def get_spo_for_matrix(
    *, search: str = "", limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    """マトリクスの行 (SPO) を取得。retired 除く、live_stake 降順。"""
    where, params = _spo_where(search)
    sql = f"""
        SELECT pool_id_bech32, ticker, pool_name, pool_icon_url
          FROM pools
          {where}
         ORDER BY live_stake DESC
         LIMIT ? OFFSET ?
    """
    params += [int(limit), int(offset)]
    with get_db() as (cursor, _):
        cursor.execute(sql, tuple(params))
        return [dict(r) for r in cursor.fetchall()]
