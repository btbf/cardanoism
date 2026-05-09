"""
governance_nav.py
ガバナンス配下のサブページ（アクション一覧 / DRep / トレジャリー / 投票マトリクス / 憲法）を
横移動するピル型ナビゲーション。
"""
import reflex as rx

from cardanoism.backend.auth_state import AuthState
from cardanoism.components.subnav_pill import pill_subnav


def governance_subnav(active: str) -> rx.Component:
    """ガバナンス共通のサブナビゲーション。

    Args:
        active: 現在のタブ（"why" | "actions" | "matrix" | "treasury" | "drep" | "constitution"）

    並び順: ガバナンスとは → ガバナンス提案 → 投票マトリクス → トレジャリー → DRep 一覧 → Cardano 憲法
    """
    return pill_subnav(active, [
        ("why",          AuthState.t["gov_subnav_why"],          "/governance/why",          "lightbulb"),
        ("actions",      AuthState.t["gov_subnav_actions"],      "/governance",              "gavel"),
        ("matrix",       AuthState.t["gov_subnav_matrix"],       "/governance/matrix",       "table-2"),
        ("treasury",     AuthState.t["gov_subnav_treasury"],     "/governance/treasury",     "landmark"),
        ("drep",         AuthState.t["gov_subnav_drep"],         "/governance/drep",         "users"),
        ("constitution", AuthState.t["gov_subnav_constitution"], "/governance/constitution", "scroll-text"),
    ])
