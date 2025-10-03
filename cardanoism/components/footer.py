import reflex as rx


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


def social_link(icon: str, href: str) -> rx.Component:
    return rx.link(rx.icon(icon), href=href ,is_external=True)


def socials() -> rx.Component:
    return rx.flex(
        # social_link("github", "/#"),
        social_link("twitter", "https://x.com/cardanoism"),
        # social_link("facebook", "/#"),
        # social_link("linkedin", "/#"),
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
                        src="/cardanoism-logo.png",
                        width="8em",
                        height="auto",
                    ),
                    rx.text(
                        "© 2024 Cardanoism by Everada Labs",
                        size="3",
                        white_space="nowrap",
                        weight="medium",
                    ),
                    spacing="2",
                    align="center",
                    justify_content=[
                        "center",
                        "center",
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
            max_width="1200px",
            margin_x="auto",
            margin_bottom="50px"
        ),
        width="100%",
    )