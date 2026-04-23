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
from cardanoism import styles


# ─── ステータス・タイプ バッジ ─────────────────────────────────────────────────

def ga_status_badge(action: Dict[str, Any]) -> rx.Component:
    return rx.match(
        action["ga_status"],
        ("active",   badge_with_dot(AuthState.t["gov_status_active"],  "white", bg="#22c55e", text_color="white", blink=True)),
        ("ratified", badge_with_dot(AuthState.t["gov_status_ratified"], "white", bg="#073ff4", text_color="white")),
        ("enacted",  badge_with_dot(AuthState.t["gov_status_enacted"],  "white", bg="#4b0082", text_color="white")),
        ("dropped",  badge_with_dot(AuthState.t["gov_status_dropped"],  "white", bg="#808080", text_color="white")),
        ("expired",  badge_with_dot(AuthState.t["gov_status_expired"],  "white", bg="#808080", text_color="white")),
        badge_with_dot(action["ga_status"], "white", bg="#808080", text_color="white"),
    )


def ga_type_badge(action: Dict[str, Any]) -> rx.Component:
    label = rx.match(
        action["proposal_type"],
        ("ParameterChange",    AuthState.t["gov_type_parameter_change"]),
        ("TreasuryWithdrawals", AuthState.t["gov_type_treasury_withdrawals"]),
        ("HardForkInitiation", AuthState.t["gov_type_hard_fork"]),
        ("InfoAction",         AuthState.t["gov_type_info_action"]),
        ("NewCommittee",       AuthState.t["gov_type_new_committee"]),
        ("NewConstitution",    AuthState.t["gov_type_new_constitution"]),
        ("NoConfidence",       AuthState.t["gov_type_no_confidence"]),
        action["proposal_type"],
    )
    return rx.badge(
        label,
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
                "text-[15px] leading-7 prose max-w-none dark:prose-invert "
                "prose-p:text-[var(--gray-12)] dark:prose-p:text-[var(--gray-12)] "
                "prose-strong:text-[var(--gray-12)] dark:prose-strong:text-[var(--gray-12)] "
                "prose-a:text-[var(--amber-11)] dark:prose-a:text-[var(--amber-11)] "
                "prose-headings:text-[var(--gray-12)] dark:prose-headings:text-[var(--gray-12)] "
                "prose-li:text-[var(--gray-12)] dark:prose-li:text-[var(--gray-12)] "
                "prose-code:text-[var(--gray-12)] dark:prose-code:bg-[var(--gray-4)] "
                "prose-blockquote:border-[var(--gray-6)] prose-blockquote:text-[var(--gray-11)]"
            ),
            width="100%",
            padding_x="8px",
            color="var(--gray-12)",
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
            rx.cond(ref["label"], ref["label"], AuthState.t["gov_ref_no_label"]),
            size="3",
            color="var(--gray-10)",
        ),
    )


# ─── 詳細コンテンツ（モーダル・個別ページ共通） ──────────────────────────────

_GOVTOOL_BTN_STYLE = {
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


def governance_detail_header(action: Dict[str, Any], close_btn=None) -> rx.Component:
    """タイトル・バッジ・エポック・リンク行（モーダルの固定ヘッダー部／ページ共通）。
    close_btn: モーダル用の閉じるボタンコンポーネント（ページでは None）。
    """
    title_block = rx.vstack(
        rx.text(
            rx.cond(
                AuthState.language == "en",
                rx.cond(action["title"], action["title"], rx.cond(action["title_ja"], action["title_ja"], AuthState.t["gov_title_none"])),
                rx.cond(action["title_ja"], action["title_ja"], rx.cond(action["title"], action["title"], AuthState.t["gov_title_none"])),
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

    badge_row = rx.hstack(
        ga_status_badge(action),
        ga_type_badge(action),
        spacing="2",
        wrap="wrap",
        align="center",
    )

    epoch_row = rx.hstack(
        rx.cond(
            action["proposed_epoch"],
            rx.hstack(
                rx.icon("calendar", size=14, color="var(--gray-9)"),
                rx.text(AuthState.t["gov_proposed_epoch_label"], size="2", color="var(--gray-9)"),
                rx.text(action["proposed_epoch_display"], size="2", weight="medium"),
                spacing="1",
                align="center",
            ),
            rx.fragment(),
        ),
        rx.cond(
            action["expiration"],
            rx.hstack(
                rx.icon("timer", size=14, color="var(--gray-9)"),
                rx.text(AuthState.t["gov_expiration_label"], size="2", color="var(--gray-9)"),
                rx.text(action["expiration_display"], size="2", weight="medium"),
                spacing="1",
                align="center",
            ),
            rx.fragment(),
        ),
        rx.cond(
            action["deposit_ada"],
            rx.hstack(
                rx.icon("coins", size=14, color="var(--gray-9)"),
                rx.text(AuthState.t["gov_deposit_label"], size="2", color="var(--gray-9)"),
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

    links_row = rx.cond(
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
            style=_GOVTOOL_BTN_STYLE,
        ),
        rx.fragment(),
    )

    title_row = (
        rx.hstack(
            title_block,
            close_btn,
            justify="between",
            align="start",
            width="100%",
        )
        if close_btn is not None
        else title_block
    )

    return rx.vstack(
        title_row,
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
        spacing="3",
        width="100%",
        align_items="stretch",
    )


def governance_detail_body(action: Dict[str, Any], sticky_top: str = "5.5em") -> rx.Component:
    """言語切り替えバー・本文・参考リンク（モーダルのスクロール部／ページ共通）。"""
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
        top=sticky_top,
        z_index="3",
        padding_y="6px",
        width="100%",
        background_color="transparent",
    )

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
            _markdown_section(AuthState.t["gov_section_abstract"], abstract_text),
            rx.fragment(),
        ),
        rx.cond(
            action["motivation_display"],
            _markdown_section(AuthState.t["gov_section_motivation"], motivation_text),
            rx.fragment(),
        ),
        rx.cond(
            action["rationale_display"],
            _markdown_section(AuthState.t["gov_section_rationale"], rationale_text),
            rx.fragment(),
        ),
        spacing="4",
        width="100%",
    )

    refs_section = rx.cond(
        GovernanceState.modal_action_refs,
        rx.vstack(
            _section_heading(AuthState.t["gov_section_refs"]),
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
        lang_toggle,
        body_sections,
        refs_section,
        spacing="4",
        width="100%",
        align_items="stretch",
    )


def governance_detail_content(action: Dict[str, Any]) -> rx.Component:
    """ページ用: ヘッダー＋ボディを結合した完全レイアウト。"""
    return rx.vstack(
        governance_detail_header(action),
        governance_detail_body(action, sticky_top="5.5em"),
        spacing="4",
        width="100%",
        align_items="stretch",
    )


# ─── モーダルダイアログ ────────────────────────────────────────────────────────

def governance_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.html(
                "<style>"
                ".governance-modal, .governance-modal * {"
                "  font-family: " + styles.font_family + ";"
                "  font-size: 15px;"
                "}"
                ".governance-modal .rt-Text {"
                "  font-family: " + styles.font_family + ";"
                "}"
                ".governance-modal .prose {"
                "  font-size: 15px;"
                "}"
                "</style>"
            ),
            rx.vstack(
                # ── 固定ヘッダー: タイトル（＋閉じるボタン）・バッジ・エポック ──
                rx.cond(
                    GovernanceState.modal_action,
                    governance_detail_header(
                        GovernanceState.modal_action,
                        close_btn=rx.dialog.close(
                            rx.button(
                                rx.icon("x"),
                                variant="solid",
                                color_scheme=None,
                                color=rx.color_mode_cond(
                                    light="var(--gray-12)",
                                    dark="var(--gray-2)",
                                ),
                                background_color="var(--amber-9)",
                                style={"_hover": {"background_color": "var(--amber-6)"}},
                                size="2",
                                on_click=GovernanceState.handle_modal_change(False),
                                cursor="pointer",
                                flex_shrink="0",
                            ),
                        ),
                    ),
                    rx.fragment(),
                ),
                # ── スクロール領域（本文のみ）────────────────────────────────
                rx.box(
                    rx.cond(
                        GovernanceState.modal_loading,
                        rx.flex(rx.spinner(size="3"), justify="center", align="center", padding_y="40px"),
                        rx.cond(
                            GovernanceState.modal_action,
                            governance_detail_body(GovernanceState.modal_action, sticky_top="0px"),
                            rx.callout(AuthState.t["gov_modal_load_error"], icon="info", color_scheme="gray"),
                        ),
                    ),
                    flex="1",
                    min_height="0",
                    overflow_y="auto",
                    padding_right="6px",
                    width="100%",
                ),
                # ── フッター（固定）──────────────────────────────────────────
                rx.hstack(
                    rx.button(
                        AuthState.t["proposal_close"],
                        on_click=GovernanceState.handle_modal_change(False),
                        width="90%",
                        variant="soft",
                        cursor="pointer",
                    ),
                    rx.menu.root(
                        rx.menu.trigger(
                            rx.icon("share-2", size=20, variant="soft", color="var(--gray-8)", cursor="pointer"),
                        ),
                        rx.menu.content(
                            rx.menu.item(
                                "X (Twitter)",
                                on_click=rx.call_script(
                                    "const t = document.querySelector('.ga-title')?.innerText ?? '';"
                                    "const url = 'https://x.com/intent/tweet'"
                                    "  + '?text=' + encodeURIComponent(t)"
                                    "  + '&url=' + encodeURIComponent(window.location.href);"
                                    "window.open(url,'x-share',"
                                    "'width=550,height=420,menubar=no,toolbar=no,"
                                    "location=no,status=no,resizable=yes,scrollbars=yes');"
                                ),
                            ),
                            rx.menu.item(
                                "LINE",
                                on_click=rx.call_script(
                                    "const t = document.querySelector('.ga-title')?.innerText ?? '';"
                                    "const url = 'https://social-plugins.line.me/lineit/share'"
                                    "  + '?url=' + encodeURIComponent(window.location.href)"
                                    "  + '&text=' + encodeURIComponent(t);"
                                    "window.open(url,'line-share',"
                                    "'width=520,height=520,menubar=no,toolbar=no,"
                                    "location=no,status=no,resizable=yes,scrollbars=yes');"
                                ),
                            ),
                            rx.menu.item(
                                AuthState.t["proposal_copy_url"],
                                on_click=[
                                    rx.call_script("navigator.clipboard.writeText(window.location.href);"),
                                    rx.toast(
                                        AuthState.t["gov_url_copied"],
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
                    rx.box(
                        rx.cond(
                            AuthState.ga_favorite_ids.contains(
                                GovernanceState.modal_action["proposal_tx_hash"].to(str)
                            ),
                            rx.icon("heart", size=26, color="var(--red-9)", style={"fill": "var(--red-9)"}),
                            rx.icon("heart", size=26, color="var(--gray-8)"),
                        ),
                        on_click=AuthState.toggle_ga_favorite(
                            GovernanceState.modal_action["proposal_tx_hash"].to(str)
                        ),
                        cursor="pointer",
                        padding="6px",
                        display="flex",
                        align_items="center",
                    ),
                    width="100%",
                    align="center",
                    padding_top="12px",
                    flex_shrink="0",
                ),
                spacing="3",
                width="100%",
                align_items="stretch",
                height="100%",
                min_height="0",
            ),
            max_width=["100vw", "100vw", "900px"],
            width=["100vw", "100vw", "95vw"],
            max_height=["100vh", "100vh", "95vh"],
            height=["100vh", "100vh", "auto"],
            padding="24px",
            class_name="governance-modal",
            style={"display": "flex", "flexDirection": "column"},
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
                rx.text(action["proposed_epoch_display"], size="2", color="var(--gray-10)"),
                spacing="1",
                align="center",
            ),
            rx.fragment(),
        ),
        rx.cond(
            action["expiration"],
            rx.hstack(
                rx.icon("timer", size=14, color="var(--gray-8)"),
                rx.text(AuthState.t["gov_expiration_label"], size="2", color="var(--gray-10)"),
                rx.text(action["expiration_display"], size="2", color="var(--gray-10)"),
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
    tx_hash = action["proposal_tx_hash"].to(str)
    return rx.box(
        rx.cond(
            AuthState.ga_favorite_ids.contains(tx_hash),
            rx.icon("heart", size=22, color="var(--red-9)", style={"fill": "var(--red-9)"}),
            rx.icon("heart", size=22, color="var(--gray-8)"),
        ),
        on_click=AuthState.toggle_ga_favorite(tx_hash),
        cursor="pointer",
        padding="4px",
        flex_shrink="0",
    )


def ga_list_card(action: Dict[str, Any]) -> rx.Component:
    content = rx.hstack(
        rx.vstack(
            rx.hstack(
                ga_status_badge(action),
                ga_type_badge(action),
                spacing="2",
                wrap="wrap",
                align="center",
            ),
            rx.text(
                rx.cond(
                    AuthState.language == "en",
                    rx.cond(action["title"], action["title"], action["title_ja"]),
                    rx.cond(action["title_ja"], action["title_ja"], action["title"]),
                ),
                size="4",
                weight="bold",
                line_height="1.2",
                color="var(--gray-12)",
                class_name="ga-title proposal-title",
            ),
            rx.cond(
                action["abstract_display"],
                rx.text(
                    rx.cond(
                        AuthState.language == "en",
                        rx.cond(action["abstract"], action["abstract"], action["abstract_ja"]),
                        rx.cond(action["abstract_ja"], action["abstract_ja"], action["abstract"]),
                    ),
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
            on_click=[GovernanceState.open_modal(action), GovernanceState.reset_modal_lang_for_language(AuthState.language)],
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
                ga_status_badge(action),
                ga_type_badge(action),
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
            rx.cond(
                AuthState.language == "en",
                rx.cond(action["title"], action["title"], action["title_ja"]),
                rx.cond(action["title_ja"], action["title_ja"], action["title"]),
            ),
            size="3",
            weight="bold",
            color="var(--gray-12)",
            class_name="ga-title proposal-title",
        ),
        rx.cond(
            action["abstract_display"],
            rx.text(
                rx.cond(
                    AuthState.language == "en",
                    rx.cond(action["abstract"], action["abstract"], action["abstract_ja"]),
                    rx.cond(action["abstract_ja"], action["abstract_ja"], action["abstract"]),
                ),
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
            on_click=[GovernanceState.open_modal(action), GovernanceState.reset_modal_lang_for_language(AuthState.language)],
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
