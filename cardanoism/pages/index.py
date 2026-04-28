import reflex as rx

from cardanoism.templates import template
from cardanoism import styles
from cardanoism.backend.warmup import WarmupState
from cardanoism.backend.auth_state import AuthState


ACCENT = "#ffcf00"
ACCENT_DARK = "#c7a300"
TEXT_MUTED = "var(--gray-10)"

REWARD_COLOR = "#16a34a"
DREP_COLOR = "#3b82f6"
POOL_COLOR = ACCENT_DARK

LINE_BRAND = "#06C755"
TG_BRAND = "#2AABEE"
MAIL_BRAND = "#7c5cff"


HOME_CSS = f"""
<style>
h1, h2, h3, h4, h5, h6 {{
  font-family: {styles.font_family};
}}
@keyframes cdn_float {{
  0%, 100% {{ transform: translateY(0); }}
  50% {{ transform: translateY(-7px); }}
}}
@keyframes cdn_pulse {{
  0%, 100% {{ opacity: 0.55; transform: scale(1); }}
  50% {{ opacity: 1; transform: scale(1.25); }}
}}
.cdn-hero-grid {{
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(140,140,140,0.10) 1px, transparent 1px),
    linear-gradient(90deg, rgba(140,140,140,0.10) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: radial-gradient(ellipse 70% 60% at 80% 30%, black 0%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse 70% 60% at 80% 30%, black 0%, transparent 75%);
  pointer-events: none;
}}
.cdn-hero-glow {{
  position: absolute;
  width: 520px;
  height: 520px;
  top: -140px;
  right: -120px;
  background: radial-gradient(circle, rgba(255,207,0,0.22) 0%, transparent 70%);
  filter: blur(36px);
  pointer-events: none;
}}
.cdn-soft-card {{
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}}
.cdn-soft-card:hover {{
  transform: translateY(-3px);
}}
</style>
"""


def _shell(*children, **kw) -> rx.Component:
    base = dict(
        max_width="1180px",
        width="100%",
        margin_x="auto",
        padding_x=["20px", "28px", "40px"],
    )
    base.update(kw)
    return rx.box(*children, **base)


# ---------- Hero -----------------------------------------------------------

def _live_pill() -> rx.Component:
    return rx.hstack(
        rx.box(
            width="7px",
            height="7px",
            border_radius="999px",
            background="#22c55e",
            box_shadow="0 0 0 4px rgba(34,197,94,0.18)",
            style={"animation": "cdn_pulse 2.2s ease-in-out infinite"},
        ),
        rx.text("LIVE", size="1", weight="bold", letter_spacing="0.16em"),
        rx.text(AuthState.t["home_preview_label"], size="1", color=TEXT_MUTED),
        spacing="2",
        align="center",
        padding="6px 12px",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="999px",
        background=rx.color_mode_cond("rgba(255,255,255,0.7)", "rgba(255,255,255,0.04)"),
        backdrop_filter="blur(8px)",
        align_self="end",
    )


def _hero_notification(accent: str, icon: str, title, body, delay: str) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon(icon, size=16, color="#fff"),
            width="36px",
            height="36px",
            display="flex",
            align_items="center",
            justify_content="center",
            border_radius="11px",
            background=accent,
            flex_shrink="0",
        ),
        rx.vstack(
            rx.text(title, size="2", weight="bold", color="var(--gray-12)"),
            rx.text(body, size="1", color=TEXT_MUTED, line_height="1.5"),
            spacing="1",
            align_items="start",
            min_width="0",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding="13px 16px",
        border_radius="14px",
        border=f"1px solid {rx.color('gray', 5)}",
        background=rx.color_mode_cond(
            "linear-gradient(135deg, rgba(255,255,255,0.95), rgba(255,255,255,0.82))",
            "linear-gradient(135deg, rgba(28,28,36,0.92), rgba(20,20,28,0.86))",
        ),
        backdrop_filter="blur(10px)",
        box_shadow=rx.color_mode_cond(
            "0 18px 38px -24px rgba(0,0,0,0.30)",
            "0 18px 38px -24px rgba(0,0,0,0.85)",
        ),
        style={
            "animation": "cdn_float 6.5s ease-in-out infinite",
            "animationDelay": delay,
        },
    )


def hero_section() -> rx.Component:
    headline = rx.heading(
        AuthState.t["hero_heading"],
        as_="h1",
        size="9",
        weight="bold",
        line_height="1.05",
        letter_spacing="-0.02em",
    )
    subtitle = rx.text(
        AuthState.t["hero_subtitle"],
        size="4",
        color=rx.color_mode_cond("rgba(20,20,20,0.74)", "rgba(245,245,245,0.78)"),
        line_height="1.75",
        max_width="600px",
    )
    cta = rx.hstack(
        rx.link(
            rx.button(
                rx.icon("bell", size=16),
                AuthState.t["hero_cta_primary"],
                size="3",
                background=ACCENT,
                color="#111",
                border=f"1px solid {ACCENT_DARK}",
                cursor="pointer",
                padding="0 22px",
                _hover={"background": ACCENT_DARK, "color": "#fff"},
            ),
            href="/login",
            underline="none",
        ),
        rx.link(
            rx.button(
                AuthState.t["hero_cta_secondary"],
                rx.icon("arrow-right", size=16),
                size="3",
                variant="ghost",
                color="var(--gray-12)",
                cursor="pointer",
            ),
            href="/governance",
            underline="none",
        ),
        spacing="3",
        wrap="wrap",
        align="center",
    )

    notif_stack = rx.vstack(
        _live_pill(),
        _hero_notification(REWARD_COLOR, "wallet", AuthState.t["home_preview_reward_title"], AuthState.t["home_preview_reward_body"], "0s"),
        _hero_notification(DREP_COLOR, "vote", AuthState.t["home_preview_drep_title"], AuthState.t["home_preview_drep_body"], "1.4s"),
        _hero_notification(POOL_COLOR, "bell", AuthState.t["home_preview_pool_title"], AuthState.t["home_preview_pool_body"], "2.8s"),
        spacing="3",
        align_items="stretch",
        width="100%",
        max_width="420px",
    )

    return rx.box(
        rx.box(class_name="cdn-hero-grid"),
        rx.box(class_name="cdn-hero-glow"),
        _shell(
            rx.flex(
                rx.vstack(
                    headline,
                    subtitle,
                    cta,
                    spacing="6",
                    align_items="start",
                    flex="1",
                    min_width="0",
                    max_width="640px",
                ),
                rx.box(
                    notif_stack,
                    flex="0 0 auto",
                    display=["none", "none", "block"],
                ),
                direction={"base": "column", "md": "row"},
                align="center",
                spacing="8",
                width="100%",
            ),
            padding_y=["72px", "96px", "120px"],
            position="relative",
        ),
        position="relative",
        background=rx.color_mode_cond(
            "linear-gradient(180deg, #fefcf2 0%, #fafbf6 100%)",
            "linear-gradient(180deg, #0c0d12 0%, #101117 100%)",
        ),
        width="100%",
        overflow="hidden",
        border_bottom=f"1px solid {rx.color('gray', 4)}",
    )


# ---------- Notification features -----------------------------------------

def _section_heading(kicker, title, subtitle, kicker_color: str = ACCENT_DARK) -> rx.Component:
    return rx.vstack(
        rx.text(kicker, size="2", weight="bold", color=kicker_color, letter_spacing="0.14em"),
        rx.heading(title, as_="h2", size="7", weight="bold", line_height="1.2", max_width="720px"),
        rx.text(subtitle, size="3", color=TEXT_MUTED, line_height="1.7", max_width="720px"),
        spacing="3",
        align_items="start",
        width="100%",
    )


def _feature_card(icon: str, accent: str, title, desc) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.box(
                rx.icon(icon, size=22, color=accent),
                width="46px",
                height="46px",
                display="flex",
                align_items="center",
                justify_content="center",
                border_radius="12px",
                background=f"{accent}1f",
                border=f"1px solid {accent}33",
            ),
            rx.heading(title, size="4", as_="h3", weight="bold"),
            rx.text(desc, size="2", color=TEXT_MUTED, line_height="1.7"),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        class_name="cdn-soft-card",
        padding="26px",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="18px",
        background=rx.color_mode_cond("rgba(255,255,255,0.78)", "rgba(255,255,255,0.03)"),
        height="100%",
        _hover={
            "border_color": accent,
            "box_shadow": f"0 22px 48px -32px {accent}80",
        },
    )


def notifications_section() -> rx.Component:
    return _shell(
        rx.vstack(
            _section_heading(
                AuthState.t["feature_section_kicker"],
                AuthState.t["feature_section_title"],
                AuthState.t["feature_section_subtitle"],
            ),
            rx.grid(
                _feature_card(
                    "wallet", REWARD_COLOR,
                    AuthState.t["feature_reward_title"],
                    AuthState.t["feature_reward_desc"],
                ),
                _feature_card(
                    "vote", DREP_COLOR,
                    AuthState.t["feature_drep_title"],
                    AuthState.t["feature_drep_desc"],
                ),
                _feature_card(
                    "bell", POOL_COLOR,
                    AuthState.t["feature_pool_title"],
                    AuthState.t["feature_pool_desc"],
                ),
                columns={"base": "1", "md": "3"},
                spacing="4",
                width="100%",
            ),
            spacing="7",
            width="100%",
        ),
        padding_y=["64px", "80px", "96px"],
    )


# ---------- Channels strip -------------------------------------------------

def _channel_card(brand_color: str, name: str, body, icon_node: rx.Component) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    icon_node,
                    width="44px",
                    height="44px",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    border_radius="12px",
                    background=f"{brand_color}1a",
                    border=f"1px solid {brand_color}33",
                ),
                rx.heading(name, size="4", as_="h3", weight="bold"),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.text(body, size="2", color=TEXT_MUTED, line_height="1.7"),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        class_name="cdn-soft-card",
        padding="22px",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="18px",
        background=rx.color_mode_cond("rgba(255,255,255,0.78)", "rgba(255,255,255,0.03)"),
        height="100%",
    )


def channels_section() -> rx.Component:
    line_icon = rx.box(
        rx.image(src="/line-icon.png", width="22px", height="22px", object_fit="contain"),
    )
    tg_icon = rx.icon("send", size=22, color=TG_BRAND)
    mail_icon = rx.icon("mail", size=22, color=MAIL_BRAND)

    return rx.box(
        _shell(
            rx.vstack(
                _section_heading(
                    "CHANNELS",
                    AuthState.t["home_preview_channel_label"],
                    AuthState.t["home_preview_footer"],
                ),
                rx.grid(
                    _channel_card(
                        LINE_BRAND, "LINE",
                        AuthState.t["home_channel_line_desc"],
                        line_icon,
                    ),
                    _channel_card(
                        TG_BRAND, "Telegram",
                        AuthState.t["home_channel_telegram_desc"],
                        tg_icon,
                    ),
                    _channel_card(
                        MAIL_BRAND, "Email",
                        AuthState.t["home_channel_email_desc"],
                        mail_icon,
                    ),
                    columns={"base": "1", "sm": "2", "md": "3"},
                    spacing="4",
                    width="100%",
                ),
                spacing="7",
                width="100%",
            ),
            padding_y=["64px", "80px", "96px"],
        ),
        background=rx.color_mode_cond(
            "linear-gradient(180deg, var(--gray-2) 0%, transparent 100%)",
            "linear-gradient(180deg, rgba(255,255,255,0.02) 0%, transparent 100%)",
        ),
        width="100%",
    )


# ---------- 3-step setup ---------------------------------------------------

def _step(num: int, title, body) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text(
                f"0{num}",
                size="6",
                weight="bold",
                color=ACCENT_DARK,
                letter_spacing="-0.02em",
                line_height="1",
            ),
            rx.box(width="32px", height="2px", background=ACCENT, align_self="center"),
            spacing="3",
            align="center",
        ),
        rx.heading(title, size="4", as_="h3", weight="bold"),
        rx.text(body, size="2", color=TEXT_MUTED, line_height="1.7"),
        spacing="3",
        align_items="start",
        padding="24px",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="18px",
        background=rx.color_mode_cond("rgba(255,255,255,0.78)", "rgba(255,255,255,0.03)"),
        height="100%",
    )


def setup_section() -> rx.Component:
    return _shell(
        rx.vstack(
            _section_heading(
                "GET STARTED",
                AuthState.t["home_setup_title"],
                AuthState.t["home_setup_subtitle"],
            ),
            rx.link(
                rx.button(
                    AuthState.t["home_setup_cta"],
                    rx.icon("arrow-right", size=16),
                    size="3",
                    background=ACCENT,
                    color="#111",
                    border=f"1px solid {ACCENT_DARK}",
                    cursor="pointer",
                    padding="0 20px",
                    _hover={"background": ACCENT_DARK, "color": "#fff"},
                ),
                href="/mypage?tab=notification",
                underline="none",
            ),
            rx.grid(
                _step(1, AuthState.t["home_step_account_title"], AuthState.t["home_step_account_body"]),
                _step(2, AuthState.t["home_step_stake_title"], AuthState.t["home_step_stake_body"]),
                _step(3, AuthState.t["home_step_channel_title"], AuthState.t["home_step_channel_body"]),
                columns={"base": "1", "md": "3"},
                spacing="4",
                width="100%",
            ),
            spacing="6",
            width="100%",
            align_items="start",
        ),
        padding_y=["64px", "80px", "96px"],
    )


# ---------- Explore other tools -------------------------------------------

def _explore_link(icon: str, label, href: str) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.icon(icon, size=16, color=ACCENT_DARK),
            rx.text(label, size="3", weight="medium", color="var(--gray-12)"),
            rx.spacer(),
            rx.icon("arrow-right", size=15, color=TEXT_MUTED),
            spacing="3",
            align="center",
            width="100%",
            padding="16px 20px",
            border=f"1px solid {rx.color('gray', 5)}",
            border_radius="14px",
            background=rx.color_mode_cond("rgba(255,255,255,0.7)", "rgba(255,255,255,0.025)"),
            class_name="cdn-soft-card",
            _hover={"border_color": ACCENT_DARK},
        ),
        href=href,
        underline="none",
        width="100%",
    )


def explore_section() -> rx.Component:
    return rx.box(
        _shell(
            rx.vstack(
                _section_heading(
                    "EXPLORE",
                    AuthState.t["home_explore_title"],
                    AuthState.t["home_explore_subtitle"],
                ),
                rx.grid(
                    _explore_link("layers", AuthState.t["home_explore_governance"], "/governance"),
                    _explore_link("users", AuthState.t["home_explore_drep"], "/governance/drep"),
                    _explore_link("search", AuthState.t["home_explore_catalyst"], "/catalyst"),
                    columns={"base": "1", "sm": "3"},
                    spacing="3",
                    width="100%",
                ),
                spacing="6",
                width="100%",
            ),
            padding_y=["64px", "80px", "96px"],
        ),
        background=rx.color_mode_cond("var(--gray-2)", "rgba(255,255,255,0.02)"),
        width="100%",
        border_top=f"1px solid {rx.color('gray', 4)}",
    )


@template(route="/", title="Cardanoism | カルダノをもっと身近に", on_load=WarmupState.warm_up_only)
def index() -> rx.Component:
    return rx.box(
        rx.html(HOME_CSS),
        hero_section(),
        notifications_section(),
        channels_section(),
        setup_section(),
        explore_section(),
        width="100%",
        max_width="100%",
    )
