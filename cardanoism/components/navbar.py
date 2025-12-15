import reflex as rx


UNDERLINE_STYLE = {
    "color": "var(--color-text-100)",
    "textDecoration": "none",
    "display": "inline-block",
    "backgroundImage": "linear-gradient(#ffcf00, #ffcf00)",
    "backgroundSize": "0% 2px",
    "backgroundPosition": "0 100%",
    "backgroundRepeat": "no-repeat",
    "transition": "color 0.2s ease, background-size 0.2s ease",
    "paddingBottom": "2px",
}

HOVER_UNDERLINE = {"color": "var(--color-text-100)", "backgroundSize": "100% 2px"}


def navbar_icons_item(text: str, url: str, disabled: bool) -> rx.Component:
    disabled_style = {"pointerEvents": "none", "opacity": "0.6"} if disabled else {}
    return rx.link(
        rx.text(text, size="4", weight="medium"),
        href=url,
        style=UNDERLINE_STYLE | disabled_style,
        _hover=HOVER_UNDERLINE,
    )


def navbar_icons_menu_item(text: str, url: str, disabled: bool = False) -> rx.Component:
    disabled_style = {"pointerEvents": "none", "opacity": "0.6"} if disabled else {}
    return rx.link(
        rx.text(text, size="3", weight="medium"),
        href=url,
        style=UNDERLINE_STYLE | disabled_style,
        _hover=HOVER_UNDERLINE,
    )


def navbar_icons() -> rx.Component:
    return rx.box(
        rx.desktop_only(
            rx.hstack(
                rx.hstack(
                    rx.link(
                        rx.color_mode_cond(
                            light=rx.image(
                                src="/cardanoism-new-logo-light.png",
                                width="15em",
                                height="auto",
                                alt="カルダノイズム",
                            ),
                            dark=rx.image(
                                src="/cardanoism-new-logo-dark.png",
                                width="15em",
                                height="auto",
                                alt="カルダノイズム",
                            ),
                        ),
                        href="./",
                    ),
                ),
                rx.hstack(
                    navbar_icons_item("ホーム", "/", False),
                    rx.menu.root(
                        rx.menu.trigger(
                            rx.button(
                                rx.text("カタリスト", size="4", weight="medium"),
                                rx.icon("chevron-down"),
                                weight="medium",
                                variant="ghost",
                                size="3",
                            ),
                        ),
                        rx.menu.content(
                            rx.menu.item(        
                                rx.link(
                                    rx.text("ファンド一覧", size="3", weight="medium"),
                                    href="/catalyst/funds",
                                    width="100%",
                                    color="inherit",
                                ),
                            ),
                            rx.menu.item(
                                rx.link(
                                    rx.text("提案一覧", size="3", weight="medium"),
                                    href="/catalyst",
                                    width="100%",
                                    color="inherit",
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
        ),
        rx.mobile_and_tablet(
            rx.hstack(
                rx.hstack(
                    rx.link(
                        rx.image(
                            src="/cardanoism-new-logo-light.png",
                            width="15em",
                            height="auto",
                            alt="カルダノイズム",
                        ),
                        href="./",
                    ),
                    align_items="center",
                ),
                rx.menu.root(
                    rx.menu.trigger(rx.icon("menu", size=30)),
                    rx.menu.content(
                        navbar_icons_menu_item("ホーム", "/"),
                        navbar_icons_menu_item("カタリスト", "/catalyst"),
                        navbar_icons_menu_item("ガバナンス", "/#", True),
                    ),
                ),
                justify_content="space-between",
                align_items="center",
            ),
        ),
        background="var(--color-bg-100)",
        padding_x="5em",
        padding_y="1em",
        justify="center",
        position="fixed",
        z_index="500",
        width="100%",
    )
