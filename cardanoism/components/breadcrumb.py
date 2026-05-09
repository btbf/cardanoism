"""breadcrumb.py
パンくずリストの共通コンポーネント。

各ページの `_breadcrumb()` 関数が
「home icon → chevron → 中間リンク群 → chevron → 現在地テキスト」
の同型コピペになっていたため集約。

Usage:
    breadcrumb([
        ("nav_governance", "/governance"),     # 中間リンク (i18n key, href)
    ], current_key="gov_subnav_why")           # 現在地 (i18n key)

home (`/`) は自動で先頭に挿入される。
"""
from __future__ import annotations

from typing import Iterable

import reflex as rx

from cardanoism.backend.auth_state import AuthState


def _chevron() -> rx.Component:
    return rx.icon("chevron-right", size=14, color="gray")


def breadcrumb(intermediate: Iterable[tuple[str, str]], current_key: str) -> rx.Component:
    """home → 中間リンク群 → 現在地 のパンくずを生成する。

    Args:
        intermediate: (i18n_key, href) の列。中間リンク群。
        current_key:  現在地として表示する i18n key (リンクではないテキスト)。
    """
    children: list[rx.Component] = [
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
    ]
    for key, href in intermediate:
        children.append(_chevron())
        children.append(
            rx.link(
                AuthState.t[key], href=href,
                size="2", underline="hover", color_scheme="gray",
            )
        )
    children.append(_chevron())
    children.append(rx.text(AuthState.t[current_key], size="2", weight="medium"))
    return rx.hstack(
        *children,
        spacing="2", align="center", width="100%", padding_top="15px",
    )
