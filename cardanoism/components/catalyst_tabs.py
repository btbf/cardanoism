import reflex as rx

from cardanoism.backend.auth_state import AuthState


def _tab(icon: str, label, href: str, active: bool) -> rx.Component:
    active_style = {
        "background": "var(--amber-9)",
        "color": "#111",
        "fontWeight": "700",
        "boxShadow": "0 2px 8px rgba(255,193,7,0.32)",
    }
    inactive_style = {
        "background": "transparent",
        "color": "var(--gray-11)",
        "fontWeight": "500",
    }
    style = active_style if active else inactive_style
    return rx.link(
        rx.hstack(
            rx.icon(icon, size=15),
            rx.text(label, size="3"),
            spacing="2",
            align="center",
            padding="7px 16px",
            border_radius="9999px",
            transition="background 0.15s, color 0.15s, box-shadow 0.15s",
            style=style,
            _hover=({} if active else {"background": "var(--gray-a3)", "color": "var(--gray-12)"}),
        ),
        href=href,
        underline="none",
    )


def catalyst_tabs(active: str) -> rx.Component:
    """Segmented toggle between proposals list and funds list.

    active: "proposals" or "funds"
    """
    return rx.box(
        rx.hstack(
            _tab("file-text", AuthState.t["nav_proposals_list"], "/catalyst", active == "proposals"),
            _tab("layers", AuthState.t["nav_funds_list"], "/catalyst/funds", active == "funds"),
            spacing="1",
            padding="4px",
            background=rx.color_mode_cond("var(--gray-3)", "var(--gray-4)"),
            border_radius="9999px",
            align="center",
            width="fit-content",
        ),
        width="100%",
        display="flex",
        justify_content=["center", "center", "flex-start"],
        padding_y="8px",
    )
