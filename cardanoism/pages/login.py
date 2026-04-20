"""
login.py
ログインページ (/login)
"""
import reflex as rx
from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from typing import Any

X_BLACK = "#000000"
X_BLACK_DARK = "#333333"

def _google_svg_icon() -> rx.Component:
    return rx.el.svg(
        rx.el.path(fill="#EA4335", d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"),
        rx.el.path(fill="#4285F4", d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"),
        rx.el.path(fill="#FBBC05", d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"),
        rx.el.path(fill="#34A853", d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"),
        view_box="0 0 48 48",
        style={"display": "block", "width": "20px", "height": "20px", "flex-shrink": "0"},
    )


def google_login_button(href: str, label: Any = None) -> rx.Component:
    """Google公式デザイン（ピル型）のログインボタン。"""
    return rx.el.a(
        _google_svg_icon(),
        rx.el.span(
            label if label is not None else AuthState.t["login_google"],
            style={
                "font-family": "'Roboto', 'Google Sans', Arial, sans-serif",
                "font-weight": "500",
                "font-size": "14px",
                "line-height": "20px",
                "letter-spacing": "0.25px",
                "color": rx.color_mode_cond("#1f1f1f", "#e3e3e3"),
            },
        ),
        href=href,
        style={
            "display": "flex",
            "align-items": "center",
            "justify-content": "center",
            "gap": "12px",
            "width": "100%",
            "height": "44px",
            "padding": "0 16px",
            "background-color": rx.color_mode_cond("#ffffff", "#131314"),
            "border": rx.color_mode_cond("1px solid #747775", "1px solid #8e918f"),
            "border-radius": "22px",
            "box-sizing": "border-box",
            "text-decoration": "none",
            "cursor": "pointer",
            "transition": "box-shadow .218s",
            "overflow": "hidden",
            "_hover": {
                "box-shadow": rx.color_mode_cond(
                    "0 1px 2px 0 rgba(60,64,67,.30), 0 1px 3px 1px rgba(60,64,67,.15)",
                    "0 1px 2px 0 rgba(0,0,0,.60), 0 1px 3px 1px rgba(0,0,0,.30)",
                ),
            },
        },
    )


def line_login_button(href: str, label: Any = None) -> rx.Component:
    """LINE公式ガイドライン準拠のログインボタン。"""
    return rx.el.a(
        rx.el.span(
            rx.el.img(src="/line-icon.png", alt="LINE", style={"width": "32px", "height": "32px", "object-fit": "contain"}),
            style={
                "display": "flex",
                "align-items": "center",
                "justify-content": "center",
                "padding": "0 14px",
                "border-right": "1px solid rgba(255,255,255,0.3)",
                "height": "100%",
                "flex-shrink": "0",
            },
        ),
        rx.el.span(
            label if label is not None else AuthState.t["login_line"],
            style={
                "flex": "1",
                "text-align": "center",
                "font-size": "15px",
                "font-weight": "700",
                "letter-spacing": "0.02em",
                "color": "white",
            },
        ),
        href=href,
        style={
            "display": "flex",
            "align-items": "center",
            "width": "100%",
            "height": "44px",
            "background": "#06C755",
            "border-radius": "5px",
            "text-decoration": "none",
            "overflow": "hidden",
            "cursor": "pointer",
            "transition": "filter 0.15s ease",
            "_hover": {"filter": "brightness(0.9)"},
            "_active": {"filter": "brightness(0.7)"},
        },
    )


def login_error_message() -> rx.Component:
    """URLパラメータにerrorがある場合にエラーメッセージを表示。"""
    error_map = {
        "line_denied": "LINEログインがキャンセルされました。",
        "invalid_state": "セキュリティエラーが発生しました。もう一度お試しください。",
        "state_mismatch": "セキュリティエラーが発生しました。もう一度お試しください。",
        "token_error": "LINEとの認証に失敗しました。もう一度お試しください。",
        "profile_error": "LINEプロフィールの取得に失敗しました。",
        "db_error": "サーバーエラーが発生しました。しばらく後にお試しください。",
        "session_error": "セッションの作成に失敗しました。",
    }
    return rx.box()


@template(route="/login", title="ログイン | Cardanoism")
def login_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            # ロゴ
            rx.link(
                rx.image(
                    src=rx.color_mode_cond(
                        light="/cardanoism-new-logo-light.png",
                        dark="/cardanoism-new-logo-dark.png",
                    ),
                    height="36px",
                    width="auto",
                    alt="Cardanoism",
                ),
                href="/",
            ),
            # カード
            rx.box(
                rx.vstack(
                    rx.heading(AuthState.t["login_page_title"], size="5", weight="bold", text_align="center"),
                    rx.text(
                        AuthState.t["login_page_desc"],
                        size="2",
                        color="var(--gray-9)",
                        text_align="center",
                        line_height="1.6",
                    ),
                    rx.divider(),
                    line_login_button("/auth/line/login"),
                    google_login_button("/auth/google/login"),
                    rx.link(
                        rx.button(
                            rx.image(src="/x-icon.svg", width="18px", height="18px", alt="X"),
                            rx.text(AuthState.t["login_x"], size="3", weight="bold"),
                            width="100%",
                            size="3",
                            style={
                                "background": X_BLACK,
                                "color": "white",
                                "border": "none",
                                "_hover": {"background": X_BLACK_DARK},
                                "cursor": "pointer",
                                "justify_content": "center",
                                "gap": "10px",
                                "padding": "12px 20px",
                            },
                        ),
                        href="/auth/twitter/login",
                        width="100%",
                        underline="none",
                    ),
                    spacing="4",
                    width="100%",
                    align="center",
                ),
                padding="32px",
                border_radius="16px",
                background=rx.color_mode_cond("white", "rgba(15,15,25,0.92)"),
                border=f"1px solid {rx.color('gray', 5)}",
                box_shadow="0 8px 32px -12px rgba(0,0,0,0.12)",
                width="100%",
                max_width="400px",
            ),
            rx.link(
                rx.text(AuthState.t["login_back_to_top"], size="2", color="var(--gray-9)"),
                href="/",
                underline="none",
            ),
            spacing="6",
            align="center",
            width="100%",
            max_width="400px",
        ),
        min_height="70vh",
        width="100%",
        padding_x="16px",
    )
