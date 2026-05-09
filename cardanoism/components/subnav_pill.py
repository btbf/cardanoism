"""subnav_pill.py
ピル型サブナビの共通描画ヘルパー。

governance_nav / staking_nav が同じ意匠の `_pill()` を別々に持っていたため
集約。新しいサブナビを追加するときは items リストだけ書けばよい。
"""
from __future__ import annotations

from typing import Iterable

import reflex as rx


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


def pill_subnav(active: str, items: Iterable[tuple]) -> rx.Component:
    """ピル型サブナビを描画する。

    Args:
        active: アクティブな key (各 item の最初の要素と一致するもの)
        items: タプル (key, label, href, icon) のシーケンス
    """
    return rx.hstack(
        *[_pill(label, href, icon, key == active) for key, label, href, icon in items],
        spacing="2",
        wrap="wrap",
        width="100%",
        padding_y="8px",
    )
