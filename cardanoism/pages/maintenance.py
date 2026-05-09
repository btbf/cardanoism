"""maintenance.py
メンテナンスページ (/maintenance)

メンテナンス時に表示する standalone ページ。@template でラップせず、
navbar / footer / cookie banner も外して「メンテナンス中」のみが見える状態にする。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.auth_state import AuthState


ACCENT      = "#ffcf00"
ACCENT_DARK = "#c7a300"
TEXT_MUTED  = "var(--gray-10)"


_PULSE_KEYFRAME = """
<style>
@keyframes maint_pulse {
  0%, 80%, 100% { opacity: 0.25; transform: scale(0.85); }
  40%           { opacity: 1;    transform: scale(1.1); }
}
</style>
"""


def _dot(delay: str) -> rx.Component:
    return rx.box(
        width="8px",
        height="8px",
        border_radius="999px",
        background=ACCENT_DARK,
        style={"animation": f"maint_pulse 1.4s ease-in-out {delay} infinite both"},
    )


@rx.page(route="/maintenance", title="メンテナンス中 | Cardanoism")
def maintenance_page() -> rx.Component:
    icon_box = rx.hstack(_dot("0s"), _dot("0.18s"), _dot("0.36s"), spacing="2")

    card = rx.vstack(
        icon_box,
        rx.heading(
            AuthState.t["maintenance_title"],
            as_="h1",
            size={"base": "7", "md": "8"},
            weight="bold",
            color="var(--gray-12)",
            line_height="1.2",
            text_align="center",
            style={"letterSpacing": "-0.02em"},
        ),
        rx.text(
            AuthState.t["maintenance_lead"],
            size="3",
            color=TEXT_MUTED,
            text_align="center",
        ),
        rx.text(
            AuthState.t["maintenance_message"],
            size="3",
            color="var(--gray-12)",
            line_height="1.7",
            text_align="center",
            style={"wordBreak": "break-word"},
        ),
        rx.divider(margin_y="8px"),
        rx.vstack(
            rx.text(
                AuthState.t["maintenance_status_note"],
                size="2",
                color=TEXT_MUTED,
                text_align="center",
                style={"wordBreak": "break-word"},
            ),
            rx.link(
                rx.button(
                    rx.icon("twitter", size=14),
                    rx.text("@cardanoism", size="2", weight="medium"),
                    size="2",
                    variant="soft",
                    color_scheme="gray",
                    cursor="pointer",
                ),
                href="https://x.com/cardanoism",
                is_external=True,
                underline="none",
            ),
            spacing="2", align="center",
        ),
        rx.vstack(
            rx.text(
                AuthState.t["maintenance_contact_label"],
                size="2",
                color=TEXT_MUTED,
            ),
            rx.link(
                "contact@kuhito.co.jp",
                href="mailto:contact@kuhito.co.jp",
                color=ACCENT_DARK,
                size="2",
                weight="medium",
            ),
            spacing="1", align="center",
        ),
        rx.link(
            rx.text(
                AuthState.t["maintenance_back"],
                size="2",
                color=TEXT_MUTED,
            ),
            href="/",
            underline="hover",
            style={"marginTop": "8px"},
        ),
        spacing="4",
        align="center",
        padding="40px 32px",
        border_radius="20px",
        background=rx.color_mode_cond(
            "rgba(255,255,255,0.96)",
            "rgba(28,28,32,0.96)",
        ),
        border=f"1px solid {rx.color('gray', 5)}",
        box_shadow=rx.color_mode_cond(
            "0 24px 60px -20px rgba(15,23,42,0.18), 0 8px 20px -8px rgba(15,23,42,0.10)",
            "0 24px 60px -20px rgba(0,0,0,0.6)",
        ),
        max_width="560px",
        width="100%",
        style={"backdropFilter": "blur(12px)"},
    )

    return rx.center(
        rx.html(_PULSE_KEYFRAME),
        rx.vstack(
            rx.link(
                rx.image(
                    src=rx.color_mode_cond(
                        light="/cardanoism-new-logo-light.png",
                        dark="/cardanoism-new-logo-dark.png",
                    ),
                    width="160px",
                    height="auto",
                    style={"opacity": "0.9"},
                ),
                href="/",
                underline="none",
            ),
            card,
            spacing="6",
            align="center",
            width="100%",
        ),
        min_height="100vh",
        padding=["32px 16px", "40px 24px", "60px 32px"],
        background=rx.color_mode_cond(
            "linear-gradient(135deg, #fff8e1 0%, #fffaf0 50%, #ffffff 100%)",
            "linear-gradient(135deg, #1a1714 0%, #14110e 50%, #0f0d0a 100%)",
        ),
    )
