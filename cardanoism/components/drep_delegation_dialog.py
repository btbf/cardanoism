"""DRep 委任 (CIP-1694 vote delegation) の確認ダイアログ。

ガバナンス DRep 一覧の「委任する」を押した時に開く。
WalletState.delegate_target_drep に対象 DRep が入った状態で
WalletState.delegate_drep_dialog_open=True に変化すると表示される。

現在委任中の DRep があれば「現在 → 変更先」の比較レイアウト。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.wallet_state import WalletState


def _section_label(text) -> rx.Component:
    return rx.text(
        text,
        size="2",
        color="var(--gray-10)",
        weight="bold",
        style={"letterSpacing": "0.04em"},
    )


def _drep_card_compact(
    drep,
    label,
    border_color: str,
    bg: str,
) -> rx.Component:
    """DRep 1 件をコンパクトにまとめたカード (現在 / 変更先 で使い回し)。"""
    avatar = rx.cond(
        drep["image_url"].to(str) != "",
        rx.image(
            src=drep["image_url"],
            width="44px", height="44px",
            border_radius="999px",
            object_fit="cover",
            flex_shrink="0",
            custom_attrs={"referrerpolicy": "no-referrer"},
        ),
        rx.box(
            rx.icon("user-round", size=22, color="var(--gray-9)"),
            width="44px", height="44px",
            border_radius="999px",
            background="var(--gray-3)",
            display="flex",
            align_items="center",
            justify_content="center",
            flex_shrink="0",
        ),
    )
    # Always Abstain / Always No Confidence は dreps テーブルに無いので
    # drep_id ベースで i18n 表示する (常に棄権 / Always Abstain など)。
    name_text = rx.match(
        drep["drep_id"].to(str),
        ("always_abstain", rx.text(
            AuthState.t["drep_special_always_abstain"],
            size="4", weight="bold", color="var(--gray-12)",
        )),
        ("always_no_confidence", rx.text(
            AuthState.t["drep_special_always_no_confidence"],
            size="4", weight="bold", color="var(--gray-12)",
        )),
        rx.cond(
            drep["given_name"].to(str) != "",
            rx.text(
                drep["given_name"],
                size="4", weight="bold", color="var(--gray-12)",
                style={"wordBreak": "break-word"},
            ),
            rx.text(
                AuthState.t["drep_delegate_unnamed"],
                size="4", weight="bold", color="var(--gray-10)",
            ),
        ),
    )
    return rx.box(
        rx.vstack(
            _section_label(label),
            rx.hstack(
                avatar,
                rx.vstack(
                    name_text,
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
                drep["drep_id"],
                color="var(--gray-9)",
                style={
                    "fontFamily": "ui-monospace, monospace",
                    "fontSize": "12px",
                    "wordBreak": "break-all",
                    "lineHeight": "1.4",
                },
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
    has_current = (
        WalletState.delegate_current_drep["drep_id"].to(str) != ""
    )

    current_card = _drep_card_compact(
        WalletState.delegate_current_drep,
        AuthState.t["delegate_label_current"],
        "var(--gray-5)",
        rx.color_mode_cond("white", "rgba(255,255,255,0.02)"),
    )
    target_card = _drep_card_compact(
        WalletState.delegate_target_drep,
        AuthState.t["delegate_label_new_target"],
        "var(--amber-7)",
        "var(--amber-2)",
    )
    target_card_new = _drep_card_compact(
        WalletState.delegate_target_drep,
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


def drep_delegation_dialog() -> rx.Component:
    """DRep 委任 (CIP-1694) の確認モーダル。"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                AuthState.t["drep_delegate_modal_title"],
                size="5",
            ),
            rx.dialog.description(
                AuthState.t["drep_delegate_modal_desc"],
                size="3",
                color_scheme="gray",
            ),

            rx.vstack(
                _wallet_info(),
                _comparison_section(),
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
                        on_click=WalletState.close_drep_delegate_dialog,
                        cursor="pointer",
                    ),
                ),
                rx.button(
                    rx.cond(
                        WalletState.delegating_drep,
                        rx.spinner(size="2"),
                        rx.icon("send", size=16),
                    ),
                    rx.text(
                        rx.cond(
                            WalletState.delegating_drep,
                            AuthState.t["delegate_btn_submitting"],
                            AuthState.t["delegate_btn_submit"],
                        ),
                        size="3",
                    ),
                    size="3",
                    on_click=WalletState.submit_drep_delegation,
                    disabled=WalletState.delegating_drep,
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
        open=WalletState.delegate_drep_dialog_open,
        on_open_change=WalletState.on_drep_delegate_dialog_open_change,
    )
