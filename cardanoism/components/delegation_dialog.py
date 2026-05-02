"""Phase 3: 委任先変更の確認ダイアログ。

ステーキングページの SPO カードから「委任する」を押した時に開く。
WalletState.delegate_target_pool に対象プールが入った状態で
WalletState.delegate_dialog_open=True に変化すると表示される。

現在委任中のプールがあれば「現在 → 変更先」の比較レイアウト。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.wallet_state import WalletState


def _section_label(text) -> rx.Component:
    """カード上部のセクションラベル (委任ウォレット / 現在の委任先 等)。

    text は文字列でも i18n の Var でも可。
    """
    return rx.text(
        text,
        size="2",
        color="var(--gray-10)",
        weight="bold",
        style={"letterSpacing": "0.04em"},
    )


def _pool_card_compact(
    pool,
    label,
    border_color: str,
    bg: str,
) -> rx.Component:
    """プール 1 件をコンパクトにまとめたカード (現在 / 変更先 で使い回し)。"""
    return rx.box(
        rx.vstack(
            _section_label(label),
            rx.hstack(
                rx.cond(
                    pool["pool_icon_url"].to(str) != "",
                    rx.image(
                        src=pool["pool_icon_url"],
                        width="44px", height="44px",
                        border_radius="999px",
                        object_fit="cover",
                        flex_shrink="0",
                        custom_attrs={"referrerpolicy": "no-referrer"},
                    ),
                    rx.box(
                        rx.icon("hexagon", size=22, color="var(--gray-9)"),
                        width="44px", height="44px",
                        border_radius="999px",
                        background="var(--gray-3)",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        flex_shrink="0",
                    ),
                ),
                rx.vstack(
                    rx.text(
                        rx.cond(pool["ticker"].to(str) != "", pool["ticker"], "—"),
                        size="4", weight="bold", color="var(--gray-12)",
                    ),
                    rx.text(
                        rx.cond(
                            pool["pool_name"].to(str) != "",
                            pool["pool_name"],
                            AuthState.t["delegate_pool_unnamed"],
                        ),
                        size="2",
                        color="var(--gray-11)",
                        style={
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                            "whiteSpace": "nowrap",
                            "maxWidth": "100%",
                        },
                    ),
                    spacing="0",
                    align_items="start",
                    flex="1",
                    min_width="0",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.text(
                pool["pool_id_bech32"],
                color="var(--gray-9)",
                style={
                    "fontFamily": "ui-monospace, monospace",
                    "fontSize": "12px",
                    "wordBreak": "break-all",
                    "lineHeight": "1.4",
                },
            ),
            rx.hstack(
                rx.text(
                    AuthState.t["delegate_label_saturation"],
                    size="2", color="var(--gray-9)",
                ),
                rx.text(
                    pool["saturation_pct"],
                    size="2", weight="medium",
                    color="var(--gray-12)",
                ),
                rx.text("·", size="2", color="var(--gray-7)"),
                rx.text(
                    AuthState.t["delegate_label_delegators"],
                    size="2", color="var(--gray-9)",
                ),
                rx.text(
                    pool["delegators_text"],
                    size="2", color="var(--gray-12)",
                ),
                spacing="2", align="center", wrap="wrap",
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding="16px 18px",
        border_radius="12px",
        border=f"1px solid {border_color}",
        background=bg,
        flex="1",
        min_width="0",
    )


def _comparison_section() -> rx.Component:
    """現在 → 変更先 (もしくは新規委任のみ) のセクション。"""
    has_current = (
        WalletState.delegate_current_pool["pool_id_bech32"].to(str) != ""
    )

    current_card = _pool_card_compact(
        WalletState.delegate_current_pool,
        AuthState.t["delegate_label_current"],
        "var(--gray-5)",
        rx.color_mode_cond("white", "rgba(255,255,255,0.02)"),
    )
    target_card = _pool_card_compact(
        WalletState.delegate_target_pool,
        AuthState.t["delegate_label_new_target"],
        "var(--amber-7)",
        "var(--amber-2)",
    )
    target_card_new = _pool_card_compact(
        WalletState.delegate_target_pool,
        AuthState.t["delegate_label_first_target"],
        "var(--amber-7)",
        "var(--amber-2)",
    )

    arrow = rx.icon(
        "arrow-right",
        size=26,
        color="var(--amber-9)",
        style={"flexShrink": "0"},
    )

    return rx.cond(
        has_current,
        rx.flex(
            current_card,
            arrow,
            target_card,
            direction={"base": "column", "md": "row"},
            align="center",
            gap="3",
            width="100%",
        ),
        target_card_new,
    )


def _wallet_info() -> rx.Component:
    return rx.box(
        rx.vstack(
            _section_label(AuthState.t["delegate_label_wallet"]),
            rx.hstack(
                rx.box(
                    width="10px", height="10px",
                    border_radius="999px",
                    background="var(--green-9)",
                    flex_shrink="0",
                    style={"boxShadow": "0 0 0 3px rgba(34,197,94,0.18)"},
                ),
                rx.vstack(
                    rx.text(
                        WalletState.wallet_label,
                        size="4", weight="bold",
                        color="var(--gray-12)",
                    ),
                    rx.text(
                        WalletState.reward_address,
                        color="var(--gray-10)",
                        style={
                            "fontFamily": "ui-monospace, monospace",
                            "fontSize": "12px",
                            "wordBreak": "break-all",
                            "lineHeight": "1.4",
                        },
                    ),
                    spacing="1", align_items="start", flex="1", min_width="0",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding="16px 20px",
        border_radius="12px",
        border="1px solid var(--gray-5)",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.02)"),
        width="100%",
    )


def delegation_dialog() -> rx.Component:
    """委任先変更の確認モーダル。"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                AuthState.t["delegate_modal_title"],
                size="5",
            ),
            rx.dialog.description(
                AuthState.t["delegate_modal_desc"],
                size="3",
                color_scheme="gray",
            ),

            rx.vstack(
                _wallet_info(),
                _comparison_section(),
                # 注意書き
                rx.hstack(
                    rx.icon("info", size=16, color="var(--gray-10)", flex_shrink="0"),
                    rx.text(
                        AuthState.t["delegate_fee_note"],
                        size="2", color="var(--gray-10)", line_height="1.6",
                    ),
                    spacing="2", align="start", width="100%",
                ),
                spacing="4",
                width="100%",
                padding_top="16px",
            ),

            rx.flex(
                rx.dialog.close(
                    rx.button(
                        AuthState.t["delegate_btn_cancel"],
                        size="3",
                        variant="soft",
                        color_scheme="gray",
                        on_click=WalletState.close_delegate_dialog,
                        cursor="pointer",
                    ),
                ),
                rx.button(
                    rx.cond(
                        WalletState.delegating,
                        rx.spinner(size="2"),
                        rx.icon("send", size=16),
                    ),
                    rx.text(
                        rx.cond(
                            WalletState.delegating,
                            AuthState.t["delegate_btn_submitting"],
                            AuthState.t["delegate_btn_submit"],
                        ),
                        size="3",
                    ),
                    size="3",
                    on_click=WalletState.submit_delegation,
                    disabled=WalletState.delegating,
                    cursor="pointer",
                    color_scheme="amber",
                ),
                gap="3",
                margin_top="20px",
                justify="end",
            ),

            max_width="720px",
            padding="28px",
        ),
        open=WalletState.delegate_dialog_open,
        on_open_change=WalletState.on_delegate_dialog_open_change,
    )
