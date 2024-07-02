"""The dashboard page."""

from cardanoism.templates import template

import reflex as rx

@template(route="/catalyst/fund", title="カタリストファンド")
def fund() -> rx.Component:
    """The dashboard page.

    Returns:
        The UI for the dashboard page.
    """
    return rx.vstack(
        rx.heading("カタリスト", size="8"),
        rx.text("Welcome to Reflex!"),
        rx.text(
            "You can edit this page in ",
            rx.code("{your_app}/pages/fund.py"),
        ),
    )