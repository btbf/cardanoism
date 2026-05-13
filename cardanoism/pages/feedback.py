"""feedback.py
ベータ期間中のフィードバック収集ページ (/feedback)

Google Form への誘導が役割。ログイン必須にし、user_id と username を
prefill 用クエリパラメータに乗せて Google Form を新タブで開く。

環境変数:
  FEEDBACK_FORM_URL              : Google Form の viewform URL
  FEEDBACK_FORM_USER_ID_ENTRY    : 例 entry.123456 (user_id を埋める短答 ID)
  FEEDBACK_FORM_USERNAME_ENTRY   : 例 entry.789012 (username を埋める短答 ID)

未設定の場合はセットアップ案内を表示する。
"""
from __future__ import annotations

import os

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState


FORM_URL = os.getenv("FEEDBACK_FORM_URL", "").strip()
USER_ID_ENTRY = os.getenv("FEEDBACK_FORM_USER_ID_ENTRY", "").strip()
USERNAME_ENTRY = os.getenv("FEEDBACK_FORM_USERNAME_ENTRY", "").strip()
FORM_CONFIGURED = bool(FORM_URL and USER_ID_ENTRY)


ACCENT = "#ffcf00"
ACCENT_DARK = "#c7a300"
TEXT_MUTED = "var(--gray-10)"


def _prefilled_url():
    """ログイン中ユーザの user_id / username を prefill した Google Form URL を生成。"""
    base = FORM_URL + "?" + USER_ID_ENTRY + "=" + AuthState.user_id.to(str)
    if USERNAME_ENTRY:
        base = base + "&" + USERNAME_ENTRY + "=" + AuthState.username
    return base


def _hero() -> rx.Component:
    return rx.vstack(
        rx.text(
            AuthState.t["feedback_kicker"],
            size="2",
            weight="bold",
            color=ACCENT_DARK,
            letter_spacing="0.14em",
        ),
        rx.heading(
            AuthState.t["feedback_title"],
            as_="h1",
            size={"base": "6", "md": "8"},
            weight="bold",
            line_height="1.2",
        ),
        rx.text(
            AuthState.t["feedback_subtitle"],
            size={"base": "2", "md": "3"},
            color=TEXT_MUTED,
            line_height="1.7",
            max_width="640px",
        ),
        spacing="3",
        align_items="start",
        width="100%",
    )


def _benefit_card() -> rx.Component:
    """ベータ協力者特典の案内カード。"""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon(tag="gift", color=ACCENT_DARK, size=22),
                rx.heading(
                    AuthState.t["feedback_benefit_title"],
                    size="4",
                    weight="bold",
                ),
                spacing="3",
                align="center",
            ),
            rx.text(
                AuthState.t["feedback_benefit_body"],
                size="3",
                color=TEXT_MUTED,
                line_height="1.7",
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding="20px",
        border_radius="12px",
        background_color="var(--amber-2)",
        border="1px solid var(--amber-6)",
        width="100%",
    )


def _logged_in_cta() -> rx.Component:
    """ログイン済み: Google Form へのリンクボタン。"""
    return rx.vstack(
        rx.text(
            AuthState.t["feedback_cta_lead"],
            size="3",
            color=TEXT_MUTED,
        ),
        rx.link(
            rx.button(
                rx.hstack(
                    rx.text(AuthState.t["feedback_open_form"], weight="bold"),
                    rx.icon(tag="external_link", size=16),
                    spacing="2",
                    align="center",
                ),
                size="3",
                style={
                    "background": ACCENT,
                    "color": "#1a1a1a",
                    "cursor": "pointer",
                    "_hover": {"background": ACCENT_DARK, "color": "#ffffff"},
                },
            ),
            href=_prefilled_url(),
            is_external=True,
            target="_blank",
            underline="none",
        ),
        rx.text(
            AuthState.t["feedback_form_note"],
            size="1",
            color=TEXT_MUTED,
        ),
        spacing="3",
        align_items="start",
        width="100%",
    )


def _login_prompt() -> rx.Component:
    """未ログイン: ログイン誘導。"""
    return rx.vstack(
        rx.text(
            AuthState.t["feedback_login_required"],
            size="3",
            color=TEXT_MUTED,
            line_height="1.7",
        ),
        rx.button(
            AuthState.t["feedback_login_button"],
            size="3",
            on_click=AuthState.open_login_modal,
            style={
                "background": ACCENT,
                "color": "#1a1a1a",
                "cursor": "pointer",
                "_hover": {"background": ACCENT_DARK, "color": "#ffffff"},
            },
        ),
        spacing="3",
        align_items="start",
        width="100%",
    )


def _not_configured() -> rx.Component:
    """環境変数未設定時のフォールバック表示。"""
    return rx.callout(
        AuthState.t["feedback_not_configured"],
        icon="triangle_alert",
        color_scheme="amber",
        width="100%",
    )


@template(route="/feedback", title="フィードバック | Cardanoism")
def feedback_page() -> rx.Component:
    if not FORM_CONFIGURED:
        body = _not_configured()
    else:
        body = rx.cond(
            AuthState.is_logged_in,
            _logged_in_cta(),
            _login_prompt(),
        )

    return rx.box(
        rx.vstack(
            _hero(),
            _benefit_card(),
            body,
            spacing="6",
            align_items="start",
            max_width="720px",
            margin_x="auto",
            padding_x=["0px", "28px", "40px"],
            padding_y=["32px", "44px", "56px"],
            width="100%",
        ),
        width="100%",
        max_width="100%",
    )
