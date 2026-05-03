import reflex as rx
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.fiat_state import FiatRateState
from cardanoism.backend.wallet_state import WalletState
from cardanoism.components.wallet_button import (
    wallet_connector_mount,
    wallet_status,
)

ACCENT = "#ffcf00"
ACCENT_DARK = "#c7a300"

_PILL = {
    "textDecoration": "none",
    "display": "inline-flex",
    "alignItems": "center",
    "padding": "5px 12px",
    "borderRadius": "9999px",
    "fontWeight": "500",
    "fontSize": "16px",
    "color": "var(--gray-11)",
    "transition": "background 0.15s, color 0.15s",
    "cursor": "pointer",
}
_PILL_HOVER = {
    "backgroundColor": "var(--gray-a3)",
    "color": "var(--gray-12)",
    "textDecoration": "none",
}


def fiat_rates_pill() -> rx.Component:
    """ナビバー内の ADA レート表示。
    言語 (AuthState.language) に連動して JA → ADA/JPY、EN → ADA/USD を表示する。
    """
    label_style = {"color": "var(--gray-9)", "fontSize": "11px", "fontWeight": "600", "letterSpacing": "0.02em"}
    value_style = {"color": "var(--gray-12)", "fontSize": "13px", "fontWeight": "700"}
    return rx.hstack(
        rx.cond(
            AuthState.language == "ja",
            rx.fragment(
                rx.el.span("ADA/JPY", style=label_style),
                rx.el.span(FiatRateState.ada_jpy, style=value_style),
            ),
            rx.fragment(
                rx.el.span("ADA/USD", style=label_style),
                rx.el.span(FiatRateState.ada_usd, style=value_style),
            ),
        ),
        rx.cond(
            FiatRateState.updated_label != "",
            rx.el.span(
                "(", FiatRateState.updated_label, ")",
                style={"color": "var(--gray-9)", "fontSize": "11px", "marginLeft": "4px"},
            ),
            rx.fragment(),
        ),
        spacing="2",
        align="center",
        padding="4px 12px",
        background=rx.color_mode_cond("var(--gray-2)", "var(--gray-3)"),
        border_radius="9999px",
        style={"whiteSpace": "nowrap"},
    )


def lang_toggle() -> rx.Component:
    btn_base = {
        "borderRadius": "9999px",
        "fontSize": "13px",
        "fontWeight": "700",
        "cursor": "pointer",
        "padding": "3px 9px",
        "border": "none",
        "transition": "background 0.15s, color 0.15s",
        "lineHeight": "1.5",
    }
    active = {
        **btn_base,
        "background": ACCENT,
        "color": "#111",
    }
    inactive = {
        **btn_base,
        "background": "transparent",
        "color": "var(--gray-10)",
    }
    return rx.hstack(
        rx.el.button(
            "JA",
            on_click=AuthState.set_language("ja"),
            style=rx.cond(AuthState.language == "ja", active, inactive),
        ),
        rx.el.button(
            "EN",
            on_click=AuthState.set_language("en"),
            style=rx.cond(AuthState.language == "en", active, inactive),
        ),
        spacing="0",
        padding="3px",
        background=rx.color_mode_cond("var(--gray-4)", "var(--gray-5)"),
        border_radius="9999px",
        align="center",
    )


def nav_pill(text, url: str, disabled: bool = False) -> rx.Component:
    style = {**_PILL, **({"opacity": "0.4", "pointerEvents": "none"} if disabled else {})}
    return rx.link(
        rx.text(text, size="3", weight="medium"),
        href=url,
        style=style,
        _hover=_PILL_HOVER,
    )


def auth_section() -> rx.Component:
    return rx.cond(
        AuthState.is_logged_in,
        rx.menu.root(
            rx.menu.trigger(
                rx.button(
                    rx.cond(
                        AuthState.avatar_url != "",
                        rx.avatar(src=AuthState.avatar_url, size="2", radius="full"),
                        rx.avatar(fallback=AuthState.username[:1], size="2", radius="full"),
                    ),
                    variant="ghost",
                    cursor="pointer",
                    padding="0",
                    border_radius="full",
                    style={"outline": "2px solid transparent", "transition": "outline-color 0.15s"},
                    _hover={"outline": f"2px solid {ACCENT}"},
                ),
            ),
            rx.menu.content(
                rx.menu.item(
                    rx.hstack(rx.icon("user", size=14), rx.text(AuthState.t["nav_mypage"], size="3"), spacing="2"),
                    on_click=rx.redirect("/mypage"),
                    cursor="pointer",
                ),
                rx.menu.separator(),
                rx.menu.item(
                    rx.hstack(rx.icon("log-out", size=14), rx.text(AuthState.t["nav_logout"], size="3"), spacing="2"),
                    color_scheme="red",
                    on_click=AuthState.logout,
                    cursor="pointer",
                ),
            ),
        ),
        rx.link(
            rx.button(
                AuthState.t["nav_login"],
                size="3",
                border_radius="9999px",
                cursor="pointer",
                style={
                    "background": f"linear-gradient(135deg, {ACCENT}, {ACCENT_DARK})",
                    "color": "#111",
                    "fontWeight": "700",
                    "border": "none",
                    "transition": "opacity 0.15s, box-shadow 0.15s",
                    "_hover": {
                        "opacity": "0.88",
                        "boxShadow": "0 2px 10px rgba(255,207,0,0.4)",
                    },
                },
            ),
            href="/login",
            underline="none",
        ),
    )


def navbar_icons() -> rx.Component:
    logo = rx.link(
        rx.image(
            src=rx.color_mode_cond(
                light="/cardanoism-new-logo-light.png",
                dark="/cardanoism-new-logo-dark.png",
            ),
            width="13em",
            height="auto",
            alt="カルダノイズム",
        ),
        href="/",
    )

    divider = rx.box(
        width="1px",
        height="18px",
        background=rx.color_mode_cond("var(--gray-5)", "var(--gray-6)"),
        flex_shrink="0",
    )

    desktop_nav = rx.desktop_only(
        rx.hstack(
            logo,
            divider,
            rx.hstack(
                nav_pill(AuthState.t["nav_home"], "/"),
                nav_pill(AuthState.t["nav_governance"], "/governance"),
                nav_pill(AuthState.t["nav_staking"], "/staking"),
                nav_pill(AuthState.t["nav_catalyst"], "/catalyst"),
                spacing="1",
                align="center",
            ),
            rx.box(flex="1"),
            rx.hstack(
                fiat_rates_pill(),
                divider,
                lang_toggle(),
                divider,
                rx.cond(
                    WalletState.connected,
                    rx.hstack(
                        wallet_status(),
                        divider,
                        spacing="3",
                        align="center",
                    ),
                    rx.fragment(),
                ),
                auth_section(),
                spacing="3",
                align="center",
            ),
            align_items="center",
            max_width="1130px",
            margin_x="auto",
            width="100%",
            spacing="4",
        ),
    )

    mobile_nav = rx.mobile_and_tablet(
        rx.hstack(
            logo,
            rx.hstack(
                auth_section(),
                rx.menu.root(
                    rx.menu.trigger(
                        rx.box(
                            rx.icon("menu", size=20, color="var(--gray-11)"),
                            padding="6px 8px",
                            border_radius="8px",
                            cursor="pointer",
                            background=rx.color_mode_cond("var(--gray-3)", "var(--gray-4)"),
                            _hover={"background": rx.color_mode_cond("var(--gray-4)", "var(--gray-5)")},
                            style={"transition": "background 0.15s", "display": "inline-flex", "alignItems": "center"},
                        ),
                    ),
                    rx.menu.content(
                        rx.menu.item(
                            rx.link(AuthState.t["nav_home"], href="/", width="100%", underline="none", color="var(--gray-12)"),
                        ),
                        rx.menu.item(
                            rx.link(AuthState.t["nav_governance"], href="/governance", width="100%", underline="none", color="var(--gray-12)"),
                        ),
                        rx.menu.item(
                            rx.link(AuthState.t["nav_staking"], href="/staking", width="100%", underline="none", color="var(--gray-12)"),
                        ),
                        rx.menu.item(
                            rx.link(AuthState.t["nav_catalyst"], href="/catalyst", width="100%", underline="none", color="var(--gray-12)"),
                        ),
                        rx.menu.separator(),
                        rx.menu.item(lang_toggle()),
                        rx.cond(
                            AuthState.is_logged_in,
                            rx.fragment(
                                rx.menu.separator(),
                                rx.menu.item(rx.link(AuthState.t["nav_mypage"], href="/mypage", width="100%", underline="none", color="var(--gray-12)")),
                                rx.menu.item(rx.text(AuthState.t["nav_logout"], size="3", color="var(--red-9)", on_click=AuthState.logout, cursor="pointer", width="100%")),
                            ),
                            rx.menu.item(rx.link(AuthState.t["nav_login"], href="/login", width="100%", underline="none", color="var(--gray-12)")),
                        ),
                    ),
                ),
                spacing="2",
                align="center",
            ),
            justify_content="space-between",
            align="center",
            width="100%",
        ),
    )

    return rx.box(
        # 不可視: ウォレット接続 React 本体 (auto_reconnect / イベント橋渡しのため常時マウント)
        wallet_connector_mount(),
        desktop_nav,
        mobile_nav,
        padding_x="1.5em",
        padding_y="0.8em",
        position="fixed",
        z_index="500",
        width="100%",
        background=rx.color_mode_cond(
            "rgba(255,255,255,0.80)",
            "rgba(11,11,17,0.80)",
        ),
        style={
            "backdropFilter": "blur(16px)",
            "WebkitBackdropFilter": "blur(16px)",
            "borderBottom": rx.color_mode_cond(
                "1px solid rgba(0,0,0,0.07)",
                "1px solid rgba(255,255,255,0.07)",
            ),
        },
    )
