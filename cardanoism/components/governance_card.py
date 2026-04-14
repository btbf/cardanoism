"""
governance_card.py
ガバナンスアクション一覧カード・モーダルダイアログ
カタリストページのスタイルに統一
"""
import reflex as rx
from typing import Dict, Any

from cardanoism.backend.db_connect import GovernanceState
from cardanoism.backend.auth_state import AuthState
from cardanoism.components.proposal_card import badge_with_dot


# ─── ステータス・タイプ バッジ ─────────────────────────────────────────────────

def ga_status_badge(action: Dict[str, Any]) -> rx.Component:
    return rx.match(
        action["ga_status"],
        ("active",   badge_with_dot("アクティブ", "white", bg="#22c55e", text_color="white", blink=True)),
        ("ratified", badge_with_dot("批准済み",   "white", bg="#073ff4", text_color="white")),
        ("enacted",  badge_with_dot("施行済み",   "white", bg="#4b0082", text_color="white")),
        ("dropped",  badge_with_dot("廃止",       "white", bg="#808080", text_color="white")),
        ("expired",  badge_with_dot("失効",       "white", bg="#808080", text_color="white")),
        badge_with_dot(action["ga_status"], "white", bg="#808080", text_color="white"),
    )


def ga_type_badge(action: Dict[str, Any]) -> rx.Component:
    return rx.badge(
        action["proposal_type_display"],
        color_scheme=action["proposal_type_color"],
        variant="surface",
        radius="full",
        size="2",
    )


# ─── セクション見出し（カタリスト detail と同一） ─────────────────────────────

def _section_heading(label: str) -> rx.Component:
    return rx.el.h2(
        label,
        class_name=(
            "text-[16px] md:text-[16px] font-semibold tracking-tight "
            "text-[var(--gray-12)] pb-1 border-b border-[var(--gray-5)] "
            "border-l-4 border-[var(--gray-6)] pl-3"
        ),
    )


def _markdown_section(label: str, text_var) -> rx.Component:
    """マークダウンをHTMLにレンダリングするセクション（カタリスト html_section と同スタイル）。"""
    return rx.vstack(
        _section_heading(label),
        rx.box(
            rx.markdown(text_var),
            class_name=(
                "text-[16px] leading-7 prose max-w-none "
                "prose-strong:text-[var(--gray-12)] dark:prose-strong:text-[var(--gray-12)] "
                "prose-a:text-[var(--amber-11)] prose-headings:text-[var(--gray-12)]"
            ),
            width="100%",
            padding_x="8px",
            color="var(--sand-a12)",
        ),
        spacing="2",
        width="100%",
    )


# ─── References リスト ────────────────────────────────────────────────────────

def _ref_item(ref: Dict[str, Any]) -> rx.Component:
    return rx.cond(
        ref["uri"],
        rx.link(
            rx.hstack(
                rx.icon("external-link", size=14),
                rx.text(
                    rx.cond(ref["label"], ref["label"], ref["uri"]),
                    size="3",
                ),
                spacing="1",
                align="center",
            ),
            href=ref["uri"],
            is_external=True,
            underline="auto",
            color="var(--amber-11)",
        ),
        rx.text(
            rx.cond(ref["label"], ref["label"], "（ラベルなし）"),
            size="3",
            color="var(--gray-10)",
        ),
    )


# ─── 詳細コンテンツ（モーダル・個別ページ共通） ──────────────────────────────

def governance_detail_content(action: Dict[str, Any]) -> rx.Component:
    # 言語切り替えバー（カタリストの semantic_toggle_bar と同スタイル）
    lang_toggle = rx.box(
        rx.center(
            rx.box(
                rx.hstack(
                    rx.button(
                        "日本語",
                        size="2",
                        radius="full",
                        variant=rx.cond(GovernanceState.modal_lang == "ja", "solid", "soft"),
                        color_scheme=rx.cond(GovernanceState.modal_lang == "ja", "blue", "gray"),
                        padding_x="14px",
                        padding_y="7px",
                        class_name=(
                            "transition-all duration-200 "
                            "shadow-[0_6px_16px_rgba(0,0,0,0.08)] "
                            "hover:shadow-[0_8px_18px_rgba(0,0,0,0.12)] text-[13px]"
                        ),
                        on_click=GovernanceState.set_modal_lang("ja"),
                        cursor="pointer",
                    ),
                    rx.button(
                        "English",
                        size="2",
                        radius="full",
                        variant=rx.cond(GovernanceState.modal_lang == "en", "solid", "soft"),
                        color_scheme=rx.cond(GovernanceState.modal_lang == "en", "blue", "gray"),
                        padding_x="14px",
                        padding_y="7px",
                        class_name=(
                            "transition-all duration-200 "
                            "shadow-[0_6px_16px_rgba(0,0,0,0.08)] "
                            "hover:shadow-[0_8px_18px_rgba(0,0,0,0.12)] text-[13px]"
                        ),
                        on_click=GovernanceState.set_modal_lang("en"),
                        cursor="pointer",
                    ),
                    spacing="2",
                    align="end",
                    margin_y="6px",
                ),
                background_color="var(--gray-2)",
                padding="8px 18px",
                border_radius="9999px",
            ),
        ),
        position="sticky",
        top="5.5em",
        z_index="3",
        padding_y="6px",
        width="100%",
        background_color="transparent",
    )

    # タイトル（カタリスト proposal_detail と同一サイズ）
    title_block = rx.vstack(
        rx.text(
            rx.cond(
                action["title_ja"],
                action["title_ja"],
                rx.cond(action["title"], action["title"], "（タイトルなし）"),
            ),
            size={"base": "6", "md": "5"},
            weight="bold",
            width="100%",
            style={"wordBreak": "break-word"},
            class_name="ga-title proposal-title",
        ),
        rx.cond(
            action["title"],
            rx.text(action["title"], size="2", width="100%", style={"wordBreak": "break-word"}),
            rx.fragment(),
        ),
        spacing="1",
        align_items="start",
        width="100%",
    )

    # バッジ行
    badge_row = rx.hstack(
        ga_type_badge(action),
        ga_status_badge(action),
        spacing="2",
        wrap="wrap",
        align="center",
    )

    # エポック・デポジット情報
    epoch_row = rx.hstack(
        rx.cond(
            action["proposed_epoch"],
            rx.hstack(
                rx.icon("calendar", size=14, color="var(--gray-9)"),
                rx.text("提案エポック: ", size="2", color="var(--gray-9)"),
                rx.text(action["proposed_epoch"], size="2", weight="medium"),
                spacing="1",
                align="center",
            ),
            rx.fragment(),
        ),
        rx.cond(
            action["expiration"],
            rx.hstack(
                rx.icon("timer", size=14, color="var(--gray-9)"),
                rx.text("期限エポック: ", size="2", color="var(--gray-9)"),
                rx.text(action["expiration"], size="2", weight="medium"),
                spacing="1",
                align="center",
            ),
            rx.fragment(),
        ),
        rx.cond(
            action["deposit_ada"],
            rx.hstack(
                rx.icon("coins", size=14, color="var(--gray-9)"),
                rx.text("デポジット: ", size="2", color="var(--gray-9)"),
                rx.text(action["deposit_ada"], size="2", weight="medium"),
                rx.text("ADA", size="2", color="var(--gray-9)"),
                spacing="1",
                align="center",
            ),
            rx.fragment(),
        ),
        spacing="4",
        wrap="wrap",
        align="center",
    )

    # リンク行
    _btn_style = {
        "display": "inline-flex",
        "align_items": "center",
        "gap": "4px",
        "padding": "4px 10px",
        "border_radius": "6px",
        "font_size": "13px",
        "font_weight": "500",
        "cursor": "pointer",
        "border": "1px solid var(--gray-5)",
        "background": "var(--gray-2)",
        "color": "var(--gray-11)",
        "text_decoration": "none",
        "_hover": {"background": "var(--gray-4)"},
    }

    favorite_btn = rx.cond(
        AuthState.ga_favorite_ids.contains(action["proposal_tx_hash"]),
        rx.icon_button(
            rx.icon("heart", size=16),
            variant="soft",
            color_scheme="red",
            size="2",
            cursor="pointer",
            on_click=AuthState.toggle_ga_favorite(action["proposal_tx_hash"]),
        ),
        rx.icon_button(
            rx.icon("heart", size=16),
            variant="ghost",
            color_scheme="gray",
            size="2",
            cursor="pointer",
            on_click=AuthState.toggle_ga_favorite(action["proposal_tx_hash"]),
        ),
    )

    links_row = rx.hstack(
        rx.cond(
            action["govtool_url"],
            rx.link(
                rx.hstack(
                    rx.text("Gov Tool", size="1"),
                    rx.icon("external-link", size=12),
                    spacing="1",
                    align="center",
                ),
                href=action["govtool_url"],
                is_external=True,
                underline="none",
                style=_btn_style,
            ),
            rx.fragment(),
        ),
        rx.menu.root(
            rx.menu.trigger(
                rx.box(
                    rx.hstack(
                        rx.text("シェア", size="1"),
                        rx.icon("share-2", size=12),
                        spacing="1",
                        align="center",
                    ),
                    style=_btn_style,
                ),
            ),
            rx.menu.content(
                rx.menu.item(
                    "X (Twitter)",
                    on_click=rx.call_script(
                        "const t = document.querySelector('.ga-title')?.innerText ?? '';"
                        "const url = 'https://x.com/intent/tweet'"
                        "  + '?text=' + encodeURIComponent(t)"
                        "  + '&url=' + encodeURIComponent(window.location.href);"
                        "window.open(url,'x-share','width=550,height=420,menubar=no,toolbar=no,"
                        "location=no,status=no,resizable=yes,scrollbars=yes');"
                    ),
                ),
                rx.menu.item(
                    "URLコピー",
                    on_click=[
                        rx.call_script("navigator.clipboard.writeText(window.location.href);"),
                        rx.toast(
                            "リンクをコピーしました",
                            position="top-center",
                            style={
                                "background-color": "var(--indigo-11)",
                                "color": "white",
                                "border-radius": "0.5rem",
                            },
                        ),
                    ],
                ),
            ),
        ),
        favorite_btn,
        spacing="2",
        wrap="wrap",
        align="center",
    )

    # 本文（言語切り替え対応）
    def text_ja_or_en(ja_key: str, en_key: str):
        return rx.cond(
            GovernanceState.modal_lang == "ja",
            rx.cond(action[ja_key], action[ja_key], rx.cond(action[en_key], action[en_key], "")),
            rx.cond(action[en_key], action[en_key], rx.cond(action[ja_key], action[ja_key], "")),
        )

    abstract_text   = text_ja_or_en("abstract_ja",  "abstract")
    motivation_text = text_ja_or_en("motivation_ja", "motivation")
    rationale_text  = text_ja_or_en("rationale_ja",  "rationale")

    body_sections = rx.vstack(
        rx.cond(
            action["abstract_display"],
            _markdown_section("概要", abstract_text),
            rx.fragment(),
        ),
        rx.cond(
            action["motivation_display"],
            _markdown_section("動機", motivation_text),
            rx.fragment(),
        ),
        rx.cond(
            action["rationale_display"],
            _markdown_section("根拠", rationale_text),
            rx.fragment(),
        ),
        spacing="4",
        width="100%",
    )

    refs_section = rx.cond(
        GovernanceState.modal_action_refs,
        rx.vstack(
            _section_heading("参考リンク"),
            rx.vstack(
                rx.foreach(GovernanceState.modal_action_refs, _ref_item),
                spacing="2",
                padding_x="8px",
            ),
            spacing="2",
            width="100%",
        ),
        rx.fragment(),
    )

    return rx.vstack(
        title_block,
        rx.hstack(
            badge_row,
            links_row,
            justify="between",
            align="center",
            width="100%",
            wrap="wrap",
            spacing="2",
        ),
        epoch_row,
        rx.divider(),
        lang_toggle,
        rx.vstack(
            body_sections,
            refs_section,
            spacing="3",
            width="100%",
        ),
        spacing="4",
        width="100%",
        align_items="stretch",
    )


# ─── モーダルダイアログ ────────────────────────────────────────────────────────

def governance_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.heading("ガバナンスアクション詳細", size="4"),
                rx.dialog.close(
                    rx.icon_button(
                        rx.icon("x", size=16),
                        variant="ghost",
                        color_scheme="gray",
                        size="2",
                        cursor="pointer",
                        on_click=lambda: GovernanceState.handle_modal_change(False),
                    ),
                ),
                justify="between",
                align="center",
                width="100%",
                padding_bottom="8px",
            ),
            rx.cond(
                GovernanceState.modal_loading,
                rx.flex(rx.spinner(size="3"), justify="center", align="center", padding_y="40px"),
                rx.cond(
                    GovernanceState.modal_action,
                    governance_detail_content(GovernanceState.modal_action),
                    rx.callout("詳細を読み込めませんでした", icon="info", color_scheme="gray"),
                ),
            ),
            rx.hstack(
                rx.dialog.close(
                    rx.button(
                        "閉じる",
                        on_click=lambda: GovernanceState.handle_modal_change(False),
                        width="100%",
                        variant="soft",
                        cursor="pointer",
                    ),
                ),
                width="100%",
                padding_top="16px",
            ),
            max_width="780px",
            width="95vw",
            max_height="90vh",
            overflow_y="auto",
            padding="24px",
            class_name="governance-modal",
        ),
        open=GovernanceState.modal_open,
        on_open_change=GovernanceState.handle_modal_change,
    )


# ─── 一覧カード ────────────────────────────────────────────────────────────────

def _card_footer(action: Dict[str, Any]) -> rx.Component:
    """エポック・デポジット情報（カードフッター）。"""
    return rx.hstack(
        rx.cond(
            action["proposed_epoch"],
            rx.hstack(
                rx.icon("calendar", size=14, color="var(--gray-9)"),
                rx.text(action["proposed_epoch"], size="2", color="var(--gray-10)"),
                spacing="1",
                align="center",
            ),
            rx.fragment(),
        ),
        rx.cond(
            action["expiration"],
            rx.hstack(
                rx.icon("timer", size=14, color="var(--gray-8)"),
                rx.text("期限:", size="2", color="var(--gray-10)"),
                rx.text(action["expiration"], size="2", color="var(--gray-10)"),
                spacing="1",
                align="center",
            ),
            rx.fragment(),
        ),
        rx.cond(
            action["deposit_ada"],
            rx.hstack(
                rx.icon("coins", size=14, color="var(--gray-8)"),
                rx.text(action["deposit_ada"], size="2", weight="bold", color="var(--indigo-11)"),
                rx.text("ADA", size="2", color="var(--gray-9)"),
                spacing="1",
                align="center",
            ),
            rx.fragment(),
        ),
        justify="start",
        align="center",
        spacing="3",
        wrap="wrap",
        width="100%",
    )


_CARD_CLASS_LIGHT = (
    "transition-all duration-300 overflow-hidden "
    "hover:shadow-[0_0_8px_rgba(0,0,0,0.22)]"
)
_CARD_CLASS_DARK = (
    "transition-all duration-300 overflow-hidden "
    "hover:shadow-[0_0_6px_rgba(229,229,229,0.12)]"
)


def _ga_fav_btn_list(action: Dict[str, Any]) -> rx.Component:
    return rx.cond(
        AuthState.ga_favorite_ids.contains(action["proposal_tx_hash"]),
        rx.icon_button(
            rx.icon("heart", size=15),
            variant="soft",
            color_scheme="red",
            size="1",
            cursor="pointer",
            on_click=AuthState.toggle_ga_favorite(action["proposal_tx_hash"]),
        ),
        rx.icon_button(
            rx.icon("heart", size=15),
            variant="ghost",
            color_scheme="gray",
            size="1",
            cursor="pointer",
            on_click=AuthState.toggle_ga_favorite(action["proposal_tx_hash"]),
        ),
    )


def ga_list_card(action: Dict[str, Any]) -> rx.Component:
    content = rx.hstack(
        rx.vstack(
            rx.hstack(
                ga_type_badge(action),
                ga_status_badge(action),
                spacing="2",
                wrap="wrap",
                align="center",
            ),
            rx.text(
                action["title_display"],
                size="4",
                weight="bold",
                line_height="1.2",
                color="var(--gray-12)",
                class_name="ga-title proposal-title",
            ),
            rx.cond(
                action["abstract_display"],
                rx.text(
                    action["abstract_display"],
                    size="3",
                    line_height="1.6",
                    text_wrap="wrap",
                    class_name="mt-2 line-clamp-3",
                    min_height="3.6em",
                    color="var(--gray-12)",
                ),
                rx.fragment(),
            ),
            _card_footer(action),
            spacing="3",
            flex="1",
            min_width="0",
            on_click=GovernanceState.open_modal(action),
            cursor="pointer",
        ),
        rx.box(
            _ga_fav_btn_list(action),
            flex_shrink="0",
            padding_top="2px",
        ),
        align="start",
        spacing="2",
        width="100%",
    )

    return rx.card(
        content,
        width="100%",
        margin_bottom="1.5em",
        padding="18px",
        background_color="var(--gray-3)",
        min_height=["250px", "250px", "200px"],
        class_name=rx.color_mode_cond(light=_CARD_CLASS_LIGHT, dark=_CARD_CLASS_DARK),
    )


def ga_grid_card(action: Dict[str, Any]) -> rx.Component:
    content_block = rx.vstack(
        rx.hstack(
            rx.hstack(
                ga_type_badge(action),
                ga_status_badge(action),
                spacing="2",
                wrap="wrap",
                align="center",
                flex="1",
                min_width="0",
            ),
            _ga_fav_btn_list(action),
            align="start",
            spacing="2",
            width="100%",
        ),
        rx.text(
            action["title_display"],
            size="3",
            weight="bold",
            color="var(--gray-12)",
            class_name="ga-title proposal-title",
        ),
        rx.cond(
            action["abstract_display"],
            rx.text(
                action["abstract_display"],
                size="2",
                color="var(--gray-12)",
                line_height="1.6",
                text_wrap="wrap",
                class_name="line-clamp-3 mt-1",
            ),
            rx.fragment(),
        ),
        spacing="3",
        width="100%",
    )

    return rx.card(
        rx.vstack(
            content_block,
            _card_footer(action),
            spacing="3",
            width="100%",
            height="100%",
            justify="between",
            on_click=GovernanceState.open_modal(action),
            cursor="pointer",
        ),
        width="100%",
        padding="18px",
        background_color="var(--gray-3)",
        class_name=rx.color_mode_cond(light=_CARD_CLASS_LIGHT, dark=_CARD_CLASS_DARK),
    )


def ga_cards_view(view_mode) -> rx.Component:
    list_view = rx.vstack(
        rx.foreach(GovernanceState.actions, ga_list_card),
        spacing="0",
        width="100%",
    )
    grid_view = rx.grid(
        rx.foreach(GovernanceState.actions, ga_grid_card),
        columns={"base": "1", "sm": "2", "lg": "3"},
        spacing="3",
        width="100%",
    )
    return rx.cond(view_mode == "list", list_view, grid_view)
