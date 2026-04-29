"""
governance_ai_analysis.py
GA 詳細ページに表示する AI 分析セクション。

- Feature A: 憲法準拠スコア（GovernanceState.modal_ai_data + modal_ai_articles + concerns）
- Feature B: VISION 2030 KPI レーダーチャート（modal_ai_pillars + modal_ai_related_kpis）

5 状態（none / pending / analyzing / analyzed / failed）は GovernanceState.modal_ai_status で
ディスパッチ。SVG ジオメトリ計算は db_connect.py 側 (build_radar_svg / build_gauge_svg) で行う。
"""
from __future__ import annotations

from typing import Dict

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
                rx.badge("OpenAI gpt-5.4-mini", color_scheme="violet", variant="soft", size="1"),
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


# ─── 状態 4: analyzed — Feature A: 憲法準拠 ────────────────────────────────────

def _gauge_box(svg_str) -> rx.Component:
    """SVG 文字列を rx.html で表示するラッパー。Var / 文字列 どちらも受け付ける。"""
    return rx.box(rx.html(svg_str), flex_shrink="0")




def _article_row(row) -> rx.Component:
    """row は Python dict でも Reflex Var でも動作する。
    score / bar_pct / color は事前に文字列で算出済みの想定（State / 定数 両対応）。
    """
    label = rx.cond(AuthState.language == "en", row["label_en"], row["label_ja"])
    comment = rx.cond(AuthState.language == "en", row["comment_en"], row["comment_ja"])

    # Radix UI のカラー名を CSS 変数に動的に展開
    bar_bg = "var(--" + row["color"] + "-9)"
    score_color = "var(--" + row["color"] + "-11)"

    return rx.vstack(
        rx.hstack(
            rx.text(label, size="2", weight="medium", color="var(--gray-12)"),
            rx.spacer(),
            rx.hstack(
                rx.text(row["score"], size="3", weight="bold", color=score_color),
                rx.text("/ 10", size="1", color="var(--gray-9)"),
                spacing="1", align="baseline",
            ),
            spacing="2", align="center", width="100%",
        ),
        rx.box(
            rx.box(
                width=row["bar_pct"],
                height="100%",
                background=bar_bg,
                border_radius="3px",
                transition="width 0.6s ease",
            ),
            width="100%",
            height="6px",
            background="var(--gray-4)",
            border_radius="3px",
            overflow="hidden",
        ),
        rx.text(comment, size="1", color="var(--gray-10)", line_height="1.5"),
        spacing="1",
        align="start",
        width="100%",
    )


def _concern_row(text: str) -> rx.Component:
    return rx.hstack(
        rx.icon("circle-alert", size=14, color="var(--ruby-10)", flex_shrink="0"),
        rx.text(text, size="2", color="var(--gray-12)", line_height="1.5"),
        spacing="2",
        align="start",
        width="100%",
    )


def _constitution_card() -> rx.Component:
    """Feature A: 憲法準拠カード（本番データ）。GovernanceState から読む。"""
    data = GovernanceState.modal_ai_data
    verdict = rx.cond(AuthState.language == "en", data["verdict_en"], data["verdict_ja"])
    summary = rx.cond(AuthState.language == "en", data["summary_en"], data["summary_ja"])
    color = data["score_color"]
    badge_color = "var(--" + color + "-11)"
    badge_bg = "var(--" + color + "-3)"

    head = rx.hstack(
        rx.icon("scroll-text", size=18, color="var(--violet-11)"),
        rx.text(AuthState.t["ga_ai_const_title"], size="3", weight="bold", color="var(--gray-12)"),
        rx.spacer(),
        # Radix の color_scheme は文字列リテラル必須なので、background/color を直接指定
        rx.box(
            rx.text(verdict, size="2", weight="medium"),
            padding="3px 10px",
            border_radius="999px",
            background=badge_bg,
            color=badge_color,
        ),
        spacing="2", align="center", width="100%",
    )

    top_block = rx.flex(
        _gauge_box(data["gauge_svg"]),
        rx.vstack(
            rx.text(AuthState.t["ga_ai_const_summary_label"], size="1", weight="medium", color="var(--gray-10)"),
            rx.text(summary, size="2", color="var(--gray-12)", line_height="1.6"),
            spacing="1",
            align="start",
            flex="1",
            min_width="240px",
        ),
        spacing="4",
        align="center",
        wrap="wrap",
        width="100%",
    )

    articles_block = rx.vstack(
        rx.text(AuthState.t["ga_ai_const_articles_label"], size="2", weight="medium", color="var(--gray-11)"),
        rx.foreach(GovernanceState.modal_ai_articles, _article_row),
        spacing="3",
        width="100%",
        align="start",
    )

    concerns_block = rx.cond(
        rx.cond(
            AuthState.language == "en",
            GovernanceState.modal_ai_concerns_en.length() > 0,
            GovernanceState.modal_ai_concerns_ja.length() > 0,
        ),
        rx.vstack(
            rx.hstack(
                rx.icon("circle-alert", size=14, color="var(--ruby-10)"),
                rx.text(AuthState.t["ga_ai_const_concerns_label"], size="2", weight="medium", color="var(--ruby-11)"),
                spacing="1", align="center",
            ),
            rx.cond(
                AuthState.language == "en",
                rx.vstack(
                    rx.foreach(GovernanceState.modal_ai_concerns_en, _concern_row),
                    spacing="2", width="100%", align="start",
                ),
                rx.vstack(
                    rx.foreach(GovernanceState.modal_ai_concerns_ja, _concern_row),
                    spacing="2", width="100%", align="start",
                ),
            ),
            spacing="2",
            width="100%",
            align="start",
            padding="12px",
            background="var(--ruby-2)",
            border=f"1px solid {rx.color('ruby', 4)}",
            border_radius="8px",
        ),
        rx.fragment(),
    )

    return rx.box(
        rx.vstack(
            head,
            top_block,
            articles_block,
            concerns_block,
            spacing="4",
            width="100%",
            align_items="stretch",
        ),
        padding="18px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


# ─── 状態 4: analyzed — Feature B: VISION 2030 KPI ─────────────────────────────

def _radar_chart() -> rx.Component:
    """5 軸レーダーチャート（State から SVG を読む）。"""
    data = GovernanceState.modal_ai_data
    return rx.cond(
        AuthState.language == "en",
        rx.html(data["radar_svg_en"]),
        rx.html(data["radar_svg_ja"]),
    )


def _pillar_row(p) -> rx.Component:
    """1 つの pillar の凡例行。p は Reflex Var-typed dict (rx.foreach 用)。"""
    label = rx.cond(AuthState.language == "en", p["label_en"], p["label_ja"])
    comment = rx.cond(AuthState.language == "en", p["comment_en"], p["comment_ja"])
    bar_bg = "var(--" + p["color"] + "-9)"
    score_color = "var(--" + p["color"] + "-11)"
    return rx.hstack(
        rx.box(
            width="8px",
            height="40px",
            background=bar_bg,
            border_radius="2px",
            flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(label, size="2", weight="medium", color="var(--gray-12)"),
                rx.spacer(),
                rx.text(p["score"], size="3", weight="bold", color=score_color),
                rx.text("/ 100", size="1", color="var(--gray-9)"),
                spacing="1", align="baseline", width="100%",
            ),
            rx.text(comment, size="1", color="var(--gray-10)", line_height="1.4"),
            spacing="0",
            align="start",
            flex="1",
            min_width="0",
        ),
        spacing="2",
        align="center",
        width="100%",
    )


def _kpi_legend() -> rx.Component:
    """5 pillar の凡例リスト。"""
    return rx.vstack(
        rx.foreach(GovernanceState.modal_ai_pillars, _pillar_row),
        spacing="3", width="100%", align="start",
    )


def _impact_badge(impact_var) -> rx.Component:
    """+ / 0 / − の影響度バッジ。impact は Reflex Var (rx.match で分岐)。"""
    return rx.match(
        impact_var,
        ("+", rx.badge(
            rx.hstack(
                rx.icon("trending-up", size=12),
                rx.text(AuthState.t["ga_ai_kpi_impact_positive"], weight="medium"),
                spacing="1", align="center",
            ),
            color_scheme="green", variant="soft", size="1",
        )),
        ("-", rx.badge(
            rx.hstack(
                rx.icon("trending-down", size=12),
                rx.text(AuthState.t["ga_ai_kpi_impact_negative"], weight="medium"),
                spacing="1", align="center",
            ),
            color_scheme="ruby", variant="soft", size="1",
        )),
        rx.badge(
            rx.hstack(
                rx.icon("minus", size=12),
                rx.text(AuthState.t["ga_ai_kpi_impact_neutral"], weight="medium"),
                spacing="1", align="center",
            ),
            color_scheme="gray", variant="soft", size="1",
        ),
    )


def _related_kpi_row(kpi) -> rx.Component:
    """1 つの関連 KPI 行。kpi は Reflex Var-typed dict (rx.foreach 用)。"""
    name = rx.cond(AuthState.language == "en", kpi["name_en"], kpi["name_ja"])
    comment = rx.cond(AuthState.language == "en", kpi["comment_en"], kpi["comment_ja"])
    return rx.hstack(
        _impact_badge(kpi["impact"]),
        rx.vstack(
            rx.hstack(
                rx.text(name, size="2", weight="medium", color="var(--gray-12)"),
                rx.text(
                    AuthState.t["ga_ai_kpi_target_label"],
                    size="1", color="var(--gray-9)",
                ),
                rx.text(kpi["target"], size="1", weight="medium", color="var(--gray-11)"),
                spacing="1", align="baseline", wrap="wrap",
            ),
            rx.text(comment, size="1", color="var(--gray-10)", line_height="1.5"),
            spacing="0", align="start", flex="1", min_width="0",
        ),
        spacing="3",
        align="start",
        width="100%",
    )


def _related_kpis_block() -> rx.Component:
    """関連 KPI セクション。AI が 1〜3 個ピック。空配列なら非表示。"""
    return rx.cond(
        GovernanceState.modal_ai_related_kpis.length() > 0,
        rx.vstack(
            rx.hstack(
                rx.icon("target", size=14, color="var(--indigo-11)"),
                rx.text(AuthState.t["ga_ai_kpi_related_label"], size="2", weight="medium", color="var(--gray-11)"),
                spacing="1", align="center",
            ),
            rx.foreach(GovernanceState.modal_ai_related_kpis, _related_kpi_row),
            spacing="3",
            width="100%",
            align="start",
            padding="12px",
            background="var(--indigo-2)",
            border=f"1px solid {rx.color('indigo', 4)}",
            border_radius="8px",
        ),
        rx.fragment(),
    )


def _kpi_card() -> rx.Component:
    head = rx.hstack(
        rx.icon("radar", size=18, color="var(--indigo-11)"),
        rx.text(AuthState.t["ga_ai_kpi_title"], size="3", weight="bold", color="var(--gray-12)"),
        rx.spacer(),
        rx.badge(AuthState.t["ga_ai_kpi_vision_label"], color_scheme="indigo", variant="soft", size="1"),
        spacing="2", align="center", width="100%",
    )

    body = rx.flex(
        rx.box(
            _radar_chart(),
            flex="0 0 auto",
            width=["100%", "100%", "350px"],
        ),
        rx.box(
            _kpi_legend(),
            flex="1",
            min_width="240px",
        ),
        spacing="4",
        wrap="wrap",
        width="100%",
        align="start",
    )

    return rx.box(
        rx.vstack(
            head,
            body,
            _related_kpis_block(),
            spacing="4",
            width="100%",
            align_items="stretch",
        ),
        padding="18px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


def _state_analyzed() -> rx.Component:
    return rx.vstack(
        _constitution_card(),
        _kpi_card(),
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


# ─── 公開エントリポイント ──────────────────────────────────────────────────────

def _state_loading() -> rx.Component:
    """modal_ai_status が空（State 未ロード）時のプレースホルダ。"""
    return rx.center(rx.spinner(size="2"), padding="20px", width="100%")


def _login_prompt_body() -> rx.Component:
    """未ログインユーザーに表示する CTA。ログインボタンで login_modal を開く。"""
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


def ai_analysis_section() -> rx.Component:
    """GA 詳細ページの voting summary 直後に配置するセクション。

    可視性: ログイン済みユーザーのみ AI 分析を表示。未ログインはログイン CTA を出す。
    （変更したい場合は AuthState.is_logged_in の rx.cond を外す or 条件を変える）
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
