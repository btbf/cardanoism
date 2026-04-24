"""
params_db.py
protocol_params テーブル（id=1 固定の単一行）の CRUD と、提案タイプごとの閾値マッピング。
同期は notify_worker.py --event params_sync で行う。
"""
from __future__ import annotations

import logging
from typing import Any

from cardanoism.backend.db_connect import get_db

logger = logging.getLogger(__name__)


_PARAM_COLUMNS = [
    "epoch_no",
    "dvt_motion_no_confidence", "dvt_committee_normal", "dvt_committee_no_confidence",
    "dvt_update_to_constitution", "dvt_hard_fork_initiation",
    "dvt_p_p_network_group", "dvt_p_p_economic_group",
    "dvt_p_p_technical_group", "dvt_p_p_gov_group",
    "dvt_treasury_withdrawal",
    "pvt_motion_no_confidence", "pvt_committee_normal", "pvt_committee_no_confidence",
    "pvt_hard_fork_initiation", "pvtpp_security_group",
    "committee_min_size", "committee_max_term_length",
    "gov_action_lifetime", "gov_action_deposit",
    "drep_deposit", "drep_activity",
    "cc_quorum_numerator", "cc_quorum_denominator",
]


def upsert_protocol_params(data: dict[str, Any]) -> None:
    """Koios /epoch_params のレスポンスを id=1 固定で上書き保存する。"""
    cols = _PARAM_COLUMNS
    placeholders = ", ".join(["?"] * (len(cols) + 1))  # +1 for id
    updates = ", ".join([f"{c} = VALUES({c})" for c in cols])
    values = [1] + [data.get(c) for c in cols]
    with get_db() as (cursor, conn):
        cursor.execute(
            f"""
            INSERT INTO protocol_params (id, {', '.join(cols)})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {updates}
            """,
            values,
        )
        conn.commit()


def upsert_cc_member(data: dict[str, Any]) -> None:
    """cc_members へ UPSERT。display_name は既存値を保持（手動編集を壊さない）。"""
    with get_db() as (cursor, conn):
        cursor.execute(
            """
            INSERT INTO cc_members (
                cc_cold_id, cc_cold_hex, cc_hot_id, cc_hot_hex,
                status, expiration_epoch, cc_hot_has_script, cc_cold_has_script
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                cc_cold_hex        = VALUES(cc_cold_hex),
                cc_hot_id          = VALUES(cc_hot_id),
                cc_hot_hex         = VALUES(cc_hot_hex),
                status             = VALUES(status),
                expiration_epoch   = VALUES(expiration_epoch),
                cc_hot_has_script  = VALUES(cc_hot_has_script),
                cc_cold_has_script = VALUES(cc_cold_has_script)
            """,
            (
                data.get("cc_cold_id"),
                data.get("cc_cold_hex"),
                data.get("cc_hot_id"),
                data.get("cc_hot_hex"),
                data.get("status"),
                data.get("expiration_epoch"),
                int(bool(data.get("cc_hot_has_script"))),
                int(bool(data.get("cc_cold_has_script"))),
            ),
        )
        conn.commit()


def get_active_cc_members() -> list[dict]:
    """authorized なアクティブ CC メンバー一覧。"""
    with get_db() as (cursor, _):
        cursor.execute(
            """
            SELECT cc_cold_id, cc_hot_id, status, expiration_epoch, display_name
            FROM cc_members
            WHERE status = 'authorized'
            ORDER BY cc_cold_id
            """
        )
        return [dict(r) for r in cursor.fetchall()]


def get_protocol_params() -> dict | None:
    with get_db() as (cursor, _):
        cursor.execute("SELECT * FROM protocol_params WHERE id = 1")
        row = cursor.fetchone()
        return dict(row) if row else None


# ============================================================
# 提案タイプごとの閾値マッピング
# ============================================================
# CIP-1694 に基づき、各 GA タイプで必要な DRep / SPO の投票閾値を返す。
# 閾値が存在しないロール（例: SPO は TreasuryWithdrawals に投票しない）は None。
# 値は 0.0〜1.0 の fraction。

def voters_for_type(proposal_type: str) -> dict:
    """
    各 GA タイプでの投票対象ロールを返す。
      True  : そのロールが投票対象
      False : 対象外（UI ではグレーアウト表示）
      "conditional": 条件付き（ParameterChange の SPO はサブグループが security 関連の場合のみ）

    CIP-1694 に準拠:
      - NoConfidence / NewCommittee  : CC は対象外（委員会自身に関する決議のため）
      - NewConstitution              : SPO は対象外
      - HardForkInitiation / InfoAction : 全員対象
      - TreasuryWithdrawals          : SPO は対象外
      - ParameterChange              : SPO は security サブグループのみ（条件付き）
    """
    mapping = {
        "NoConfidence":        {"drep": True,  "pool": True,          "committee": False},
        "NewCommittee":        {"drep": True,  "pool": True,          "committee": False},
        "NewConstitution":     {"drep": True,  "pool": False,         "committee": True},
        "HardForkInitiation":  {"drep": True,  "pool": True,          "committee": True},
        "ParameterChange":     {"drep": True,  "pool": "conditional", "committee": True},
        "TreasuryWithdrawals": {"drep": True,  "pool": False,         "committee": True},
        "InfoAction":          {"drep": True,  "pool": True,          "committee": True},
    }
    return mapping.get(proposal_type or "", {"drep": True, "pool": True, "committee": True})


def thresholds_for_type(proposal_type: str, params: dict | None) -> dict:
    """戻り値: {"drep": float|None, "pool": float|None, "committee": float|None}

    CC の閾値は CIP-1694 に従い committee_info.quorum_numerator / quorum_denominator（現 mainnet は 2/3）。
    voters_for_type と連動し、CC 投票対象外の GA タイプ（NoConfidence / NewCommittee）では None。
    """
    if not params:
        return {"drep": None, "pool": None, "committee": None}

    def f(k):
        v = params.get(k)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    # CC quorum を算出
    cc_num = params.get("cc_quorum_numerator")
    cc_den = params.get("cc_quorum_denominator")
    try:
        cc_q = float(cc_num) / float(cc_den) if cc_num and cc_den else None
    except (TypeError, ValueError, ZeroDivisionError):
        cc_q = None

    # 各 GA タイプの CC 閾値: voters_for_type で True のものは cc_q を使う
    voters = voters_for_type(proposal_type)
    committee_th = cc_q if voters.get("committee") is True else None

    mapping = {
        "NoConfidence": {
            "drep":      f("dvt_motion_no_confidence"),
            "pool":      f("pvt_motion_no_confidence"),
            "committee": committee_th,
        },
        "NewCommittee": {
            "drep":      f("dvt_committee_normal"),
            "pool":      f("pvt_committee_normal"),
            "committee": committee_th,
        },
        "NewConstitution": {
            "drep":      f("dvt_update_to_constitution"),
            "pool":      None,
            "committee": committee_th,
        },
        "HardForkInitiation": {
            "drep":      f("dvt_hard_fork_initiation"),
            "pool":      f("pvt_hard_fork_initiation"),
            "committee": committee_th,
        },
        "ParameterChange": {
            "drep": max(
                (v for v in [f("dvt_p_p_network_group"), f("dvt_p_p_economic_group"),
                             f("dvt_p_p_technical_group"), f("dvt_p_p_gov_group")] if v is not None),
                default=None,
            ),
            "pool":      f("pvtpp_security_group"),
            "committee": committee_th,
        },
        "TreasuryWithdrawals": {
            "drep":      f("dvt_treasury_withdrawal"),
            "pool":      None,
            "committee": committee_th,
        },
        "InfoAction": {
            # InfoAction は情報提案だが、DRep / SPO / CC いずれも 50% を合意ラインとする
            "drep":      0.50,
            "pool":      0.50,
            "committee": 0.50 if voters.get("committee") is True else None,
        },
    }
    return mapping.get(
        proposal_type or "",
        {"drep": None, "pool": None, "committee": committee_th},
    )
