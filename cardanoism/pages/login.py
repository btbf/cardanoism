"""
login.py
ログインページ (/login)
"""
import reflex as rx
from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState

LINE_GREEN = "#06C755"
LINE_GREEN_DARK = "#05a847"


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
                    rx.heading("ログイン", size="5", weight="bold", text_align="center"),
                    rx.text(
                        "マイページ・お気に入り・通知機能を利用するにはログインが必要です。",
                        size="2",
                        color="var(--gray-9)",
                        text_align="center",
                        line_height="1.6",
                    ),
                    rx.divider(),
                    # LINEログインボタン
                    rx.link(
                        rx.button(
                            rx.icon("message-circle", size=20),
                            rx.text("LINEでログイン", size="3", weight="bold"),
                            width="100%",
                            size="3",
                            style={
                                "background": LINE_GREEN,
                                "color": "white",
                                "border": "none",
                                "_hover": {"background": LINE_GREEN_DARK},
                                "cursor": "pointer",
                                "justify_content": "center",
                                "gap": "10px",
                                "padding": "12px 20px",
                            },
                        ),
                        href="/auth/line/login",
                        width="100%",
                        underline="none",
                    ),
                    rx.text(
                        "今後 Google・X（Twitter）ログインにも対応予定です。",
                        size="1",
                        color="var(--gray-8)",
                        text_align="center",
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
                rx.text("← トップページに戻る", size="2", color="var(--gray-9)"),
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
