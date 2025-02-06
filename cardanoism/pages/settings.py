"""The settings page."""

from cardanoism.templates import ThemeState, template
from reflex.style import toggle_color_mode

import reflex as rx

@template(route="/settings", title="設定")
def settings() -> rx.Component:
    """The settings page.

    Returns:
        The UI for the settings page.
    """
    return rx.vstack(
        rx.heading("Settings", size="8"),
        rx.hstack(
            rx.text("Dark mode: "),
            rx.color_mode.switch(),
        ),
        rx.button(
        rx.color_mode_cond(light=rx.icon("moon"), dark=rx.icon("sun")),
        on_click=toggle_color_mode,
        ),
        rx.hstack(
            rx.text("Primary color: "),
            rx.select(
                [
                    "tomato",
                    "red",
                    "ruby",
                    "crimson",
                    "pink",
                    "plum",
                    "purple",
                    "violet",
                    "iris",
                    "indigo",
                    "blue",
                    "cyan",
                    "teal",
                    "jade",
                    "green",
                    "grass",
                    "brown",
                    "orange",
                    "sky",
                    "mint",
                    "lime",
                    "yellow",
                    "amber",
                    "gold",
                    "bronze",
                    "gray",
                ],
                value=ThemeState.accent_color,
                on_change=ThemeState.set_accent_color,
            ),
        ),
        rx.hstack(
            rx.text("Secondary color: "),
            rx.select(
                [
                    "gray",
                    "mauve",
                    "slate",
                    "sage",
                    "olive",
                    "sand",
                ],
                value=ThemeState.gray_color,
                on_change=ThemeState.set_gray_color,
            ),
        ),
        rx.text(
            "You can edit this page in ",
            rx.code("{your_app}/pages/settings.py"),
            size="1",
        ),
    )
