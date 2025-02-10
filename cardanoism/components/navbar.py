import reflex as rx
import reflex_chakra as rc
from reflex.style import toggle_color_mode

def navbar_icons_item(
    text: str, icon: str, url: str, disabled: bool
) -> rx.Component:
    return rx.link(
        rc.button(
            rx.hstack(
                rx.icon(icon),
                rx.text(text, size="4", weight="medium"),
            ),
            variant="ghost",
            size="md",
            is_disabled=disabled
        ),
        href=url,
    )


def navbar_icons_menu_item(
    text: str, icon: str, url: str
) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.icon(icon, size=16),
            rx.text(text, size="3", weight="medium"),
        ),
        href=url,
    )


def navbar_icons() -> rx.Component:
    return rx.box(
        rx.desktop_only(
            rx.hstack(
                rx.hstack(
                    rx.link(
                        rx.image(
                        src="/cardanoism-logo.png",
                        width="15em",
                        height="auto",
                        alt="カルダノイズム",
                        ),
                        href="./"
                    ),

                ),
                rx.hstack(
                    navbar_icons_item("ホーム", "home", "/", False),
                    navbar_icons_item("カタリスト", "landmark", "/catalyst", False),
                    navbar_icons_item("ガバナンス", "vote", "/#", True),
                    #navbar_icons_item("連絡先", "mail", "/#", False),
                    rx.button(
                        rx.color_mode_cond(light=rx.icon("moon"), dark=rx.icon("sun")),
                        on_click=toggle_color_mode,
                    ),
                    spacing="6",
                    padding_right="5px",
                ),
                justify_content="space-between",
                align_items="center",
                max_width="1200px",
                margin_x="auto"
            ),
        ),
        rx.mobile_and_tablet(
            rx.hstack(
                rx.hstack(
                    rx.link(
                        rx.image(
                        src="/cardanoism-logo.png",
                        width="15em",
                        height="auto",
                        alt="カルダノイズム",
                        ),
                        href="./"
                    ),
                    align_items="center",
                ),
                rx.menu.root(
                    rx.menu.trigger(
                        rx.icon("menu", size=30)
                    ),
                    rx.menu.content(
                        navbar_icons_menu_item(
                            "ホーム", "home", "/"
                        ),
                        navbar_icons_menu_item(
                            "カタリスト", "coins", "/catalyst"
                        ),
                        navbar_icons_menu_item(
                            "ガバナンス", "layers", "/#"
                        ),
                        # navbar_icons_menu_item(
                        #     "連絡先", "mail", "/#"
                        # ),
                    ),
                ),
                justify_content="space-between",
                align_items="center",
            ),
        ),
        background=f"radial-gradient(circle at top right, {rx.color('accent', 2)}, {rx.color('mauve', 1)});",
        padding_x="5em",
        padding_y="1em",
        justify="center",
        position="fixed",
        z_index="500",
        width="100%",
        #border_radius="12px",
    )