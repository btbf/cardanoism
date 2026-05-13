"""mobile_page_subnav.py
スマホ専用: 各セクション (staking / governance / catalyst) のサブナビを
フッターの直上に全幅リンクとして表示する。

デスクトップでは表示しない。各ページ上部にあるピル型サブナビ
(staking_nav / governance_nav / catalyst_tabs) は CSS でスマホ時に
非表示になる前提。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.auth_state import AuthState


def _full_width_link(icon_name: str, label, href: str) -> rx.Component:
    """全幅リンク行。現在のパスと href が一致したら active 表示。"""
    active = AuthState.current_path == href
    return rx.link(
        rx.hstack(
            rx.icon(
                icon_name,
                size=16,
                color=rx.cond(active, "var(--amber-11)", "var(--gray-10)"),
                flex_shrink="0",
            ),
            rx.text(
                label,
                size="3",
                weight=rx.cond(active, "bold", "medium"),
                color=rx.cond(active, "var(--amber-12)", "var(--gray-12)"),
            ),
            rx.spacer(),
            rx.icon(
                "chevron-right",
                size=14,
                color=rx.cond(active, "var(--amber-11)", "var(--gray-9)"),
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
        href=href,
        underline="none",
        style={
            "display":      "block",
            "padding":      "14px 16px",
            "borderBottom": "1px solid var(--gray-5)",
            "background":   rx.cond(active, "var(--amber-2)", "transparent"),
            "transition":   "background 0.12s",
            "width":        "100%",
        },
        _hover=rx.cond(active, None, {"background": rx.color("gray", 2)}),
    )


_STAKING_ITEMS: list[tuple[str, str, str]] = [
    ("lightbulb",        "staking_subnav_why",       "/staking/why"),
    ("layout-dashboard", "staking_subnav_dashboard", "/staking"),
    ("server",           "staking_subnav_spo",       "/staking/spo"),
]

_GOVERNANCE_ITEMS: list[tuple[str, str, str]] = [
    ("lightbulb",    "gov_subnav_why",          "/governance/why"),
    ("gavel",        "gov_subnav_actions",      "/governance"),
    ("table-2",      "gov_subnav_matrix",       "/governance/matrix"),
    ("landmark",     "gov_subnav_treasury",     "/governance/treasury"),
    ("users",        "gov_subnav_drep",         "/governance/drep"),
    ("scroll-text",  "gov_subnav_constitution", "/governance/constitution"),
]

_CATALYST_ITEMS: list[tuple[str, str, str]] = [
    ("file-text", "nav_proposals_list", "/catalyst"),
    ("layers",    "nav_funds_list",     "/catalyst/funds"),
]


def _section_block(items: list[tuple[str, str, str]]) -> rx.Component:
    return rx.vstack(
        *[_full_width_link(icon, AuthState.t[label_key], href)
          for icon, label_key, href in items],
        spacing="0",
        align_items="stretch",
        width="100%",
        style={
            "borderTop":    "1px solid var(--gray-5)",
            "borderBottom": "1px solid var(--gray-5)",
            "background":   "var(--gray-1)",
        },
    )


def mobile_page_subnav() -> rx.Component:
    """フッター直上に挟むモバイル専用サブナビ。
    デスクトップでは display:none。

    template_page_style の padding-bottom (2em) + template_content_style の
    margin-bottom (2em) で 64px 開いてしまうので、negative margin で詰める。
    """
    body = rx.match(
        AuthState.mobile_subnav_section,
        ("staking",    _section_block(_STAKING_ITEMS)),
        ("governance", _section_block(_GOVERNANCE_ITEMS)),
        ("catalyst",   _section_block(_CATALYST_ITEMS)),
        rx.fragment(),
    )
    return rx.box(
        body,
        width="100%",
        style={
            # 768px 以上 (デスクトップ) では非表示
            "@media (min-width: 768px)": {"display": "none"},
            # スマホ: 親 padding/margin の隙間を詰める
            "@media (max-width: 767px)": {"marginTop": "-32px"},
        },
    )
