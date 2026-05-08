"""
governance_nav.py
ガバナンス配下のサブページ（アクション一覧 / DRep / トレジャリー）を横移動するピル型ナビゲーション
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


def governance_subnav(active: str) -> rx.Component:
    """ガバナンス共通のサブナビゲーション。

    Args:
        active: 現在のタブ（"why" | "actions" | "matrix" | "treasury" | "drep" | "constitution"）

    並び順: ガバナンスとは → ガバナンス提案 → 投票マトリクス → トレジャリー → DRep 一覧 → Cardano 憲法
    """
    return rx.hstack(
        _pill(AuthState.t["gov_subnav_why"], "/governance/why", "lightbulb", active == "why"),
        _pill(AuthState.t["gov_subnav_actions"], "/governance", "gavel", active == "actions"),
        _pill(AuthState.t["gov_subnav_matrix"], "/governance/matrix", "table-2", active == "matrix"),
        _pill(AuthState.t["gov_subnav_treasury"], "/governance/treasury", "landmark", active == "treasury"),
        _pill(AuthState.t["gov_subnav_drep"], "/governance/drep", "users", active == "drep"),
        _pill(AuthState.t["gov_subnav_constitution"], "/governance/constitution", "scroll-text", active == "constitution"),
        spacing="2",
        wrap="wrap",
        width="100%",
        padding_y="8px",
    )
