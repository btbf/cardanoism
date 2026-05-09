"""
staking_nav.py
ステーキング配下のサブページ（ダッシュボード / SPO 一覧）を横移動するピル型ナビゲーション。
"""
import reflex as rx

from cardanoism.backend.auth_state import AuthState
from cardanoism.components.subnav_pill import pill_subnav


def staking_subnav(active: str) -> rx.Component:
    """ステーキング共通のサブナビゲーション。

    Args:
        active: 現在のタブ（"why" | "dashboard" | "spo"）
    """
    return pill_subnav(active, [
        ("why",       AuthState.t["staking_subnav_why"],       "/staking/why",  "lightbulb"),
        ("dashboard", AuthState.t["staking_subnav_dashboard"], "/staking",      "layout-dashboard"),
        ("spo",       AuthState.t["staking_subnav_spo"],       "/staking/spo",  "server"),
    ])
