"""
staking_nav.py
ステーキング配下のサブページ（ダッシュボード / SPO 一覧）を横移動するピル型ナビゲーション。
governance_nav と同じ意匠で揃える。
"""
import reflex as rx

from cardanoism.backend.auth_state import AuthState


def _pill(label, href: str, icon_name: str, active: bool) -> rx.Component:
    base = {
        "display": "inline-flex",
        "alignItems": "center",
        "gap": "6px",
        "padding": "6px 14px",
        "borderRadius": "9999px",
        "fontSize": "14px",
        "fontWeight": "600",
        "textDecoration": "none",
        "border": "1px solid transparent",
        "transition": "background 0.15s, color 0.15s, border-color 0.15s",
        "cursor": "pointer",
    }
    if active:
        style = {
            **base,
            "background": "var(--amber-7)",
            "color": "var(--gray-12)",
            "border": "1px solid var(--amber-8)",
        }
    else:
        style = {
            **base,
            "background": "var(--gray-3)",
            "color": "var(--gray-11)",
        }
    return rx.link(
        rx.icon(icon_name, size=14),
        rx.text(label, size="2", weight="medium"),
        href=href,
        style=style,
        _hover=None if active else {
            "background": "var(--gray-4)",
            "color": "var(--gray-12)",
            "textDecoration": "none",
        },
        underline="none",
    )


def staking_subnav(active: str) -> rx.Component:
    """ステーキング共通のサブナビゲーション。

    Args:
        active: 現在のタブ（"dashboard" | "spo"）
    """
    return rx.hstack(
        _pill(AuthState.t["staking_subnav_dashboard"], "/staking", "layout-dashboard", active == "dashboard"),
        _pill(AuthState.t["staking_subnav_spo"], "/staking/spo", "server", active == "spo"),
        spacing="2",
        wrap="wrap",
        width="100%",
        padding_y="8px",
    )
