import reflex as rx
from reflex.style import set_color_mode, color_mode



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
        ),
        rx.segmented_control.item(
            rx.icon(tag="sun", size=20),
            value="light",
        ),
        rx.segmented_control.item(
            rx.icon(tag="moon", size=20),
            value="dark",
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


def footer_three_columns() -> rx.Component:
    return rx.el.footer(
        rx.vstack(
            # rx.flex(
            #     footer_items_1(),
            #     footer_items_2(),
            #     footer_items_3(),
            #     justify="between",
            #     spacing="6",
            #     flex_direction=["column", "column", "row"],
            #     width="100%",
            # ),
            rx.divider(),
            rx.flex(
                rx.hstack(
                    rx.image(
                        src="/cardanoism-new-logo-light.png",
                        width="8em",
                        height="auto",
                    ),
                    rx.text(
                        "© 2025 Cardanoism by Everada Labs",
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
            spacing="5",
            max_width="1130px",
            margin_x="auto",
            margin_bottom="50px"
        ),
        width="100%",
    )
