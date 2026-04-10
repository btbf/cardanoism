import reflex as rx
from cardanoism.backend.auth_state import AuthState


UNDERLINE_STYLE = {
    "textDecoration": "none",
    "display": "inline-block",
    "backgroundImage": "linear-gradient(currentColor, currentColor)",
    "backgroundSize": "0% 2px",
    "backgroundPosition": "0 100%",
    "backgroundRepeat": "no-repeat",
    "transition": "background-size 0.2s ease",
    "paddingBottom": "2px",
}

HOVER_UNDERLINE = {"backgroundSize": "100% 2px", "backgroundColor": "unset"}


def navbar_icons_item(text: str, url: str, disabled: bool) -> rx.Component:
    disabled_style = {"pointerEvents": "none", "opacity": "0.6"} if disabled else {}
    return rx.link(
        rx.text(text, size="4", weight="medium", color="var(--gray-12)"),
        href=url,
        style=UNDERLINE_STYLE | disabled_style,
        _hover=HOVER_UNDERLINE,
    )


def navbar_icons() -> rx.Component:
    logo = rx.link(
        rx.image(
            src=rx.color_mode_cond(
                light="/cardanoism-new-logo-light.png",
                dark="/cardanoism-new-logo-dark.png",
            ),
            width="15em",
            height="auto",
            alt="カルダノイズム",
        ),
        href="/",
    )

    auth_area = rx.cond(
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
                ),
            ),
            rx.menu.content(
                rx.menu.item(rx.link("マイページ", href="/mypage", width="100%", underline="none")),
                rx.menu.separator(),
                rx.menu.item(rx.text("ログアウト", color="var(--red-9)", on_click=AuthState.logout, cursor="pointer", width="100%")),
            ),
        ),
        rx.link(
            rx.button(
                "ログイン",
                size="2",
                variant="soft",
                cursor="pointer",
            ),
            href="/login",
            underline="none",
        ),
    )

    desktop_nav = rx.desktop_only(
        rx.hstack(
            logo,
            rx.hstack(
                navbar_icons_item("ホーム", "/", False),
                rx.menu.root(
                    rx.menu.trigger(
                        rx.button(
                            rx.text("カタリスト", size="4", weight="medium", color="var(--gray-12)"),
                            weight="medium",
                            variant="ghost",
                            size="3",
                            style=UNDERLINE_STYLE,
                            _hover=HOVER_UNDERLINE,
                            _active={"background_color": "unset"},
                            cursor="pointer",
                        ),
                    ),
                    rx.menu.content(
                        rx.menu.item(
                            rx.link(
                                rx.text("提案一覧", size="3", weight="medium", color="var(--gray-12)"),
                                href="/catalyst",
                                width="100%",
                                underline="none"
                            ),
                        ),
                        rx.menu.item(
                            rx.link(
                                rx.text("ファンド一覧", size="3", weight="medium", color="var(--gray-12)"),
                                href="/catalyst/funds",
                                width="100%",
                                underline="none"
                            ),
                        ),
                    ),
                ),
                navbar_icons_item("ガバナンス", "/#", True),
                auth_area,
                spacing="6",
                padding_right="5px",
            ),
            justify_content="space-between",
            align_items="center",
            max_width="1130px",
            margin_x="auto",
        ),
    )

    mobile_nav = rx.mobile_and_tablet(
        rx.hstack(
            logo,
            rx.hstack(
                auth_area,
                rx.menu.root(
                    rx.menu.trigger(rx.icon("menu", size=30)),
                    rx.menu.content(
                        navbar_icons_item("ホーム", "/", False),
                        rx.menu.root(
                            rx.menu.trigger(
                                rx.button(
                                    rx.text("カタリスト", size="4", weight="medium", color="var(--gray-12)"),
                                    rx.icon("chevron-down"),
                                    weight="medium",
                                    variant="ghost",
                                    size="3",
                                ),
                            ),
                            rx.menu.content(
                                rx.menu.item(
                                    rx.link(
                                        rx.text("提案一覧", size="3", weight="medium", color="var(--gray-12)"),
                                        href="/catalyst",
                                        width="100%",
                                    ),
                                ),
                                rx.menu.item(
                                    rx.link(
                                        rx.text("ファンド一覧", size="3", weight="medium", color="var(--gray-12)"),
                                        href="/catalyst/funds",
                                        width="100%",
                                    ),
                                ),
                            ),
                        ),
                        navbar_icons_item("ガバナンス", "/#", True),
                        rx.cond(
                            AuthState.is_logged_in,
                            rx.fragment(
                                rx.menu.separator(),
                                rx.menu.item(rx.link("マイページ", href="/mypage", width="100%", underline="none")),
                                rx.menu.item(rx.text("ログアウト", color="var(--red-9)", on_click=AuthState.logout, cursor="pointer", width="100%")),
                            ),
                            rx.menu.item(rx.link("ログイン", href="/login", width="100%", underline="none")),
                        ),
                    ),
                ),
                spacing="3",
                align="center",
            ),
            justify_content="space-between",
            align="center",
        ),
    )

    return rx.box(
        desktop_nav,
        mobile_nav,
        padding_x="1em",
        padding_y="1em",
        justify="center",
        position="fixed",
        z_index="500",
        width="100%",
        background_color="var(--gray-1)",
    )
