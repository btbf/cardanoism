"""
governance_ai_analysis.py
GA 詳細ページに表示する AI 分析セクション（A 方針: ファクト整理ツール）。

スコア / 判定 / KPI レーダー等は出さず、以下を提示する:
- 提案概要 (proposal_summary)
- 提案ファクト (proposal_facts)
- 関連憲法条文 (articles, スコア無し)
- 自動チェック項目 (rule_checks, ルールベース決定論的判定)

5 状態（none / pending / analyzing / analyzed / failed）は
GovernanceState.modal_ai_status でディスパッチ。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.db_connect import GovernanceState  # noqa: F401  reactive only


# ─── 共通レイアウト ────────────────────────────────────────────────────────────

_AI_SECTION_PADDING = "20px 22px"


def _ai_heading() -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon("sparkles", size=18, color="white"),
            background="linear-gradient(135deg, var(--violet-9), var(--indigo-9))",
            border_radius="8px",
            padding="6px",
            display="inline-flex",
            align_items="center",
            justify_content="center",
        ),
        rx.vstack(
            rx.text(AuthState.t["ga_ai_section_title"], size="3", weight="bold", color="var(--gray-12)"),
            rx.text(AuthState.t["ga_ai_section_subtitle"], size="1", color="var(--gray-10)"),
            spacing="0",
            align="start",
        ),
        rx.spacer(),
        rx.badge(
            rx.hstack(
                rx.icon("flask-conical", size=12),
                rx.text("Beta", weight="medium"),
                spacing="1",
                align="center",
            ),
            color_scheme="violet",
            variant="soft",
            size="1",
            radius="full",
        ),
        spacing="3",
        align="center",
        width="100%",
    )


def _ai_card(content: rx.Component) -> rx.Component:
    return rx.box(
        rx.vstack(
            _ai_heading(),
            rx.divider(),
            content,
            spacing="3",
            width="100%",
            align_items="stretch",
        ),
        padding=_AI_SECTION_PADDING,
        border=f"1px solid {rx.color('violet', 5)}",
        border_radius="14px",
        background=rx.color_mode_cond(
            light="linear-gradient(180deg, var(--violet-2), var(--gray-1))",
            dark="linear-gradient(180deg, var(--violet-3), var(--gray-2))",
        ),
        width="100%",
    )


# ─── 状態 1: 対象外 ────────────────────────────────────────────────────────────

def _state_none() -> rx.Component:
    return rx.hstack(
        rx.icon("info", size=16, color="var(--gray-9)"),
        rx.text(
            AuthState.t["ga_ai_state_none"],
            size="2",
            color="var(--gray-10)",
        ),
        spacing="2",
        align="center",
        padding="12px 4px",
    )


# ─── 状態 2: pending ───────────────────────────────────────────────────────────

def _state_pending() -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.box(
                width="10px",
                height="10px",
                border_radius="50%",
                background="var(--amber-9)",
                animation="ai-pulse 1.4s ease-in-out infinite",
            ),
            rx.html(
                """
                <style>
                @keyframes ai-pulse {
                  0%, 100% { transform: scale(1); opacity: 1; }
                  50% { transform: scale(1.6); opacity: 0.4; }
                }
                </style>
                """
            ),
        ),
        rx.vstack(
            rx.text(
                AuthState.t["ga_ai_state_pending_title"],
                size="2", weight="bold", color="var(--gray-12)",
            ),
            rx.hstack(
                rx.text(
                    AuthState.t["ga_ai_state_pending_desc_prefix"],
                    size="1", color="var(--gray-10)",
                ),
                rx.text(
                    GovernanceState.modal_ai_data["elapsed_pending"],
                    size="1", color="var(--gray-12)", weight="medium",
                ),
                rx.text(
                    AuthState.t["ga_ai_state_pending_desc_suffix"],
                    size="1", color="var(--gray-10)",
                ),
                spacing="1",
                align="baseline",
            ),
            spacing="0",
            align="start",
        ),
        spacing="3",
        align="center",
        padding="14px 4px",
    )


# ─── 状態 3: analyzing ─────────────────────────────────────────────────────────

def _state_analyzing() -> rx.Component:
    return rx.hstack(
        rx.spinner(size="3", color="violet"),
        rx.vstack(
            rx.hstack(
                rx.text(
                    AuthState.t["ga_ai_state_analyzing_title"],
                    size="2", weight="bold", color="var(--gray-12)",
                ),
                rx.badge("AI", color_scheme="violet", variant="soft", size="1"),
                spacing="2", align="center",
            ),
            rx.text(
                AuthState.t["ga_ai_state_analyzing_desc"],
                size="1", color="var(--gray-10)",
            ),
            spacing="1",
            align="start",
        ),
        spacing="3",
        align="center",
        padding="14px 4px",
    )


# ─── 状態 5: failed ────────────────────────────────────────────────────────────

def _state_failed() -> rx.Component:
    return rx.hstack(
        rx.icon("triangle-alert", size=20, color="var(--red-10)"),
        rx.vstack(
            rx.text(
                AuthState.t["ga_ai_state_failed_title"],
                size="2", weight="bold", color="var(--red-11)",
            ),
            rx.text(
                GovernanceState.modal_ai_last_error,
                size="1",
                color="var(--gray-10)",
                style={"fontFamily": "var(--code-font-family, ui-monospace, monospace)"},
            ),
            spacing="0", align="start",
        ),
        rx.spacer(),
        rx.button(
            rx.icon("rotate-ccw", size=14),
            rx.text(AuthState.t["ga_ai_retry"], size="2"),
            color_scheme="red",
            variant="soft",
            size="2",
            cursor="pointer",
            on_click=GovernanceState.retry_ai_analysis,
        ),
        spacing="3",
        align="center",
        padding="10px 4px",
        width="100%",
    )


# ─── 状態 4: analyzed パーツ ───────────────────────────────────────────────────

def _section_box(content: rx.Component) -> rx.Component:
    """analyzed 中の各サブセクション共通の枠。"""
    return rx.box(
        content,
        padding="16px 18px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


def _summary_block() -> rx.Component:
    """提案の概要（AI による中立的な要約）。"""
    data = GovernanceState.modal_ai_data
    text = rx.cond(
        AuthState.language == "en",
        rx.cond(data["summary_en"] != "", data["summary_en"], data["summary_ja"]),
        rx.cond(data["summary_ja"] != "", data["summary_ja"], data["summary_en"]),
    )
    has_text = rx.cond(
        AuthState.language == "en",
        rx.cond(data["summary_en"] != "", True, data["summary_ja"] != ""),
        rx.cond(data["summary_ja"] != "", True, data["summary_en"] != ""),
    )
    return rx.cond(
        has_text,
        _section_box(
            rx.vstack(
                rx.hstack(
                    rx.icon("file-text", size=16, color="var(--violet-11)"),
                    rx.text(
                        AuthState.t["ga_ai_summary_title"],
                        size="2", weight="bold", color="var(--gray-12)",
                    ),
                    spacing="2", align="center", width="100%",
                ),
                rx.text(text, size="2", color="var(--gray-12)", line_height="1.7"),
                spacing="3", width="100%", align_items="stretch",
            ),
        ),
        rx.fragment(),
    )


def _facts_row(f) -> rx.Component:
    label = rx.cond(AuthState.language == "en", f["label_en"], f["label_ja"])
    # value_ja / value_en で言語連動。空ならもう一方にフォールバック
    value = rx.cond(
        AuthState.language == "en",
        rx.cond(f["value_en"] != "", f["value_en"], f["value_ja"]),
        rx.cond(f["value_ja"] != "", f["value_ja"], f["value_en"]),
    )
    return rx.flex(
        rx.text(
            label,
            size="2", weight="medium", color="var(--gray-10)",
            style={"minWidth": "140px", "flexShrink": "0"},
        ),
        rx.text(
            value,
            size="2", color="var(--gray-12)",
            style={"wordBreak": "break-word"},
        ),
        spacing="3",
        align="start",
        width="100%",
        wrap="wrap",
    )


def _facts_block() -> rx.Component:
    """提案ファクト（AI 抽出のキー情報リスト）。"""
    return rx.cond(
        GovernanceState.modal_ai_facts.length() > 0,
        _section_box(
            rx.vstack(
                rx.hstack(
                    rx.icon("list", size=16, color="var(--violet-11)"),
                    rx.text(
                        AuthState.t["ga_ai_facts_title"],
                        size="2", weight="bold", color="var(--gray-12)",
                    ),
                    spacing="2", align="center", width="100%",
                ),
                rx.foreach(GovernanceState.modal_ai_facts, _facts_row),
                spacing="3", width="100%", align_items="stretch",
            ),
        ),
        rx.fragment(),
    )


def _article_entry(a) -> rx.Component:
    label = rx.cond(AuthState.language == "en", a["label_en"], a["label_ja"])
    why = rx.cond(AuthState.language == "en", a["why_relevant_en"], a["why_relevant_ja"])
    quote = rx.cond(
        AuthState.language == "en",
        rx.cond(a["quote_en"] != "", a["quote_en"], a["quote_ja"]),
        rx.cond(a["quote_ja"] != "", a["quote_ja"], a["quote_en"]),
    )
    has_quote = rx.cond(
        AuthState.language == "en",
        rx.cond(a["quote_en"] != "", True, a["quote_ja"] != ""),
        rx.cond(a["quote_ja"] != "", True, a["quote_en"] != ""),
    )
    quote_block = rx.cond(
        has_quote,
        rx.box(
            rx.text(
                quote,
                size="1",
                color="var(--gray-11)",
                line_height="1.6",
                style={"fontStyle": "italic", "whiteSpace": "pre-wrap"},
            ),
            padding="6px 10px",
            border_left=f"3px solid {rx.color('amber', 7)}",
            background="var(--amber-2)",
            border_radius="0 6px 6px 0",
            width="100%",
        ),
        rx.fragment(),
    )
    return rx.vstack(
        rx.text(label, size="2", weight="bold", color="var(--gray-12)"),
        quote_block,
        rx.cond(
            why != "",
            rx.text(why, size="1", color="var(--gray-10)", line_height="1.5"),
            rx.fragment(),
        ),
        spacing="2",
        align="start",
        width="100%",
    )


def _articles_block() -> rx.Component:
    """関連する憲法条文（AI が抽出、スコア無し）。"""
    return rx.cond(
        GovernanceState.modal_ai_articles.length() > 0,
        _section_box(
            rx.vstack(
                rx.hstack(
                    rx.icon("scroll-text", size=16, color="var(--violet-11)"),
                    rx.text(
                        AuthState.t["ga_ai_articles_title"],
                        size="2", weight="bold", color="var(--gray-12)",
                    ),
                    spacing="2", align="center", width="100%",
                ),
                rx.foreach(GovernanceState.modal_ai_articles, _article_entry),
                spacing="4", width="100%", align_items="stretch",
            ),
        ),
        rx.fragment(),
    )


def _rule_check_row(r) -> rx.Component:
    label = rx.cond(AuthState.language == "en", r["label_en"], r["label_ja"])
    detail = rx.cond(AuthState.language == "en", r["detail_en"], r["detail_ja"])
    icon = rx.match(
        r["status"],
        ("ok", rx.icon("check", size=16, color="var(--green-11)")),
        ("ng", rx.icon("x", size=16, color="var(--ruby-11)")),
        rx.icon("minus", size=16, color="var(--gray-9)"),
    )
    label_color = rx.match(
        r["status"],
        ("ok", "var(--gray-12)"),
        ("ng", "var(--ruby-11)"),
        "var(--gray-10)",
    )
    return rx.flex(
        rx.box(icon, flex_shrink="0", style={"width": "20px", "display": "flex", "alignItems": "center"}),
        rx.text(label, size="2", weight="medium", color=label_color, flex="1", min_width="0"),
        rx.cond(
            detail != "",
            rx.text(detail, size="1", color="var(--gray-10)", style={"textAlign": "right", "flexShrink": "0"}),
            rx.fragment(),
        ),
        spacing="2",
        align="center",
        width="100%",
    )


def _rule_checks_block() -> rx.Component:
    """ルールベースの自動チェック結果（AI 不使用、決定論的）。"""
    return rx.cond(
        GovernanceState.modal_ai_rule_checks.length() > 0,
        _section_box(
            rx.vstack(
                rx.hstack(
                    rx.icon("check-check", size=16, color="var(--violet-11)"),
                    rx.text(
                        AuthState.t["ga_ai_rule_checks_title"],
                        size="2", weight="bold", color="var(--gray-12)",
                    ),
                    rx.spacer(),
                    rx.badge(
                        AuthState.t["ga_ai_rule_checks_badge"],
                        color_scheme="green", variant="soft", size="1",
                    ),
                    spacing="2", align="center", width="100%",
                ),
                rx.foreach(GovernanceState.modal_ai_rule_checks, _rule_check_row),
                spacing="2", width="100%", align_items="stretch",
            ),
        ),
        rx.fragment(),
    )


def _state_analyzed() -> rx.Component:
    return rx.vstack(
        _summary_block(),
        _facts_block(),
        rx.hstack(
            rx.icon("info", size=12, color="var(--gray-9)"),
            rx.text(
                AuthState.t["ga_ai_disclaimer"],
                size="1", color="var(--gray-9)", line_height="1.5",
            ),
            spacing="1",
            align="start",
            width="100%",
        ),
        spacing="4",
        width="100%",
        align_items="stretch",
    )


# ─── 状態未ロード ──────────────────────────────────────────────────────────────

def _state_loading() -> rx.Component:
    return rx.center(rx.spinner(size="2"), padding="20px", width="100%")


def _login_prompt_body() -> rx.Component:
    """未ログインユーザーに表示する CTA。"""
    return rx.vstack(
        rx.box(
            rx.icon("lock", size=28, color="var(--violet-11)"),
            padding="12px",
            background="var(--violet-3)",
            border_radius="50%",
            display="inline-flex",
            align_items="center",
            justify_content="center",
        ),
        rx.text(
            AuthState.t["ga_ai_login_required_title"],
            size="3", weight="bold", color="var(--gray-12)",
        ),
        rx.text(
            AuthState.t["ga_ai_login_required_desc"],
            size="2", color="var(--gray-10)",
            text_align="center",
            max_width="420px",
            line_height="1.6",
        ),
        rx.button(
            rx.icon("log-in", size=14),
            rx.text(AuthState.t["ga_ai_login_required_btn"], size="2", weight="medium"),
            color_scheme="violet",
            size="3",
            cursor="pointer",
            on_click=AuthState.open_login_modal,
        ),
        spacing="3",
        align="center",
        padding="24px 12px",
        width="100%",
    )


# ─── 公開エントリポイント ──────────────────────────────────────────────────────

def ai_analysis_section() -> rx.Component:
    """GA 詳細ページの voting summary 直後に配置するセクション。
    可視性: ログイン済みユーザーのみ AI 分析を表示。
    """
    body = rx.match(
        GovernanceState.modal_ai_status,
        ("none",      _state_none()),
        ("pending",   _state_pending()),
        ("analyzing", _state_analyzing()),
        ("analyzed",  _state_analyzed()),
        ("failed",    _state_failed()),
        _state_loading(),
    )
    return _ai_card(
        rx.cond(
            AuthState.is_logged_in,
            body,
            _login_prompt_body(),
        )
    )
