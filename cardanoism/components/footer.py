import reflex as rx
from reflex.style import set_color_mode, color_mode

from cardanoism.backend.auth_state import AuthState
from cardanoism.components.cookie_banner import cookie_settings_link



def footer_item(text: str, href: str) -> rx.Component:
    return rx.link(rx.text(text, size="3"), href=href)


def footer_items_1() -> rx.Component:
    return rx.flex(
        rx.heading(
            "PRODUCTS", size="4", weight="bold", as_="h3"
        ),
        footer_item("Web Design", "/#"),
        footer_item("Web Development", "/#"),
        footer_item("E-commerce", "/#"),
        footer_item("Content Management", "/#"),
        footer_item("Mobile Apps", "/#"),
        spacing="4",
        text_align=["center", "center", "start"],
        flex_direction="column",
    )


def footer_items_2() -> rx.Component:
    return rx.flex(
        rx.heading(
            "RESOURCES", size="4", weight="bold", as_="h3"
        ),
        footer_item("Blog", "/#"),
        footer_item("Case Studies", "/#"),
        footer_item("Whitepapers", "/#"),
        footer_item("Webinars", "/#"),
        footer_item("E-books", "/#"),
        spacing="4",
        text_align=["center", "center", "start"],
        flex_direction="column",
    )


def footer_items_3() -> rx.Component:
    return rx.flex(
        rx.heading(
            "ABOUT US", size="4", weight="bold", as_="h3"
        ),
        footer_item("Our Team", "/#"),
        footer_item("Careers", "/#"),
        footer_item("Contact Us", "/#"),
        footer_item("Privacy Policy", "/#"),
        footer_item("Terms of Service", "/#"),
        spacing="4",
        text_align=["center", "center", "start"],
        flex_direction="column",
    )


def dark_mode_toggle() -> rx.Component:
    return rx.segmented_control.root(
        rx.segmented_control.item(
            rx.icon(tag="monitor", size=20),
            value="system",
            cursor="pointer",
        ),
        rx.segmented_control.item(
            rx.icon(tag="sun", size=20),
            value="light",
            cursor="pointer",
        ),
        rx.segmented_control.item(
            rx.icon(tag="moon", size=20),
            value="dark",
            cursor="pointer",
        ),
        on_change=set_color_mode,
        variant="classic",
        radius="large",
        value=color_mode,
    )

def socials() -> rx.Component:
    return rx.flex(
        dark_mode_toggle(),
        spacing="3",
        justify_content=["center", "center", "end"],
        width="100%",
    )


def _legal_links() -> rx.Component:
    """フッター下部のプライバシーポリシー / 利用規約 / Cookie 設定 / お問い合わせリンク。"""
    item_style = {
        "fontSize": "13px",
        "color": "var(--gray-10)",
    }

    def _sep():
        return rx.text("·", color="var(--gray-7)", style={"fontSize": "13px"})

    return rx.flex(
        rx.link(rx.text(AuthState.t["nav_company"], style=item_style), href="/company"),
        _sep(),
        rx.link(rx.text(AuthState.t["nav_pricing"], style=item_style), href="/pricing"),
        _sep(),
        rx.link(rx.text(AuthState.t["nav_privacy"], style=item_style), href="/privacy"),
        _sep(),
        rx.link(rx.text(AuthState.t["nav_terms"], style=item_style), href="/terms"),
        _sep(),
        rx.link(rx.text(AuthState.t["nav_tokushoho"], style=item_style), href="/tokushoho"),
        _sep(),
        cookie_settings_link("nav_cookie_settings"),
        _sep(),
        rx.link(rx.text(AuthState.t["nav_contact"], style=item_style), href="/contact"),
        spacing="2",
        align="center",
        justify_content=["center", "center", "start"],
        flex_wrap="wrap",
    )


def footer_three_columns() -> rx.Component:
    return rx.el.footer(
        rx.vstack(
            rx.divider(),
            rx.flex(
                rx.hstack(
                    rx.image(
                        src=rx.color_mode_cond(
                            light="/cardanoism-new-logo-light.png",
                            dark="/cardanoism-new-logo-dark.png",
                        ),
                        width="8em",
                        height="auto",
                    ),
                    rx.text(
                        "© 2025 Cardanoism All rights reserved.",
                        size="3",
                        white_space="nowrap",
                        weight="medium",
                    ),
                    rx.link(
                        rx.image(
                        src=rx.color_mode_cond(
                            light="/x-logo-black.png",
                            dark="/x-logo-white.png",
                            ),
                        width="1.2em",
                        height="auto",
                        ),
                        href="https://x.com/cardanoism",
                        target="_blank",
                        padding_x="5px",
                        padding_y="5px",
                    ),
                    spacing="2",
                    align="center",
                    justify_content=[
                        "start",
                        "start",
                        "start",
                    ],
                    flex_direction=["column","column","row","row","row"],
                    width="100%",
                ),
                socials(),
                spacing="4",
                flex_direction=["column", "column", "row"],
                width="100%",
            ),
            _legal_links(),
            spacing="5",
            max_width="1130px",
            margin_x="auto",
            margin_bottom="50px"
        ),
        width="100%",
    )
