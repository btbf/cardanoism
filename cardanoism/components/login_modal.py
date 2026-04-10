"""
login_modal.py
サイト全体で使えるログインモーダルコンポーネント
"""
import reflex as rx
from cardanoism.backend.auth_state import AuthState

LINE_GREEN = "#06C755"
LINE_GREEN_DARK = "#05a847"


def login_modal() -> rx.Component:
    """ログインモーダル。AuthState.show_login_modal が True のとき表示。"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title(
                    rx.hstack(
                        rx.image(
                            src="/cardanoism-new-logo-light.png",
                            height="28px",
                            width="auto",
                            alt="Cardanoism",
                        ),
                        justify="center",
                        width="100%",
                    )
                ),
                rx.dialog.description(
                    rx.text(
                        "ログインしてマイページ・お気に入り・通知機能を利用できます。",
                        size="2",
                        color="var(--gray-9)",
                        text_align="center",
                    )
                ),
                rx.vstack(
                    rx.link(
                        rx.button(
                            rx.icon("message-circle", size=18),
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
                                "gap": "8px",
                            },
                        ),
                        href="/auth/line/login",
                        width="100%",
                        underline="none",
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.dialog.close(
                    rx.button(
                        "閉じる",
                        variant="ghost",
                        size="2",
                        color="var(--gray-9)",
                        cursor="pointer",
                        on_click=AuthState.close_login_modal,
                    ),
                ),
                spacing="5",
                align="center",
                width="100%",
                padding="8px",
            ),
            max_width="380px",
        ),
        open=AuthState.show_login_modal,
        on_open_change=AuthState.close_login_modal,
    )
