"""markdown_doc.py
JA/EN 切替の長文 markdown ページ用の共通レイアウトヘルパー。

privacy / terms / tokushoho / company 等の規約・案内ページが同じ wrapper を
重複していたので集約。max-width / margin / padding はここ 1 箇所で調整できる。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.auth_state import AuthState


def bilingual_markdown(ja: str, en: str) -> rx.Component:
    return rx.box(
        rx.cond(
            AuthState.language == "ja",
            rx.markdown(ja),
            rx.markdown(en),
        ),
        max_width="900px",
        width="100%",
        margin_x="auto",
        padding_x="16px",
        padding_y="24px",
    )
