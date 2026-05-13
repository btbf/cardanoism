import reflex as rx
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.fiat_state import FiatRateState
from cardanoism.backend.wallet_state import WalletState
from cardanoism.components.wallet_button import (
    wallet_connector_mount,
    wallet_status,
)

ACCENT = "#ffcf00"
ACCENT_DARK = "#c7a300"

_PILL = {
    "textDecoration": "none",
    "display": "inline-flex",
    "alignItems": "center",
    "padding": "5px 12px",
    "borderRadius": "9999px",
    "fontWeight": "500",
    "fontSize": "16px",
    "color": "var(--gray-11)",
    "transition": "background 0.15s, color 0.15s",
    "cursor": "pointer",
    # JA モードで「ステーキング」「ガバナンス」等が縦に折り返さないように
    "whiteSpace": "nowrap",
    "flexShrink": 0,
}
_PILL_HOVER = {
    "backgroundColor": "var(--gray-a3)",
    "color": "var(--gray-12)",
    "textDecoration": "none",
}


def fiat_rates_pill() -> rx.Component:
    """ナビバー内の ADA レート表示。
    言語 (AuthState.language) に連動して JA → ADA/JPY、EN → ADA/USD を表示する。
    """
    label_style = {"color": "var(--gray-9)", "fontSize": "11px", "fontWeight": "600", "letterSpacing": "0.02em"}
    value_style = {"color": "var(--gray-12)", "fontSize": "13px", "fontWeight": "700"}
    return rx.hstack(
        rx.cond(
            AuthState.language == "ja",
            rx.fragment(
                rx.el.span("ADA/JPY", style=label_style),
                rx.el.span(FiatRateState.ada_jpy, style=value_style),
            ),
            rx.fragment(
                rx.el.span("ADA/USD", style=label_style),
                rx.el.span(FiatRateState.ada_usd, style=value_style),
            ),
        ),
        rx.cond(
            FiatRateState.updated_label != "",
            rx.el.span(
                "(", FiatRateState.updated_label, ")",
                style={"color": "var(--gray-9)", "fontSize": "11px", "marginLeft": "4px"},
            ),
            rx.fragment(),
        ),
        spacing="2",
        align="center",
        padding="4px 12px",
        background=rx.color_mode_cond("var(--gray-2)", "var(--gray-3)"),
        border_radius="9999px",
        style={"whiteSpace": "nowrap"},
    )


def lang_toggle() -> rx.Component:
    """言語切替: globe アイコン + 現在言語のチップ。
    クリックで JA ⇄ EN をトグル。シンプルでモダンな見た目に。
    """
    is_ja = AuthState.language == "ja"
    current_label = rx.cond(is_ja, "日本語", "English")
    next_lang = rx.cond(is_ja, "en", "ja")
    return rx.el.button(
        rx.icon("globe", size=14, color="var(--gray-11)"),
        rx.text(
            current_label,
            size="2",
            weight="medium",
            color="var(--gray-11)",
            style={"whiteSpace": "nowrap"},
        ),
        on_click=AuthState.set_language(next_lang),
        style={
            "display":      "inline-flex",
            "alignItems":   "center",
            "gap":          "6px",
            "padding":      "5px 12px",
            "background":   "transparent",
            "border":       "1px solid var(--gray-6)",
            "borderRadius": "9999px",
            "cursor":       "pointer",
            "transition":   "background 0.15s, color 0.15s, border-color 0.15s",
            "whiteSpace":   "nowrap",
            "flexShrink":   0,
        },
        _hover={
            "background":   rx.color("gray", 3),
            "borderColor":  rx.color("gray", 8),
        },
    )


def nav_pill(text, url: str, disabled: bool = False) -> rx.Component:
    style = {**_PILL, **({"opacity": "0.4", "pointerEvents": "none"} if disabled else {})}
    return rx.link(
        rx.text(text, size="3", weight="medium"),
        href=url,
        style=style,
        _hover=_PILL_HOVER,
    )


def _submenu_link(icon_name: str, label, href: str) -> rx.Component:
    """サブメニュー項目（アイコン + テキスト）。Reflex 公式 About 風。"""
    return rx.link(
        rx.icon(icon_name, size=15, color="var(--gray-11)", flex_shrink="0"),
        rx.text(label, size="2", weight="medium", color="var(--gray-12)"),
        href=href,
        underline="none",
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "gap": "10px",
            "padding": "8px 12px",
            "borderRadius": "8px",
            "textDecoration": "none",
            "transition": "background 0.12s",
            "width": "100%",
        },
        _hover={
            "background": rx.color("gray", 3),
            "textDecoration": "none",
        },
    )


def _mobile_drawer_link(label, href: str, *, bold: bool = False) -> rx.Component:
    """ドロワー内のシンプルなリンク行 (セクション見出しなど用)。
    rx.drawer.close で wrap して、リンククリック時にドロワーを自動で閉じる。
    """
    return rx.drawer.close(
        rx.link(
            rx.text(
                label,
                size="3",
                weight="bold" if bold else "medium",
                color="var(--gray-12)",
            ),
            href=href,
            underline="none",
            style={
                "display":      "flex",
                "alignItems":   "center",
                "padding":      "12px 8px",
                "borderRadius": "8px",
                "width":        "100%",
            },
            _hover={"background": rx.color("gray", 3)},
        ),
    )


def _mobile_drawer_subitem(icon_name: str, label, href: str) -> rx.Component:
    """ドロワー内のサブメニュー項目 (インデント + アイコン)。リンククリックでドロワーを閉じる。"""
    return rx.drawer.close(
        rx.link(
            rx.icon(icon_name, size=14, color="var(--gray-10)", flex_shrink="0"),
            rx.text(label, size="2", color="var(--gray-11)"),
            href=href,
            underline="none",
            style={
                "display":      "flex",
                "alignItems":   "center",
                "gap":          "10px",
                "padding":      "10px 12px 10px 24px",
                "borderRadius": "8px",
                "width":        "100%",
            },
            _hover={"background": rx.color("gray", 3)},
        ),
    )


def _mobile_drawer_section(
    label,
    value: str,
    sub_items: list[tuple[str, str, str]],
) -> rx.Component:
    """ドロワー 1 セクションをアコーディオン項目として返す。
    親 rx.accordion.root の子として配置する想定。
    sub_items: [(icon_name, label, href), ...]
    """
    return rx.accordion.item(
        value=value,
        header=rx.text(
            label,
            size="3",
            weight="bold",
            color="var(--gray-12)",
        ),
        content=rx.vstack(
            *[_mobile_drawer_subitem(icon, lab, h) for icon, lab, h in sub_items],
            spacing="0",
            align_items="stretch",
            width="100%",
        ),
    )


def nav_with_submenu(
    label,
    href: str,
    items: list[tuple[str, str, str]],
) -> rx.Component:
    """トップナビ項目 + ホバー時のドロップダウン。

    items: [(icon_name, label, href), ...]

    クリックで href に遷移、ホバーでサブメニューが開く。
    Radix HoverCard ベース (open_delay/close_delay を短く設定)。
    """
    return rx.hover_card.root(
        rx.hover_card.trigger(nav_pill(label, href)),
        rx.hover_card.content(
            rx.vstack(
                *[_submenu_link(icon, lab, h) for icon, lab, h in items],
                spacing="1",
                align_items="stretch",
                width="100%",
            ),
            side="bottom",
            align="start",
            side_offset=6,
            style={
                "padding": "8px",
                "minWidth": "220px",
                "borderRadius": "12px",
            },
        ),
        open_delay=80,
        close_delay=120,
    )


def auth_section() -> rx.Component:
    return rx.cond(
        AuthState.is_logged_in,
        rx.menu.root(
            rx.menu.trigger(
                rx.button(
                    rx.cond(
                        AuthState.avatar_url != "",
                        rx.avatar(src=AuthState.avatar_url, size="2", radius="full"),
                        rx.avatar(fallback=AuthState.username[:1], size="2", radius="full"),
                    ),
                    variant="ghost",
                    cursor="pointer",
                    padding="0",
                    border_radius="full",
                    style={"outline": "none", "background": "transparent"},
                    _hover={"background": "transparent", "outline": "none"},
                ),
            ),
            rx.menu.content(
                rx.menu.item(
                    rx.hstack(rx.icon("user", size=14), rx.text(AuthState.t["nav_mypage"], size="3"), spacing="2"),
                    on_click=rx.redirect("/mypage"),
                    cursor="pointer",
                ),
                rx.menu.separator(),
                rx.menu.item(
                    rx.hstack(rx.icon("log-out", size=14), rx.text(AuthState.t["nav_logout"], size="3"), spacing="2"),
                    color_scheme="red",
                    on_click=AuthState.logout,
                    cursor="pointer",
                ),
            ),
        ),
        rx.link(
            rx.button(
                AuthState.t["nav_login"],
                size="3",
                border_radius="9999px",
                cursor="pointer",
                style={
                    "background": f"linear-gradient(135deg, {ACCENT}, {ACCENT_DARK})",
                    "color": "#111",
                    "fontWeight": "700",
                    "border": "none",
                    "transition": "opacity 0.15s, box-shadow 0.15s",
                    "_hover": {
                        "opacity": "0.88",
                        "boxShadow": "0 2px 10px rgba(255,207,0,0.4)",
                    },
                },
            ),
            href="/login",
            underline="none",
        ),
    )


def navbar_icons() -> rx.Component:
    # ロゴ: 画像要素の min-width が intrinsic サイズに固定されると、JA モードで
    # ナビ項目が長いときに縮められず横にあふれる。max-width + 100% で柔軟に
    # 縮むようにし、ナビ項目側にも flex-shrink を許容する。
    logo = rx.link(
        rx.image(
            src=rx.color_mode_cond(
                light="/cardanoism-new-logo-light.png",
                dark="/cardanoism-new-logo-dark.png",
            ),
            width="100%",
            max_width="13em",
            height="auto",
            alt="カルダノイズム",
            style={"minWidth": "0"},
        ),
        href="/",
        style={
            "flex":     "0 1 13em",  # 基本 13em、足りなければ縮む
            "minWidth": "0",
            "display":  "block",
        },
    )

    divider = rx.box(
        width="1px",
        height="18px",
        background=rx.color_mode_cond("var(--gray-5)", "var(--gray-6)"),
        flex_shrink="0",
    )

    desktop_nav = rx.desktop_only(
        rx.hstack(
            logo,
            divider,
            rx.hstack(
                nav_pill(AuthState.t["nav_home"], "/"),
                nav_with_submenu(
                    AuthState.t["nav_staking"], "/staking",
                    [
                        ("lightbulb",        AuthState.t["staking_subnav_why"],       "/staking/why"),
                        ("layout-dashboard", AuthState.t["staking_subnav_dashboard"], "/staking"),
                        ("server",           AuthState.t["staking_subnav_spo"],       "/staking/spo"),
                    ],
                ),
                nav_with_submenu(
                    AuthState.t["nav_governance"], "/governance",
                    [
                        ("lightbulb",    AuthState.t["gov_subnav_why"],          "/governance/why"),
                        ("gavel",        AuthState.t["gov_subnav_actions"],      "/governance"),
                        ("table-2",      AuthState.t["gov_subnav_matrix"],       "/governance/matrix"),
                        ("landmark",     AuthState.t["gov_subnav_treasury"],     "/governance/treasury"),
                        ("users",        AuthState.t["gov_subnav_drep"],         "/governance/drep"),
                        ("scroll-text",  AuthState.t["gov_subnav_constitution"], "/governance/constitution"),
                    ],
                ),
                nav_with_submenu(
                    AuthState.t["nav_catalyst"], "/catalyst",
                    [
                        ("file-text", AuthState.t["nav_proposals_list"], "/catalyst"),
                        ("layers",    AuthState.t["nav_funds_list"],     "/catalyst/funds"),
                    ],
                ),
                nav_pill(AuthState.t["nav_pricing"], "/pricing"),
                # マイページはログイン時のみ表示
                rx.cond(
                    AuthState.is_logged_in,
                    nav_pill(AuthState.t["nav_mypage"], "/mypage"),
                    rx.fragment(),
                ),
                spacing="1",
                align="center",
            ),
            rx.box(flex="1"),
            rx.hstack(
                fiat_rates_pill(),
                divider,
                rx.cond(
                    WalletState.connected,
                    rx.hstack(
                        wallet_status(),
                        divider,
                        spacing="3",
                        align="center",
                    ),
                    rx.fragment(),
                ),
                auth_section(),
                spacing="3",
                align="center",
            ),
            align_items="center",
            max_width="1130px",
            margin_x="auto",
            width="100%",
            spacing="4",
        ),
    )

    # スマホ用ドロワー: 右からスライドイン。各メインセクションのサブメニューも展開する。
    drawer_trigger = rx.drawer.trigger(
        rx.box(
            rx.icon("menu", size=20, color="var(--gray-11)"),
            padding="6px 8px",
            border_radius="8px",
            cursor="pointer",
            background=rx.color_mode_cond("var(--gray-3)", "var(--gray-4)"),
            _hover={"background": rx.color_mode_cond("var(--gray-4)", "var(--gray-5)")},
            style={"transition": "background 0.15s", "display": "inline-flex", "alignItems": "center"},
        ),
    )

    # × ボタンは右上に絶対配置してメニュー行と被せる (専用行を作らない)
    drawer_close_btn = rx.drawer.close(
        rx.box(
            rx.icon("x", size=20, color="var(--gray-11)"),
            padding="6px 8px",
            border_radius="8px",
            cursor="pointer",
            _hover={"background": rx.color("gray", 3)},
            style={
                "position":    "absolute",
                "top":         "12px",
                "right":       "12px",
                "zIndex":      1,
            },
        ),
    )

    drawer_body = rx.vstack(
        _mobile_drawer_link(AuthState.t["nav_home"], "/", bold=True),
        # ステーキング / ガバナンス / Catalyst はアコーディオン化。
        # type="single" / collapsible=True で 1 つだけ開ける、全閉じ可。
        rx.accordion.root(
            _mobile_drawer_section(
                AuthState.t["nav_staking"], "staking",
                [
                    ("lightbulb",        AuthState.t["staking_subnav_why"],       "/staking/why"),
                    ("layout-dashboard", AuthState.t["staking_subnav_dashboard"], "/staking"),
                    ("server",           AuthState.t["staking_subnav_spo"],       "/staking/spo"),
                ],
            ),
            _mobile_drawer_section(
                AuthState.t["nav_governance"], "governance",
                [
                    ("lightbulb",    AuthState.t["gov_subnav_why"],          "/governance/why"),
                    ("gavel",        AuthState.t["gov_subnav_actions"],      "/governance"),
                    ("table-2",      AuthState.t["gov_subnav_matrix"],       "/governance/matrix"),
                    ("landmark",     AuthState.t["gov_subnav_treasury"],     "/governance/treasury"),
                    ("users",        AuthState.t["gov_subnav_drep"],         "/governance/drep"),
                    ("scroll-text",  AuthState.t["gov_subnav_constitution"], "/governance/constitution"),
                ],
            ),
            _mobile_drawer_section(
                AuthState.t["nav_catalyst"], "catalyst",
                [
                    ("file-text", AuthState.t["nav_proposals_list"], "/catalyst"),
                    ("layers",    AuthState.t["nav_funds_list"],     "/catalyst/funds"),
                ],
            ),
            type="single",
            collapsible=True,
            variant="ghost",  # 余計な背景を抑えて drawer に馴染ませる
            width="100%",
        ),
        _mobile_drawer_link(AuthState.t["nav_pricing"], "/pricing", bold=True),
        rx.cond(
            AuthState.is_logged_in,
            _mobile_drawer_link(AuthState.t["nav_mypage"], "/mypage", bold=True),
            rx.fragment(),
        ),
        spacing="1",
        align_items="stretch",
        width="100%",
        style={"flex": "1", "overflowY": "auto", "paddingTop": "12px"},
    )

    drawer_footer = rx.vstack(
        rx.cond(
            AuthState.is_logged_in,
            rx.drawer.close(
                rx.box(
                    rx.text(
                        AuthState.t["nav_logout"],
                        size="3",
                        weight="medium",
                        color="var(--red-10)",
                        on_click=AuthState.logout,
                        cursor="pointer",
                        style={
                            "padding": "10px 12px",
                            "borderRadius": "8px",
                            "width": "100%",
                            "textAlign": "center",
                        },
                        _hover={"background": rx.color("red", 3)},
                    ),
                    width="100%",
                ),
            ),
            rx.drawer.close(
                rx.link(
                    rx.box(
                        rx.text(
                            AuthState.t["nav_login"],
                            size="3",
                            weight="bold",
                            style={"color": "#111"},
                        ),
                        padding="10px 16px",
                        border_radius="9999px",
                        style={
                            "background": f"linear-gradient(135deg, {ACCENT}, {ACCENT_DARK})",
                            "display":    "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "boxShadow":  "0 2px 8px rgba(255,207,0,0.35)",
                            "width":      "100%",
                        },
                    ),
                    href="/login",
                    underline="none",
                    width="100%",
                ),
            ),
        ),
        spacing="3",
        align_items="stretch",
        width="100%",
        padding_top="12px",
        style={"borderTop": f"1px solid var(--gray-5)"},
    )

    drawer = rx.drawer.root(
        drawer_trigger,
        rx.drawer.overlay(z_index="600"),
        rx.drawer.portal(
            rx.drawer.content(
                drawer_close_btn,
                rx.vstack(
                    drawer_body,
                    drawer_footer,
                    spacing="0",
                    height="100%",
                    width="100%",
                ),
                # Vaul (Radix drawer) は direction="right" の時、配置を自動制御する。
                # top / left / right は "auto" を渡して Vaul に任せ、サイズと装飾のみ指定する。
                top="auto",
                left="auto",
                right="0",
                height="100%",
                width="min(86vw, 340px)",
                padding="20px",
                background_color=rx.color("gray", 1),
                style={
                    "borderLeft":    "1px solid var(--gray-5)",
                    "boxShadow":     "-8px 0 24px rgba(0,0,0,0.18)",
                    "display":       "flex",
                    "flexDirection": "column",
                    "zIndex":        700,
                },
            ),
        ),
        direction="right",
    )

    mobile_nav = rx.mobile_and_tablet(
        rx.hstack(
            logo,
            rx.hstack(
                # ログイン済みのみアバターを表示。未ログインのログインボタンは
                # ドロワーフッターに集約してトップバーをスッキリさせる。
                rx.cond(
                    AuthState.is_logged_in,
                    auth_section(),
                    rx.fragment(),
                ),
                drawer,
                spacing="2",
                align="center",
            ),
            justify_content="space-between",
            align="center",
            width="100%",
        ),
    )

    return rx.box(
        # 不可視: ウォレット接続 React 本体 (auto_reconnect / イベント橋渡しのため常時マウント)
        wallet_connector_mount(),
        desktop_nav,
        mobile_nav,
        padding_x="1.5em",
        padding_y="0.8em",
        position="fixed",
        z_index="500",
        width="100%",
        background=rx.color_mode_cond(
            "rgba(255,255,255,0.80)",
            "rgba(11,11,17,0.80)",
        ),
        style={
            "backdropFilter": "blur(16px)",
            "WebkitBackdropFilter": "blur(16px)",
            "borderBottom": rx.color_mode_cond(
                "1px solid rgba(0,0,0,0.07)",
                "1px solid rgba(255,255,255,0.07)",
            ),
        },
    )
