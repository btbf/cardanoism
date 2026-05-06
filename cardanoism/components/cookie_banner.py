"""cookie_banner.py
Cookie 同意バナー + 設定モーダル UI。

template.py のレイアウト末尾で呼び出され、画面下部に sticky 表示される。
同意済みの場合は何も描画しない (rx.cond で空の rx.fragment)。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.cookie_consent_state import CookieConsentState


def _category_row(
    label_key: str,
    desc_key: str,
    *,
    locked: bool,
    checked,
    on_change=None,
) -> rx.Component:
    """カテゴリ 1 行 (タイトル + 説明 + トグル)。"""
    if locked:
        toggle_component = rx.text(
            AuthState.t["cookie_locked_label"],
            size="1",
            color="var(--gray-9)",
            style={"whiteSpace": "nowrap"},
        )
    else:
        toggle_component = rx.switch(
            checked=checked,
            on_change=on_change,
            color_scheme="amber",
        )
    return rx.hstack(
        rx.vstack(
            rx.text(AuthState.t[label_key], size="2", weight="bold", color="var(--gray-12)"),
            rx.text(
                AuthState.t[desc_key],
                size="1",
                color="var(--gray-10)",
                style={"lineHeight": "1.5"},
            ),
            spacing="1",
            align_items="start",
            style={"flex": "1 1 auto", "minWidth": "0"},
        ),
        toggle_component,
        spacing="3",
        align="center",
        width="100%",
        padding_y="8px",
    )


def _settings_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(AuthState.t["cookie_modal_title"]),
            rx.dialog.description(
                AuthState.t["cookie_modal_desc"],
                size="2",
                color="var(--gray-10)",
                style={"marginBottom": "12px"},
            ),
            rx.vstack(
                _category_row(
                    "cookie_cat_essential",
                    "cookie_cat_essential_desc",
                    locked=True,
                    checked=True,
                ),
                rx.divider(),
                _category_row(
                    "cookie_cat_functional",
                    "cookie_cat_functional_desc",
                    locked=True,
                    checked=True,
                ),
                rx.divider(),
                _category_row(
                    "cookie_cat_analytics",
                    "cookie_cat_analytics_desc",
                    locked=False,
                    checked=CookieConsentState.pending_analytics,
                    on_change=CookieConsentState.set_pending_analytics,
                ),
                spacing="0",
                align="stretch",
                width="100%",
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button(
                        AuthState.t["cookie_btn_cancel"],
                        variant="soft",
                        color_scheme="gray",
                        on_click=CookieConsentState.close_settings,
                        cursor="pointer",
                    ),
                ),
                rx.button(
                    AuthState.t["cookie_btn_save"],
                    color_scheme="amber",
                    on_click=CookieConsentState.save_settings,
                    cursor="pointer",
                ),
                rx.button(
                    AuthState.t["cookie_btn_accept_all"],
                    color_scheme="amber",
                    variant="solid",
                    on_click=CookieConsentState.accept_all,
                    cursor="pointer",
                ),
                spacing="3",
                justify="end",
                wrap="wrap",
                style={"marginTop": "16px"},
            ),
            max_width="560px",
        ),
        open=CookieConsentState.show_settings,
        on_open_change=CookieConsentState.on_settings_open_change,
    )


def _bottom_banner() -> rx.Component:
    return rx.cond(
        CookieConsentState.show_banner,
        rx.box(
            rx.box(
                rx.vstack(
                    # タイトル
                    rx.text(
                        AuthState.t["cookie_banner_title"],
                        size="3",
                        weight="bold",
                        color="var(--gray-12)",
                        style={"lineHeight": "1.3", "letterSpacing": "-0.01em"},
                    ),
                    # 説明文
                    rx.text(
                        AuthState.t["cookie_banner_desc"],
                        size="2",
                        color="var(--gray-11)",
                        style={"lineHeight": "1.65"},
                    ),
                    # プライバシーポリシーリンク (改行)
                    rx.link(
                        AuthState.t["cookie_banner_more"],
                        href="/privacy",
                        style={
                            "fontSize": "13px",
                            "color": "var(--gray-12)",
                            "textDecoration": "underline",
                            "textUnderlineOffset": "2px",
                            "textDecorationColor": "var(--gray-7)",
                            "width": "fit-content",
                        },
                        _hover={
                            "textDecorationColor": "var(--gray-11)",
                        },
                    ),
                    # アクションボタン
                    rx.flex(
                        rx.el.button(
                            rx.text(
                                AuthState.t["cookie_btn_settings"],
                                size="2",
                                weight="medium",
                            ),
                            on_click=CookieConsentState.open_settings,
                            style={
                                "padding": "8px 14px",
                                "border": "none",
                                "background": "transparent",
                                "color": "var(--gray-11)",
                                "cursor": "pointer",
                                "borderRadius": "8px",
                                "transition": "background 0.15s, color 0.15s",
                            },
                            _hover={
                                "background": rx.color("gray", 3),
                                "color": "var(--gray-12)",
                            },
                        ),
                        rx.el.button(
                            rx.text(
                                AuthState.t["cookie_btn_reject"],
                                size="2",
                                weight="medium",
                            ),
                            on_click=CookieConsentState.reject_non_essential,
                            style={
                                "padding": "8px 16px",
                                "background": "transparent",
                                "color": "var(--gray-12)",
                                "cursor": "pointer",
                                "borderRadius": "8px",
                                "border": f"1px solid {rx.color('gray', 6)}",
                                "transition": "background 0.15s, border-color 0.15s",
                            },
                            _hover={
                                "background": rx.color("gray", 3),
                                "borderColor": rx.color("gray", 7),
                            },
                        ),
                        rx.el.button(
                            rx.text(
                                AuthState.t["cookie_btn_accept_all"],
                                size="2",
                                weight="bold",
                            ),
                            on_click=CookieConsentState.accept_all,
                            style={
                                "padding": "8px 18px",
                                "background": rx.color("amber", 9),
                                "color": "var(--gray-12)",
                                "cursor": "pointer",
                                "borderRadius": "8px",
                                "border": f"1px solid {rx.color('amber', 9)}",
                                "transition": "background 0.15s, transform 0.1s",
                                "fontWeight": "600",
                                "boxShadow": f"0 1px 2px {rx.color('amber', 6)}",
                            },
                            _hover={
                                "background": rx.color("amber", 10),
                            },
                            _active={"transform": "translateY(1px)"},
                        ),
                        spacing="2",
                        wrap="wrap",
                        justify="end",
                        align="center",
                        width="100%",
                        style={"marginTop": "4px"},
                    ),
                    spacing="3",
                    align_items="stretch",
                    width="100%",
                ),
                # カード本体
                padding="20px 22px",
                border_radius="16px",
                background=rx.color_mode_cond(
                    "rgba(255, 255, 255, 0.98)",
                    "rgba(28, 28, 32, 0.98)",
                ),
                border=f"1px solid {rx.color('gray', 5)}",
                style={
                    "backdropFilter": "blur(12px)",
                    "boxShadow": rx.color_mode_cond(
                        "0 12px 32px -8px rgba(15, 23, 42, 0.18), 0 4px 12px -4px rgba(15, 23, 42, 0.10)",
                        "0 12px 32px -8px rgba(0, 0, 0, 0.6), 0 4px 12px -4px rgba(0, 0, 0, 0.4)",
                    ),
                    "borderTop": f"3px solid {rx.color('amber', 9)}",
                    "animation": "cookie-banner-in 0.35s cubic-bezier(0.16, 1, 0.3, 1)",
                },
                width="100%",
                max_width="520px",
            ),
            # 固定ポジション (下中央 / モバイルは下部いっぱい)
            position="fixed",
            bottom=["12px", "16px", "24px"],
            left=["12px", "16px", "auto"],
            right=["12px", "16px", "24px"],
            z_index="9000",
            style={
                "@keyframes cookie-banner-in": (
                    "from { opacity: 0; transform: translateY(20px); }"
                    "to   { opacity: 1; transform: translateY(0); }"
                ),
            },
        ),
        rx.fragment(),
    )


def cookie_banner() -> rx.Component:
    """画面共通の Cookie 同意バナー + 設定モーダルをまとめて返す。"""
    return rx.fragment(
        _bottom_banner(),
        _settings_modal(),
    )


def cookie_settings_link(label_key: str = "nav_cookie_settings") -> rx.Component:
    """フッター用「Cookie 設定」リンク。クリックでモーダルを開く。"""
    return rx.text(
        AuthState.t[label_key],
        on_click=CookieConsentState.open_settings,
        style={
            "fontSize": "13px",
            "color": "var(--gray-10)",
            "cursor": "pointer",
            "textDecoration": "none",
        },
        _hover={"color": "var(--gray-12)", "textDecoration": "underline"},
    )
