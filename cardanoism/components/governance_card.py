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
from cardanoism.components.governance_ai_analysis import ai_analysis_section
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

    # 投票期限カウントダウン（上部 badge_row と同じ高さ・スタイルで揃える）
    deadline_badge = rx.match(
        GovernanceState.modal_deadline_status,
        ("active", rx.box(
            rx.hstack(
                rx.icon("timer", size=14, color="white"),
                rx.text(AuthState.t["gov_deadline_remaining"], size="1", color="white", weight="medium"),
                rx.text(GovernanceState.modal_deadline_days.to_string(), size="2", weight="bold", color="white"),
                rx.text(AuthState.t["gov_deadline_days"], size="1", color="white"),
                spacing="1", align="center",
            ),
            padding="3px 10px",
            background="linear-gradient(90deg, var(--blue-9), var(--indigo-9))",
            border_radius="999px",
            display="inline-flex",
            align_items="center",
            line_height="1",
        )),
        ("urgent", rx.box(
            rx.hstack(
                rx.icon("timer", size=14, color="white"),
                rx.text(AuthState.t["gov_deadline_remaining"], size="1", color="white", weight="medium"),
                rx.text(GovernanceState.modal_deadline_days.to_string(), size="2", weight="bold", color="white"),
                rx.text(AuthState.t["gov_deadline_days"], size="1", color="white"),
                rx.badge(AuthState.t["gov_deadline_urgent"], color_scheme=None,
                         background_color="var(--ruby-12)", color="white", size="1"),
                spacing="1", align="center",
            ),
            padding="3px 10px",
            background="linear-gradient(90deg, var(--ruby-9), var(--ruby-11))",
            border_radius="999px",
            box_shadow="0 0 0 0 rgba(239, 68, 68, 0.7)",
            animation="cdn_deadline_pulse 1.6s ease-in-out infinite",
            display="inline-flex",
            align_items="center",
            line_height="1",
        )),
        rx.fragment(),
    )

    badge_row = rx.hstack(
        rx.html(
            "<style>"
            "@keyframes cdn_deadline_pulse {"
            "  0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.55); }"
            "  70%      { box-shadow: 0 0 0 6px rgba(239,68,68,0); }"
            "}"
            "</style>"
        ),
        ga_status_badge(action),
        ga_type_badge(action),
        deadline_badge,
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


def _localized_text(ja_key: str, en_key: str, action: Dict[str, Any]) -> rx.Component:
    """AuthState.language に応じて ja/en を出し分ける。片方が空ならもう一方をフォールバック。"""
    return rx.cond(
        AuthState.language == "en",
        rx.cond(action[en_key], action[en_key], action[ja_key]),
        rx.cond(action[ja_key], action[ja_key], action[en_key]),
    )


def _has_any_text(ja_key: str, en_key: str, action: Dict[str, Any]):
    """ja / en のどちらかに値があるかを返す（rx.cond の条件用）。"""
    return rx.cond(action[ja_key], action[ja_key], action[en_key])


def _fiat_inline(jpy_var, usd_var, size: str = "2", color: str = "var(--gray-10)") -> rx.Component:
    """ADA の後ろに括弧付きで法定通貨を併記（言語連動）。空なら非表示。"""
    jpy_part = rx.cond(
        jpy_var != "",
        rx.text("(≈ ", jpy_var, ")", size=size, color=color),
        rx.fragment(),
    )
    usd_part = rx.cond(
        usd_var != "",
        rx.text("(≈ ", usd_var, ")", size=size, color=color),
        rx.fragment(),
    )
    return rx.cond(AuthState.language == "en", usd_part, jpy_part)


def _withdrawal_entry_row(entry) -> rx.Component:
    """内訳1行（受取ステークアドレス + 金額 + 法定通貨）。"""
    return rx.hstack(
        rx.code(entry["stake_address_short"], size="1"),
        rx.text("→", size="2", color="var(--gray-8)"),
        rx.text(entry["amount_ada_display"], size="2", weight="medium"),
        rx.text("ADA", size="1", color="var(--gray-10)"),
        _fiat_inline(
            entry["amount_jpy_display"],
            entry["amount_usd_display"],
            size="1",
        ),
        spacing="2", align="center", wrap="wrap",
    )


def _mini_donut(label, yes_pct, yes_pct_donut, no_pct, abstain_pct, threshold_pct, status, donut_bg, applicable) -> rx.Component:
    """一覧カード用のミニドーナツ（YES/NO/Abstain を一目で把握できる円グラフ）。

    yes_pct        : 凡例表示用 (小数点1位)
    yes_pct_donut  : 中央表示用 (整数。狭い円内で 100.0 等が縁に被るのを回避)
    """
    donut = rx.box(
        rx.box(
            width="56px",
            height="56px",
            border_radius="50%",
            background=donut_bg,
            transition="background 0.3s ease",
        ),
        rx.center(
            rx.hstack(
                rx.text(yes_pct_donut, weight="bold", color="var(--gray-12)", style={"fontSize": "14px", "lineHeight": "1"}),
                rx.text("%", style={"fontSize": "10px", "color": "var(--gray-10)", "lineHeight": "1"}),
                spacing="0", align="baseline",
            ),
            position="absolute",
            top="50%", left="50%",
            transform="translate(-50%, -50%)",
            width="42px", height="42px",
            border_radius="50%",
            background="var(--gray-2)",
        ),
        position="relative",
        width="56px",
        height="56px",
        flex_shrink="0",
    )

    detail = rx.vstack(
        rx.text(label, weight="bold", color="var(--gray-12)", style={"fontSize": "11px"}),
        rx.cond(
            threshold_pct != "",
            rx.hstack(
                rx.text(AuthState.t["gov_vote_threshold_label"], style={"fontSize": "9px", "color": "var(--gray-10)"}),
                rx.text(threshold_pct + "%", style={"fontSize": "10px", "color": "var(--gray-12)", "fontWeight": "500"}),
                spacing="1", align="baseline",
            ),
            rx.fragment(),
        ),
        rx.hstack(
            rx.box(width="6px", height="6px", background="var(--blue-9)", border_radius="1px", flex_shrink="0"),
            rx.text("Yes", style={"fontSize": "9px", "color": "var(--gray-10)"}),
            rx.text(yes_pct + "%", style={"fontSize": "10px", "color": "var(--blue-11)", "fontWeight": "600"}),
            spacing="1", align="baseline",
        ),
        rx.hstack(
            rx.box(width="6px", height="6px", background="var(--orange-9)", border_radius="1px", flex_shrink="0"),
            rx.text("No", style={"fontSize": "9px", "color": "var(--gray-10)"}),
            rx.text(no_pct + "%", style={"fontSize": "10px", "color": "var(--orange-11)", "fontWeight": "600"}),
            spacing="1", align="baseline",
        ),
        spacing="0",
        align="start",
        flex="1",
        min_width="0",
    )

    normal = rx.hstack(
        donut,
        detail,
        spacing="2",
        align="center",
        flex="1",
        min_width="150px",
    )

    disabled = rx.hstack(
        rx.box(
            rx.center(
                rx.icon("ban", size=18, color="var(--gray-8)"),
                position="absolute",
                top="50%", left="50%",
                transform="translate(-50%, -50%)",
                width="36px", height="36px",
                border_radius="50%",
                background="var(--gray-2)",
            ),
            position="relative",
            width="56px",
            height="56px",
            border_radius="50%",
            background="var(--gray-4)",
            flex_shrink="0",
            style={"opacity": "0.6"},
        ),
        rx.vstack(
            rx.text(label, weight="bold", color="var(--gray-9)", style={"fontSize": "11px"}),
            rx.text(AuthState.t["gov_vote_not_applicable"], style={"fontSize": "9px", "color": "var(--gray-9)"}),
            spacing="0",
            align="start",
            flex="1",
            min_width="0",
        ),
        spacing="2",
        align="center",
        flex="1",
        min_width="150px",
    )

    return rx.cond(applicable == "no", disabled, normal)


def _vote_summary_inline(action: Dict[str, Any]) -> rx.Component:
    """一覧カード用のコンパクト投票サマリ（3ロールのミニドーナツ横並び）。voting_summary なしなら非表示。"""
    return rx.cond(
        action["has_voting_summary"].to(str) != "",
        rx.hstack(
            _mini_donut(
                AuthState.t["gov_voter_drep"],
                action["drep_yes_pct"].to(str),
                action["drep_yes_pct_donut"].to(str),
                action["drep_no_pct"].to(str),
                action["drep_abstain_pct"].to(str),
                action["drep_threshold_pct"].to(str),
                action["drep_status"].to(str),
                action["drep_donut_bg"].to(str),
                action["drep_applicable"].to(str),
            ),
            _mini_donut(
                AuthState.t["gov_voter_cc"],
                action["cc_yes_pct"].to(str),
                action["cc_yes_pct_donut"].to(str),
                action["cc_no_pct"].to(str),
                action["cc_abstain_pct"].to(str),
                action["cc_threshold_pct"].to(str),
                action["cc_status"].to(str),
                action["cc_donut_bg"].to(str),
                action["cc_applicable"].to(str),
            ),
            _mini_donut(
                AuthState.t["gov_voter_spo"],
                action["pool_yes_pct"].to(str),
                action["pool_yes_pct_donut"].to(str),
                action["pool_no_pct"].to(str),
                action["pool_abstain_pct"].to(str),
                action["pool_threshold_pct"].to(str),
                action["pool_status"].to(str),
                action["pool_donut_bg"].to(str),
                action["pool_applicable"].to(str),
            ),
            spacing="3",
            align="center",
            wrap="wrap",
            width="100%",
        ),
        rx.fragment(),
    )


def _withdrawal_inline(action: Dict[str, Any]) -> rx.Component:
    """カード一覧用のコンパクトな引き出し額表示（1 行）。TreasuryWithdrawals のみ表示。"""
    return rx.cond(
        action["is_treasury_withdrawal"].to(bool),
        rx.hstack(
            rx.icon("landmark", size=14, color="var(--amber-11)"),
            rx.text(
                action["withdrawal_total_ada_display"].to(str),
                size="2", weight="bold", color="var(--amber-11)",
            ),
            rx.text("ADA", size="1", color="var(--gray-10)"),
            _fiat_inline(
                action["withdrawal_total_jpy_display"].to(str),
                action["withdrawal_total_usd_display"].to(str),
                size="1",
            ),
            spacing="2", align="center", wrap="wrap",
        ),
        rx.fragment(),
    )


def _withdrawal_section(action: Dict[str, Any]) -> rx.Component:
    """TreasuryWithdrawals の場合のみ表示される引き出し額セクション。"""
    return rx.cond(
        action["is_treasury_withdrawal"].to(bool),
        rx.vstack(
            _section_heading(AuthState.t["gov_section_withdrawal"]),
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.icon("landmark", size=22, color="var(--amber-11)"),
                        rx.text(action["withdrawal_total_ada_display"].to(str), size="7", weight="bold", color="var(--amber-11)"),
                        rx.text("ADA", size="3", color="var(--gray-11)"),
                        _fiat_inline(
                            action["withdrawal_total_jpy_display"].to(str),
                            action["withdrawal_total_usd_display"].to(str),
                            size="2",
                        ),
                        spacing="2", align="baseline", wrap="wrap",
                    ),
                    rx.cond(
                        action["withdrawal_list"].to(list).length() > 1,
                        rx.vstack(
                            rx.text(
                                AuthState.t["gov_withdrawal_breakdown"],
                                size="2", weight="medium", color="var(--gray-11)",
                                padding_top="8px",
                            ),
                            rx.foreach(
                                action["withdrawal_list"].to(list[dict[str, str]]),
                                _withdrawal_entry_row,
                            ),
                            spacing="1", align="start", width="100%",
                        ),
                        rx.fragment(),
                    ),
                    spacing="2", align="start", width="100%",
                ),
                padding="16px",
                border=f"1px solid {rx.color('gray', 4)}",
                border_radius="10px",
                background="var(--gray-2)",
                width="100%",
            ),
            spacing="2", align="start", width="100%",
        ),
        rx.fragment(),
    )


def _donut_chart(role_label, yes_pct, yes_pct_donut, no_pct, abstain_pct, threshold, status, donut_bg, applicable) -> rx.Component:
    """1つの役割のドーナツチャート。中央に Yes%、下に閾値と状態バッジ。
    applicable: "yes" = 通常表示 / "no" = グレーアウト / "conditional" = 条件付き注釈付き
    """
    status_badge = rx.match(
        status,
        ("passed", rx.badge(AuthState.t["gov_vote_passed"], color_scheme="green", variant="soft", size="1")),
        ("failed", rx.badge(AuthState.t["gov_vote_failed"], color_scheme="red",   variant="soft", size="1")),
        rx.fragment(),
    )

    # 通常のコンテンツ
    normal_content = rx.vstack(
        rx.text(role_label, size="2", weight="bold", color="var(--gray-12)"),
        rx.box(
            rx.box(
                width="140px",
                height="140px",
                border_radius="50%",
                background=donut_bg,
                transition="background 0.3s ease",
            ),
            rx.center(
                rx.vstack(
                    rx.text("Yes", size="1", color="var(--gray-10)"),
                    rx.hstack(
                        rx.text(yes_pct_donut, size="6", weight="bold", color="var(--gray-12)"),
                        rx.text("%", size="2", color="var(--gray-11)"),
                        spacing="0", align="baseline",
                    ),
                    spacing="0", align="center",
                ),
                position="absolute",
                top="50%", left="50%",
                transform="translate(-50%, -50%)",
                width="96px", height="96px",
                border_radius="50%",
                background="var(--gray-2)",
            ),
            position="relative",
            width="140px",
            height="140px",
        ),
        rx.cond(
            threshold != "",
            rx.hstack(
                rx.text(AuthState.t["gov_vote_threshold_label"], size="1", color="var(--gray-10)"),
                rx.text(threshold, size="2", weight="medium", color="var(--gray-12)"),
                rx.text("%", size="1", color="var(--gray-10)"),
                spacing="1", align="baseline",
            ),
            rx.text(AuthState.t["gov_vote_no_threshold"], size="1", color="var(--gray-9)"),
        ),
        # conditional（ParameterChange の SPO など）の注釈
        rx.cond(
            applicable == "conditional",
            rx.badge(
                AuthState.t["gov_vote_conditional"],
                color_scheme="amber",
                variant="soft",
                size="1",
            ),
            status_badge,
        ),
        rx.vstack(
            rx.hstack(
                rx.text("No:", size="1", color="var(--gray-10)"),
                rx.text(no_pct + "%", size="1", color="var(--orange-11)", weight="medium"),
                spacing="1", align="baseline",
            ),
            rx.hstack(
                rx.text("Abstain:", size="1", color="var(--gray-10)"),
                rx.text(abstain_pct + "%", size="1", color="var(--gray-11)"),
                spacing="1", align="baseline",
            ),
            spacing="1", align="center",
        ),
        spacing="2",
        align="center",
    )

    # 対象外（グレーアウト）
    disabled_content = rx.vstack(
        rx.text(role_label, size="2", weight="bold", color="var(--gray-9)"),
        rx.box(
            rx.box(
                width="140px",
                height="140px",
                border_radius="50%",
                background="var(--gray-4)",
            ),
            rx.center(
                rx.vstack(
                    rx.icon("ban", size=28, color="var(--gray-8)"),
                    rx.text(AuthState.t["gov_vote_not_applicable"], size="1", color="var(--gray-9)"),
                    spacing="1", align="center",
                ),
                position="absolute",
                top="50%", left="50%",
                transform="translate(-50%, -50%)",
                width="96px", height="96px",
                border_radius="50%",
                background="var(--gray-2)",
            ),
            position="relative",
            width="140px",
            height="140px",
        ),
        spacing="2",
        align="center",
        style={"opacity": "0.6"},
    )

    return rx.box(
        rx.cond(applicable == "no", disabled_content, normal_content),
        padding="12px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        min_width="150px",
        flex="1",
    )


def _cc_member_row(m) -> rx.Component:
    """CC メンバー 1 名の投票行。スクロール不要になるようコンパクト表示。"""
    identity = rx.cond(
        m["display_name"] != "",
        rx.text(m["display_name"], size="1", weight="medium", color="var(--gray-12)"),
        rx.text(
            m["show_id_short"],
            style={
                "fontFamily": "var(--code-font-family, ui-monospace, monospace)",
                "fontSize": "10px",
                "color": "var(--gray-11)",
            },
        ),
    )
    vote_ui = rx.cond(
        m["has_voted"] != "",
        _vote_badge(m["vote"]),
        rx.badge(AuthState.t["gov_vote_not_voted"], color_scheme="gray", variant="outline", size="1"),
    )
    return rx.hstack(
        rx.box(identity, flex="1", min_width="0"),
        vote_ui,
        spacing="2",
        align="center",
        width="100%",
    )


def _cc_vote_card(action: Dict[str, Any]) -> rx.Component:
    """CC はメンバー数が少ないので円グラフではなく個別投票リストで表示。"""
    cc_applicable = action["cc_applicable"].to(str)
    cc_threshold = action["cc_threshold_pct"].to(str)
    cc_status = action["cc_status"].to(str)
    cc_yes_pct = action["cc_yes_pct"].to(str)

    status_badge = rx.match(
        cc_status,
        ("passed", rx.badge(AuthState.t["gov_vote_passed"], color_scheme="green", variant="soft", size="1")),
        ("failed", rx.badge(AuthState.t["gov_vote_failed"], color_scheme="red",   variant="soft", size="1")),
        rx.fragment(),
    )

    normal_content = rx.vstack(
        rx.text(AuthState.t["gov_voter_cc"], size="2", weight="bold", color="var(--gray-12)"),
        rx.hstack(
            rx.text("Yes ", size="1", color="var(--gray-10)"),
            rx.text(cc_yes_pct, size="3", weight="bold", color="var(--green-11)"),
            rx.text("%", size="1", color="var(--gray-11)"),
            rx.cond(
                cc_threshold != "",
                rx.hstack(
                    rx.text("/", size="1", color="var(--gray-9)"),
                    rx.text(cc_threshold, size="2", weight="medium", color="var(--gray-12)"),
                    rx.text("%", size="1", color="var(--gray-10)"),
                    spacing="1", align="baseline",
                ),
                rx.fragment(),
            ),
            spacing="1", align="baseline", wrap="wrap",
        ),
        status_badge,
        # メンバー別投票リスト（全件表示・コンパクト）
        rx.box(
            rx.cond(
                GovernanceState.modal_cc_votes,
                rx.vstack(
                    rx.foreach(
                        GovernanceState.modal_cc_votes.to(list[dict[str, str]]),
                        _cc_member_row,
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.text(AuthState.t["gov_vote_no_members"], size="1", color="var(--gray-9)"),
            ),
            width="100%",
            padding_top="4px",
        ),
        spacing="2",
        align="start",
        width="100%",
    )

    disabled_content = rx.vstack(
        rx.text(AuthState.t["gov_voter_cc"], size="2", weight="bold", color="var(--gray-9)"),
        rx.center(
            rx.vstack(
                rx.icon("ban", size=28, color="var(--gray-8)"),
                rx.text(AuthState.t["gov_vote_not_applicable"], size="1", color="var(--gray-9)"),
                spacing="1", align="center",
            ),
            width="100%",
            min_height="140px",
        ),
        spacing="2",
        align="center",
        width="100%",
        style={"opacity": "0.6"},
    )

    return rx.box(
        rx.cond(cc_applicable == "no", disabled_content, normal_content),
        padding="12px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        min_width="220px",
        flex="1.3",
    )


def _voting_summary_section(action: Dict[str, Any]) -> rx.Component:
    """DRep / CC / SPO の3ドーナツを横並びで表示。見出しの右隣に投票状況への遷移ボタン。"""
    return rx.cond(
        action["has_voting_summary"].to(str) != "",
        rx.vstack(
            rx.hstack(
                rx.box(_section_heading(AuthState.t["gov_section_voting_summary"]), flex="1"),
                _votes_anchor_button(),
                spacing="2",
                align="center",
                width="100%",
                wrap="wrap",
            ),
            rx.hstack(
                _donut_chart(
                    AuthState.t["gov_voter_drep"],
                    action["drep_yes_pct"].to(str),
                    action["drep_yes_pct_donut"].to(str),
                    action["drep_no_pct"].to(str),
                    action["drep_abstain_pct"].to(str),
                    action["drep_threshold_pct"].to(str),
                    action["drep_status"].to(str),
                    action["drep_donut_bg"].to(str),
                    action["drep_applicable"].to(str),
                ),
                _cc_vote_card(action),
                _donut_chart(
                    AuthState.t["gov_voter_spo"],
                    action["pool_yes_pct"].to(str),
                    action["pool_yes_pct_donut"].to(str),
                    action["pool_no_pct"].to(str),
                    action["pool_abstain_pct"].to(str),
                    action["pool_threshold_pct"].to(str),
                    action["pool_status"].to(str),
                    action["pool_donut_bg"].to(str),
                    action["pool_applicable"].to(str),
                ),
                spacing="3",
                wrap="wrap",
                width="100%",
                justify="center",
                align="stretch",
            ),
            spacing="2", align="start", width="100%",
        ),
        rx.fragment(),
    )


def _vote_badge(vote_var) -> rx.Component:
    """Yes / No / Abstain のバッジ（アイコン + ソリッドカラーで強調）。"""
    return rx.match(
        vote_var,
        ("Yes", rx.badge(
            rx.hstack(
                rx.icon("check", size=14, stroke_width=3),
                rx.text("Yes", weight="bold"),
                spacing="1", align="center",
            ),
            color_scheme="green", variant="solid", size="2", radius="full",
        )),
        ("No", rx.badge(
            rx.hstack(
                rx.icon("x", size=14, stroke_width=3),
                rx.text("No", weight="bold"),
                spacing="1", align="center",
            ),
            color_scheme="red", variant="solid", size="2", radius="full",
        )),
        ("Abstain", rx.badge(
            rx.hstack(
                rx.icon("minus", size=14, stroke_width=3),
                rx.text("Abstain", weight="bold"),
                spacing="1", align="center",
            ),
            color_scheme="gray", variant="soft", size="2", radius="full",
        )),
        rx.badge(vote_var, variant="soft"),
    )


def _role_badge(role_var) -> rx.Component:
    """DRep / ConstitutionalCommittee / SPO のバッジ。"""
    return rx.match(
        role_var,
        ("DRep",                     rx.badge("DRep", color_scheme="blue",   variant="soft")),
        ("ConstitutionalCommittee",  rx.badge("CC",   color_scheme="violet", variant="soft")),
        ("SPO",                      rx.badge("SPO",  color_scheme="amber",  variant="soft")),
        rx.badge(role_var, variant="soft"),
    )


def _vote_row(v) -> rx.Component:
    """投票 1 行。ロール / 投票者（DRep名+小さい省略ID）/ 投票 / 日時 / 理由（有れば）。"""
    rationale_text = rx.cond(
        v["rationale_ja"] != "",
        v["rationale_ja"],
        v["rationale"],
    )
    has_rationale = rx.cond(
        v["rationale_ja"] != "",
        True,
        v["rationale"] != "",
    )
    # DRep 名があれば名前を大きく、省略 ID を下に小さく表示。
    # 名前が空（CC/SPO や名前未設定 DRep）の場合は省略 ID のみ。
    voter_cell = rx.cond(
        v["voter_name"] != "",
        rx.vstack(
            rx.text(
                v["voter_name"],
                size="2", weight="medium", color="var(--gray-12)",
                style={"wordBreak": "break-word"},
            ),
            rx.text(
                v["voter_id_short"],
                size="1",
                color="var(--gray-9)",
                style={"fontFamily": "var(--code-font-family, ui-monospace, monospace)", "fontSize": "10px"},
            ),
            spacing="0", align="start",
        ),
        rx.text(
            v["voter_id_short"],
            size="1",
            color="var(--gray-11)",
            style={"fontFamily": "var(--code-font-family, ui-monospace, monospace)"},
        ),
    )
    return rx.table.row(
        rx.table.cell(_role_badge(v["voter_role"])),
        rx.table.cell(voter_cell),
        rx.table.cell(_vote_badge(v["vote"])),
        rx.table.cell(
            rx.text(v["block_time"], size="1", color="var(--gray-10)"),
        ),
        rx.table.cell(
            rx.cond(
                has_rationale,
                rx.dialog.root(
                    rx.dialog.trigger(
                        rx.button(
                            AuthState.t["gov_vote_rationale_view"],
                            variant="soft",
                            color_scheme="blue",
                            size="1",
                            cursor="pointer",
                        ),
                    ),
                    rx.dialog.content(
                        rx.dialog.title(AuthState.t["gov_vote_rationale_title"]),
                        rx.vstack(
                            # 投票者情報
                            rx.hstack(
                                _role_badge(v["voter_role"]),
                                rx.cond(
                                    v["voter_name"] != "",
                                    rx.text(v["voter_name"], size="2", weight="medium"),
                                    rx.fragment(),
                                ),
                                _vote_badge(v["vote"]),
                                spacing="2", align="center", wrap="wrap",
                            ),
                            rx.text(
                                v["voter_id_short"],
                                size="1", color="var(--gray-10)",
                                style={"fontFamily": "var(--code-font-family, ui-monospace, monospace)"},
                            ),
                            rx.divider(),
                            # 日本語訳（あれば）
                            rx.cond(
                                v["rationale_ja"] != "",
                                rx.vstack(
                                    rx.text(AuthState.t["gov_vote_rationale_ja_label"], size="2", weight="bold", color="var(--gray-12)"),
                                    rx.text(
                                        v["rationale_ja"],
                                        size="2", color="var(--gray-12)",
                                        style={"whiteSpace": "pre-wrap", "lineHeight": "1.6"},
                                    ),
                                    spacing="1", align="start", width="100%",
                                ),
                                rx.fragment(),
                            ),
                            # 原文
                            rx.cond(
                                v["rationale"] != "",
                                rx.vstack(
                                    rx.text(AuthState.t["gov_vote_rationale_en_label"], size="2", weight="bold", color="var(--gray-12)"),
                                    rx.text(
                                        v["rationale"],
                                        size="2", color="var(--gray-11)",
                                        style={"whiteSpace": "pre-wrap", "lineHeight": "1.6"},
                                    ),
                                    spacing="1", align="start", width="100%",
                                ),
                                rx.fragment(),
                            ),
                            rx.dialog.close(
                                rx.button(
                                    AuthState.t["gov_vote_rationale_close"],
                                    variant="soft",
                                    size="2",
                                    cursor="pointer",
                                ),
                            ),
                            spacing="3", align="start", width="100%",
                        ),
                        max_width=["95vw", "95vw", "680px"],
                    ),
                ),
                rx.text("—", size="1", color="var(--gray-8)"),
            ),
        ),
    )


def _vote_section(action: Dict[str, Any]) -> rx.Component:
    """投票一覧セクション。1 テーブルにロール混在で表示。
    id='votes' をアンカー対象にして、上部のボタンからジャンプできるようにする。
    テーブルは max-height でスクロール可能。
    """
    return rx.cond(
        GovernanceState.modal_votes,
        rx.vstack(
            _section_heading(AuthState.t["gov_section_votes"]),
            rx.box(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell(AuthState.t["gov_vote_col_role"]),
                            rx.table.column_header_cell(AuthState.t["gov_vote_col_voter"]),
                            rx.table.column_header_cell(AuthState.t["gov_vote_col_vote"]),
                            rx.table.column_header_cell(AuthState.t["gov_vote_col_time"]),
                            rx.table.column_header_cell(AuthState.t["gov_vote_col_rationale"]),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(
                            GovernanceState.modal_votes.to(list[dict[str, str]]),
                            _vote_row,
                        ),
                    ),
                    variant="surface",
                    size="1",
                ),
                id="votes",
                width="100%",
                max_height="820px",
                overflow_y="auto",
                overflow_x="auto",
                border=f"1px solid {rx.color('gray', 5)}",
                border_radius="8px",
            ),
            spacing="2", align="start", width="100%",
        ),
        rx.fragment(),
    )


def _votes_anchor_button() -> rx.Component:
    """投票セクションへのアンカーボタン（本文上部に配置）。モーダル/ページ両対応で JS で scrollIntoView。"""
    return rx.cond(
        GovernanceState.modal_votes,
        rx.button(
            rx.icon("vote", size=14),
            rx.text(AuthState.t["gov_anchor_votes"], size="2", weight="medium"),
            on_click=rx.call_script(
                "document.getElementById('votes')?.scrollIntoView({behavior:'smooth', block:'start'});"
            ),
            variant="soft",
            color_scheme="blue",
            size="2",
            cursor="pointer",
        ),
        rx.fragment(),
    )


def _user_drep_vote_row(v) -> rx.Component:
    """1 件の登録ステークアドレス → 委任先 DRep → 投票結果カード。"""
    drep_name = rx.cond(v["drep_name"] != "", v["drep_name"], v["drep_id"])

    # 全文ダイアログ: 概要をクリックすると開く
    full_rationale_dialog = rx.dialog.root(
        rx.dialog.trigger(
            rx.box(
                rx.text(
                    v["rationale_short"],
                    size="1", color="var(--gray-10)",
                    line_height="1.5",
                    style={
                        "wordBreak": "break-word",
                        "cursor": "pointer",
                        "transition": "color 0.15s",
                    },
                    _hover={"color": "var(--gray-12)"},
                ),
                rx.hstack(
                    rx.icon("maximize-2", size=10, color="var(--amber-11)"),
                    rx.text(
                        AuthState.t["gov_vote_rationale_view"],
                        size="1", color="var(--amber-11)", weight="medium",
                    ),
                    spacing="1", align="center",
                    style={"marginTop": "4px"},
                ),
                style={"flex": "1", "minWidth": "0", "cursor": "pointer"},
            ),
        ),
        rx.dialog.content(
            rx.dialog.title(AuthState.t["gov_vote_rationale_title"]),
            rx.vstack(
                rx.hstack(
                    rx.icon("user-check", size=14, color="var(--violet-11)"),
                    rx.text(drep_name, size="2", weight="medium"),
                    _vote_badge(v["vote"]),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.divider(),
                rx.text(
                    v["rationale"],
                    size="2", color="var(--gray-12)",
                    style={"whiteSpace": "pre-wrap", "lineHeight": "1.6"},
                ),
                # 閉じるボタンを右下に配置
                rx.flex(
                    rx.dialog.close(
                        rx.button(
                            AuthState.t["gov_vote_rationale_close"],
                            variant="soft",
                            size="2",
                            cursor="pointer",
                        ),
                    ),
                    justify="end",
                    width="100%",
                ),
                spacing="3", align="start", width="100%",
            ),
            max_width=["95vw", "95vw", "680px"],
        ),
    )

    voted_block = rx.hstack(
        _vote_badge(v["vote"]),
        rx.cond(
            v["rationale_short"] != "",
            full_rationale_dialog,
            rx.text(
                AuthState.t["gov_user_drep_no_rationale"],
                size="1", color="var(--gray-9)",
                style={"fontStyle": "italic"},
            ),
        ),
        spacing="2",
        align="center",
        wrap="wrap",
        width="100%",
    )
    not_voted_block = rx.hstack(
        rx.icon("clock", size=14, color="var(--gray-9)"),
        rx.text(
            AuthState.t["gov_user_drep_not_voted"],
            size="2", color="var(--gray-10)",
        ),
        spacing="2",
        align="center",
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("wallet", size=14, color="var(--amber-11)"),
                rx.text(v["nickname"], size="2", weight="bold", color="var(--gray-12)"),
                rx.icon("arrow-right", size=12, color="var(--gray-9)"),
                rx.icon("user-check", size=12, color="var(--violet-11)"),
                rx.text(drep_name, size="2", weight="medium", color="var(--gray-12)",
                        style={"wordBreak": "break-word"}),
                spacing="2", align="center", wrap="wrap",
            ),
            rx.cond(
                v["has_voted"] != "",
                voted_block,
                not_voted_block,
            ),
            spacing="2", align="start", width="100%",
        ),
        padding="12px 14px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="10px",
        background="var(--gray-2)",
        width="100%",
    )


def _user_drep_votes_card() -> rx.Component:
    """ログインユーザーの委任先 DRep の投票一覧。
    未ログイン時は非表示、ログイン済みで委任先が無ければ案内、ある場合はカードリスト。
    """
    head = rx.hstack(
        rx.icon("user-check", size=18, color="var(--violet-11)"),
        rx.text(
            AuthState.t["gov_user_drep_title"],
            size="3", weight="bold", color="var(--gray-12)",
        ),
        spacing="2", align="center", width="100%",
    )

    list_body = rx.vstack(
        rx.foreach(GovernanceState.modal_user_drep_votes, _user_drep_vote_row),
        spacing="2",
        width="100%",
        align_items="stretch",
    )

    return rx.cond(
        AuthState.is_logged_in,
        rx.cond(
            GovernanceState.modal_user_drep_votes.length() > 0,
            rx.box(
                rx.vstack(
                    head,
                    list_body,
                    spacing="3",
                    width="100%",
                    align_items="stretch",
                ),
                padding="16px 20px",
                border=f"1px solid {rx.color('violet', 5)}",
                border_radius="12px",
                background="var(--violet-2)",
                width="100%",
            ),
            rx.fragment(),
        ),
        rx.fragment(),
    )


def governance_detail_body(action: Dict[str, Any]) -> rx.Component:
    """本文・参考リンク（モーダルのスクロール部／ページ共通）。言語はグローバル AuthState.language に連動。"""
    abstract_text   = _localized_text("abstract_ja",  "abstract",  action)
    motivation_text = _localized_text("motivation_ja", "motivation", action)
    rationale_text  = _localized_text("rationale_ja",  "rationale",  action)

    body_sections = rx.vstack(
        # ログインユーザーの委任先 DRep の投票（最優先で表示）
        _user_drep_votes_card(),
        _withdrawal_section(action),
        # 投票集計（ドーナツ + CC メンバーリスト）は概要より先に表示。右隣に投票状況へジャンプボタン
        _voting_summary_section(action),
        # AI 分析セクション
        ai_analysis_section(),
        rx.cond(
            _has_any_text("abstract_ja", "abstract", action),
            _markdown_section(AuthState.t["gov_section_abstract"], abstract_text),
            rx.fragment(),
        ),
        rx.cond(
            _has_any_text("motivation_ja", "motivation", action),
            _markdown_section(AuthState.t["gov_section_motivation"], motivation_text),
            rx.fragment(),
        ),
        rx.cond(
            _has_any_text("rationale_ja", "rationale", action),
            _markdown_section(AuthState.t["gov_section_rationale"], rationale_text),
            rx.fragment(),
        ),
        # 投票状況は本文の下部に配置
        _vote_section(action),
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
        governance_detail_body(action),
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
                            governance_detail_body(GovernanceState.modal_action),
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
                                GovernanceState.modal_action["proposal_id"].to(str)
                            ),
                            rx.icon("heart", size=26, color="var(--red-9)", style={"fill": "var(--red-9)"}),
                            rx.icon("heart", size=26, color="var(--gray-8)"),
                        ),
                        on_click=AuthState.toggle_ga_favorite(
                            GovernanceState.modal_action["proposal_id"].to(str)
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
            background_color="var(--gray-3)",
            style={"display": "flex", "flexDirection": "column"},
        ),
        open=GovernanceState.modal_open,
        on_open_change=GovernanceState.handle_modal_change,
    )


# ─── 一覧カード ────────────────────────────────────────────────────────────────

def _date_chips(action: Dict[str, Any]) -> rx.Component:
    """提案エポック / 期限エポックを上部バッジ列に並べるための小チップ。"""
    proposed_chip = rx.cond(
        action["proposed_epoch"],
        rx.hstack(
            rx.icon("calendar", size=12, color="var(--gray-9)"),
            rx.text(AuthState.t["gov_proposed_epoch_label"], size="1", color="var(--gray-10)"),
            rx.text(action["proposed_epoch_display"], size="1", color="var(--gray-11)"),
            spacing="1",
            align="center",
            style={
                "padding": "2px 8px",
                "borderRadius": "999px",
                "background": "var(--gray-3)",
                "border": "1px solid var(--gray-4)",
                "whiteSpace": "nowrap",
            },
        ),
        rx.fragment(),
    )
    expiration_chip = rx.cond(
        action["expiration"],
        rx.hstack(
            rx.icon("timer", size=12, color="var(--gray-9)"),
            rx.text(AuthState.t["gov_expiration_label"], size="1", color="var(--gray-10)"),
            rx.text(action["expiration_display"], size="1", color="var(--gray-11)"),
            spacing="1",
            align="center",
            style={
                "padding": "2px 8px",
                "borderRadius": "999px",
                "background": "var(--gray-3)",
                "border": "1px solid var(--gray-4)",
                "whiteSpace": "nowrap",
            },
        ),
        rx.fragment(),
    )
    return rx.hstack(
        proposed_chip,
        expiration_chip,
        spacing="2",
        align="center",
        wrap="wrap",
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
    proposal_id = action["proposal_id"].to(str)
    return rx.box(
        rx.cond(
            AuthState.ga_favorite_ids.contains(proposal_id),
            rx.icon("heart", size=22, color="var(--red-9)", style={"fill": "var(--red-9)"}),
            rx.icon("heart", size=22, color="var(--gray-8)"),
        ),
        on_click=AuthState.toggle_ga_favorite(proposal_id),
        cursor="pointer",
        padding="4px",
        flex_shrink="0",
    )


def ga_list_card(action: Dict[str, Any]) -> rx.Component:
    content = rx.hstack(
        rx.vstack(
            # ── 上部: ステータス / タイプ バッジ + 日付チップ ──
            rx.hstack(
                ga_status_badge(action),
                ga_type_badge(action),
                _date_chips(action),
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
            _withdrawal_inline(action),
            rx.cond(
                _has_any_text("abstract_ja_card", "abstract_card", action),
                rx.text(
                    _localized_text("abstract_ja_card", "abstract_card", action),
                    size="3",
                    line_height="1.6",
                    text_wrap="wrap",
                    class_name="mt-2 line-clamp-3",
                    min_height="3.6em",
                    color="var(--gray-12)",
                ),
                rx.fragment(),
            ),
            # ── 一番下: 投票状況（DRep/CC/SPO ミニドーナツ） ──
            _vote_summary_inline(action),
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
        # ── 上部: バッジ + 日付チップ + お気に入りボタン ──
        rx.hstack(
            rx.hstack(
                ga_status_badge(action),
                ga_type_badge(action),
                _date_chips(action),
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
        _withdrawal_inline(action),
        rx.cond(
            _has_any_text("abstract_ja_card", "abstract_card", action),
            rx.text(
                _localized_text("abstract_ja_card", "abstract_card", action),
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
            # ── 一番下: 投票状況 ──
            _vote_summary_inline(action),
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
