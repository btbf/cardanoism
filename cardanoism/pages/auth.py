"""
auth.py
LINE OAuth フロー用 Reflex ページ

/auth/line/login    → LINE認証ページへリダイレクト
/auth/line/callback → LINE認証コールバック処理
/auth/logout        → ログアウト
"""
import reflex as rx
from cardanoism.backend.auth_state import AuthState


@rx.page(route="/auth/line/login", on_load=[AuthState.detect_browser_language, AuthState.start_line_login])
def line_login_redirect() -> rx.Component:
    """LINEへのリダイレクト中に表示するローディング画面。"""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(AuthState.t["auth_connecting_line"], size="3", color="var(--gray-9)"),
            spacing="3",
            align="center",
        ),
        min_height="100vh",
    )


@rx.page(route="/auth/line/callback", on_load=[AuthState.detect_browser_language, AuthState.handle_line_callback])
def line_callback() -> rx.Component:
    """LINEコールバック処理中のローディング画面。"""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(AuthState.t["auth_processing_login"], size="3", color="var(--gray-9)"),
            rx.cond(
                AuthState.auth_error != "",
                rx.text(AuthState.auth_error, size="2", color="var(--red-9)"),
                rx.box(),
            ),
            spacing="3",
            align="center",
        ),
        min_height="100vh",
    )


@rx.page(route="/auth/line/connect", on_load=[AuthState.detect_browser_language, AuthState.start_line_connect])
def line_connect_redirect() -> rx.Component:
    """LINE通知連携用OAuthへのリダイレクト画面。"""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(AuthState.t["auth_connecting_line"], size="3", color="var(--gray-9)"),
            spacing="3",
            align="center",
        ),
        min_height="100vh",
    )


@rx.page(route="/auth/google/login", on_load=[AuthState.detect_browser_language, AuthState.start_google_login])
def google_login_redirect() -> rx.Component:
    """Googleへのリダイレクト中に表示するローディング画面。"""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(AuthState.t["auth_connecting_google"], size="3", color="var(--gray-9)"),
            spacing="3",
            align="center",
        ),
        min_height="100vh",
    )


@rx.page(route="/auth/google/callback", on_load=[AuthState.detect_browser_language, AuthState.handle_google_callback])
def google_callback() -> rx.Component:
    """Googleコールバック処理中のローディング画面。"""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(AuthState.t["auth_processing_login"], size="3", color="var(--gray-9)"),
            rx.cond(
                AuthState.auth_error != "",
                rx.text(AuthState.auth_error, size="2", color="var(--red-9)"),
                rx.box(),
            ),
            spacing="3",
            align="center",
        ),
        min_height="100vh",
    )


@rx.page(route="/auth/twitter/login", on_load=[AuthState.detect_browser_language, AuthState.start_twitter_login])
def twitter_login_redirect() -> rx.Component:
    """X(Twitter)へのリダイレクト中に表示するローディング画面。"""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(AuthState.t["auth_connecting_x"], size="3", color="var(--gray-9)"),
            spacing="3",
            align="center",
        ),
        min_height="100vh",
    )


@rx.page(route="/auth/twitter/callback", on_load=[AuthState.detect_browser_language, AuthState.handle_twitter_callback])
def twitter_callback() -> rx.Component:
    """X(Twitter)コールバック処理中のローディング画面。"""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(AuthState.t["auth_processing_login"], size="3", color="var(--gray-9)"),
            rx.cond(
                AuthState.auth_error != "",
                rx.text(AuthState.auth_error, size="2", color="var(--red-9)"),
                rx.box(),
            ),
            spacing="3",
            align="center",
        ),
        min_height="100vh",
    )


@rx.page(route="/auth/logout", on_load=[AuthState.detect_browser_language, AuthState.logout])
def logout_page() -> rx.Component:
    """ログアウト処理中のローディング画面。"""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text(AuthState.t["auth_processing_logout"], size="3", color="var(--gray-9)"),
            spacing="3",
            align="center",
        ),
        min_height="100vh",
    )
