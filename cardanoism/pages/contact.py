"""The home page of the app."""
from cardanoism.templates import template

import reflex as rx

@template(route="/contact", title="連絡先")
def contact() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.box(
                rx.section(
                    rx.heading("連絡先"),
                    rx.box(
                        rx.link("BTBF", href="https://x.com/btbfpark"),
                        rx.link("Cardanoism", href="https://x.com/cardanoism")
                    ),
                    padding_left="12px",
                    padding_right="12px",
                    background_color="var(--gray-2)",
                ),
                rx.section(
                    rx.heading("提案書修正依頼"),
                    rx.box(
                        rx.text("翻訳精度の修正依頼などこちらからお願いいたします"),
                        ),
                    padding_left="12px",
                    padding_right="12px",
                    background_color="var(--gray-2)",
                ),
                width="100%",
                margin_top="50px"
            ),
        )
    )
