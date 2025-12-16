import reflex as rx


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

HOVER_UNDERLINE = {"backgroundSize": "100% 2px"}


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
        href="./",
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
                ),
            ),
            justify_content="space-between",
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
        background=rx.color_mode_cond(
            light="var(--rs-body)",
            dark="var(--gray-1)",
        ),
    )
