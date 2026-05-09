"""staking_why.py
ステーキング > 「ステーキングとは？」初心者向け啓発ページ (/staking/why)

ターゲット:
  - ADA は持っているがまだステークしたことがないユーザー
  - 他チェーン (Ethereum / Polkadot / Cosmos / Solana) のステーキング経験者で
    Cardano 流儀に慣れていないユーザー

トーン: カジュアルで短くシンプル
構成 (縦スクロール 1 ページ):
  1. ヒーロー (1 行サマリ + 3 つの安心バッジ)
  2. なぜステーキングするの？ (3 価値カード)
  3. 他チェーンとの違い (TL;DR 比較表)
  4. 4 ステップで始める
  5. プール選びの 3 つのコツ
  6. エポックと報酬タイムライン
  7. よくある誤解 Q&A
  8. CTA (Cardanoism から委任 / プールを見る)
"""
from __future__ import annotations

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.components.staking_nav import staking_subnav
from cardanoism.components.breadcrumb import breadcrumb


ACCENT       = "#ffcf00"
ACCENT_DARK  = "#c7a300"
TEXT_MUTED   = "var(--gray-10)"

# 価値カードの色
C_REWARD = "#16a34a"   # 緑: 報酬
C_VOTE   = "#7c5cff"   # 紫: ガバナンス
C_FREE   = "#0ea5e9"   # 水色: 自由

# プール選び指標カラー
C_SAT    = "#f97316"   # オレンジ: 飽和度
C_FEE    = "#3b82f6"   # 青: 手数料
C_PERF   = "#10b981"   # エメラルド: 実績


# ─── 共通パーツ ────────────────────────────────────────────────────────────────


def _shell(*children, **kw) -> rx.Component:
    """セクションコンテンツを 1130px max で中央寄せ。"""
    base = dict(
        max_width="1130px",
        width="100%",
        margin_x="auto",
        padding_x=["20px", "28px", "40px"],
    )
    base.update(kw)
    return rx.box(*children, **base)


def _section_heading(kicker, title, subtitle=None) -> rx.Component:
    body = [
        rx.text(kicker, size="2", weight="bold", color=ACCENT_DARK, letter_spacing="0.14em"),
        rx.heading(
            title,
            as_="h2",
            size={"base": "6", "md": "7"},
            weight="bold",
            line_height="1.25",
            style={"wordBreak": "break-word"},
        ),
    ]
    if subtitle is not None:
        body.append(
            rx.text(subtitle, size="3", color=TEXT_MUTED, line_height="1.7",
                    max_width="720px", style={"wordBreak": "break-word"})
        )
    return rx.vstack(*body, spacing="2", align_items="start", width="100%")


def _breadcrumb() -> rx.Component:
    return breadcrumb([("nav_staking", "/staking")], "staking_subnav_why")


def _bullet_card(icon: str, color: str, title_key: str, desc_key: str) -> rx.Component:
    """3 列で並ぶ価値カード。"""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.center(
                    rx.icon(icon, size=22, color="white"),
                    width="40px", height="40px",
                    border_radius="10px",
                    background=color,
                ),
                rx.text(AuthState.t[title_key], size="3", weight="bold", color="var(--gray-12)"),
                spacing="3", align="center",
            ),
            rx.text(AuthState.t[desc_key], size="2", color=TEXT_MUTED, line_height="1.7"),
            spacing="3", align_items="start", width="100%",
        ),
        padding="20px 22px",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="14px",
        background=rx.color_mode_cond("rgba(255,255,255,0.7)", "rgba(255,255,255,0.025)"),
        height="100%",
    )


# ─── 1. ヒーロー ──────────────────────────────────────────────────────────────


def _hero() -> rx.Component:
    def _badge(icon: str, label_key: str) -> rx.Component:
        return rx.hstack(
            rx.icon(icon, size=14, color=ACCENT_DARK),
            rx.text(AuthState.t[label_key], size="2", weight="medium", color="var(--gray-12)"),
            spacing="2", align="center",
            padding="6px 12px",
            border_radius="999px",
            border=f"1px solid {rx.color('amber', 6)}",
            background=rx.color_mode_cond("rgba(255,207,0,0.08)", "rgba(255,207,0,0.10)"),
        )
    return _shell(
        rx.vstack(
            rx.text(AuthState.t["staking_why_kicker"], size="2", weight="bold",
                    color=ACCENT_DARK, letter_spacing="0.14em"),
            rx.heading(
                AuthState.t["staking_why_hero_title"],
                as_="h1",
                size={"base": "7", "md": "8"},
                weight="bold",
                line_height="1.2",
                style={"wordBreak": "break-word"},
                max_width="780px",
            ),
            rx.text(
                AuthState.t["staking_why_hero_lead"],
                size="3", color=TEXT_MUTED, line_height="1.8",
                max_width="640px",
                style={"wordBreak": "break-word"},
            ),
            rx.flex(
                _badge("lock-open", "staking_why_badge_no_lock"),
                _badge("rotate-ccw", "staking_why_badge_anytime"),
                _badge("shield-check", "staking_why_badge_safe"),
                spacing="2", wrap="wrap",
                style={"marginTop": "8px"},
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding_y=["48px", "56px", "72px"],
    )


# ─── 2. なぜステーキングするの？ ────────────────────────────────────────────────


def _why_section() -> rx.Component:
    return _shell(
        rx.vstack(
            _section_heading(
                AuthState.t["staking_why_kicker_2"],
                AuthState.t["staking_why_value_title"],
            ),
            rx.grid(
                _bullet_card("coins",          C_REWARD, "staking_why_v1_title", "staking_why_v1_desc"),
                _bullet_card("heart-handshake", C_VOTE,  "staking_why_v2_title", "staking_why_v2_desc"),
                _bullet_card("shield-check",   C_FREE,   "staking_why_v3_title", "staking_why_v3_desc"),
                columns={"base": "1", "sm": "1", "md": "3"},
                spacing="4",
                width="100%",
            ),
            spacing="6", width="100%",
        ),
        padding_y=["32px", "40px", "56px"],
    )


# ─── 3. 4 ステップで始める ────────────────────────────────────────────────────


def _step_card(num: str, icon: str, title_key: str, desc_key: str) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.center(
                    rx.text(num, size="3", weight="bold", color="var(--amber-11)"),
                    width="32px", height="32px",
                    border_radius="999px",
                    background="var(--amber-3)",
                    border="1px solid var(--amber-6)",
                    style={"flexShrink": "0"},
                ),
                rx.icon(icon, size=20, color=ACCENT_DARK),
                rx.text(AuthState.t[title_key], size="3", weight="bold", color="var(--gray-12)"),
                spacing="3", align="center",
            ),
            rx.text(AuthState.t[desc_key], size="2", color=TEXT_MUTED, line_height="1.7"),
            spacing="3", align_items="start", width="100%",
        ),
        padding="18px 20px",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="14px",
        background=rx.color_mode_cond("rgba(255,255,255,0.7)", "rgba(255,255,255,0.025)"),
        height="100%",
    )


def _steps_section() -> rx.Component:
    return _shell(
        rx.vstack(
            _section_heading(
                AuthState.t["staking_why_kicker_4"],
                AuthState.t["staking_why_steps_title"],
                AuthState.t["staking_why_steps_lead"],
            ),
            rx.grid(
                _step_card("1", "wallet",     "staking_why_step1_title", "staking_why_step1_desc"),
                _step_card("2", "arrow-down", "staking_why_step2_title", "staking_why_step2_desc"),
                _step_card("3", "search",     "staking_why_step3_title", "staking_why_step3_desc"),
                _step_card("4", "send",       "staking_why_step4_title", "staking_why_step4_desc"),
                columns={"base": "1", "sm": "2", "md": "4"},
                spacing="3",
                width="100%",
            ),
            spacing="6", width="100%",
        ),
        padding_y=["32px", "40px", "56px"],
    )


# ─── 5. プール選びの 3 つのコツ ───────────────────────────────────────────────


def _checkpoint_card(icon: str, color: str, title_key: str, desc_key: str, hint_key: str) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.center(
                    rx.icon(icon, size=18, color="white"),
                    width="36px", height="36px",
                    border_radius="10px",
                    background=color,
                ),
                rx.text(AuthState.t[title_key], size="3", weight="bold", color="var(--gray-12)"),
                spacing="3", align="center",
            ),
            rx.text(AuthState.t[desc_key], size="2", color=TEXT_MUTED, line_height="1.7"),
            rx.box(
                rx.text(
                    AuthState.t[hint_key],
                    size="1", weight="medium", color="var(--gray-12)",
                    style={"lineHeight": "1.5"},
                ),
                padding="10px 12px",
                border_radius="10px",
                background=rx.color_mode_cond("rgba(0,0,0,0.04)", "rgba(255,255,255,0.04)"),
                width="100%",
                style={
                    "minHeight": "48px",
                    "display":   "flex",
                    "alignItems": "center",
                    "marginTop": "auto",
                },
            ),
            spacing="3", align_items="start", width="100%", height="100%",
        ),
        padding="20px 22px",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="14px",
        background=rx.color_mode_cond("rgba(255,255,255,0.7)", "rgba(255,255,255,0.025)"),
        height="100%",
    )


def _checkpoints_section() -> rx.Component:
    return _shell(
        rx.vstack(
            _section_heading(
                AuthState.t["staking_why_kicker_5"],
                AuthState.t["staking_why_check_title"],
                AuthState.t["staking_why_check_lead"],
            ),
            rx.grid(
                _checkpoint_card("gauge",     C_SAT,
                                 "staking_why_c1_title", "staking_why_c1_desc", "staking_why_c1_hint"),
                _checkpoint_card("percent",   C_FEE,
                                 "staking_why_c2_title", "staking_why_c2_desc", "staking_why_c2_hint"),
                _checkpoint_card("heart", C_PERF,
                                 "staking_why_c3_title", "staking_why_c3_desc", "staking_why_c3_hint"),
                columns={"base": "1", "sm": "1", "md": "3"},
                spacing="4",
                width="100%",
            ),
            spacing="6", width="100%",
        ),
        padding_y=["32px", "40px", "56px"],
    )


# ─── 6. エポックと報酬タイムライン ────────────────────────────────────────────


def _timeline_step(day_key: str, title_key: str, desc_key: str, *, last: bool = False) -> rx.Component:
    return rx.flex(
        rx.vstack(
            rx.center(
                rx.icon("check", size=14, color="white"),
                width="22px", height="22px",
                border_radius="999px",
                background=ACCENT_DARK,
                style={"flexShrink": "0"},
            ),
            rx.cond(
                last,
                rx.fragment(),
                rx.box(
                    width="2px",
                    flex_grow="1",
                    background="var(--amber-6)",
                    style={"minHeight": "32px"},
                ),
            ),
            spacing="0", align="center",
            style={"flexShrink": "0"},
        ),
        rx.vstack(
            rx.text(AuthState.t[day_key], size="1", weight="bold",
                    color=ACCENT_DARK, letter_spacing="0.10em"),
            rx.text(AuthState.t[title_key], size="3", weight="bold", color="var(--gray-12)"),
            rx.text(AuthState.t[desc_key], size="2", color=TEXT_MUTED, line_height="1.7"),
            spacing="1", align_items="start",
            style={"paddingBottom": "20px"},
        ),
        spacing="4", align_items="start", width="100%",
    )


def _timeline_section() -> rx.Component:
    return _shell(
        rx.vstack(
            _section_heading(
                AuthState.t["staking_why_kicker_6"],
                AuthState.t["staking_why_timeline_title"],
                AuthState.t["staking_why_timeline_lead"],
            ),
            rx.box(
                _timeline_step("staking_why_t1_day",  "staking_why_t1_title", "staking_why_t1_desc"),
                _timeline_step("staking_why_t2_day",  "staking_why_t2_title", "staking_why_t2_desc"),
                _timeline_step("staking_why_t3_day",  "staking_why_t3_title", "staking_why_t3_desc"),
                _timeline_step("staking_why_t4_day",  "staking_why_t4_title", "staking_why_t4_desc", last=True),
                width="100%",
            ),
            spacing="6", width="100%",
        ),
        padding_y=["32px", "40px", "56px"],
    )


# ─── 7. よくある誤解 Q&A ──────────────────────────────────────────────────────


def _faq_item(q_key: str, a_key: str) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.center(
                    rx.text("Q", size="2", weight="bold", color="white"),
                    width="22px", height="22px",
                    border_radius="6px",
                    background=ACCENT_DARK,
                    style={"flexShrink": "0"},
                ),
                rx.text(AuthState.t[q_key], size="3", weight="bold", color="var(--gray-12)",
                        style={"wordBreak": "break-word"}),
                spacing="3", align="start",
            ),
            rx.hstack(
                rx.center(
                    rx.text("A", size="2", weight="bold", color="var(--gray-12)"),
                    width="22px", height="22px",
                    border_radius="6px",
                    background=rx.color_mode_cond("rgba(0,0,0,0.06)", "rgba(255,255,255,0.08)"),
                    style={"flexShrink": "0"},
                ),
                rx.text(AuthState.t[a_key], size="2", color=TEXT_MUTED, line_height="1.8",
                        style={"wordBreak": "break-word"}),
                spacing="3", align="start",
            ),
            spacing="3", align_items="start", width="100%",
        ),
        padding="18px 20px",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="14px",
        background=rx.color_mode_cond("rgba(255,255,255,0.7)", "rgba(255,255,255,0.025)"),
        width="100%",
    )


def _faq_section() -> rx.Component:
    return _shell(
        rx.vstack(
            _section_heading(
                AuthState.t["staking_why_kicker_7"],
                AuthState.t["staking_why_faq_title"],
                None,
            ),
            rx.vstack(
                _faq_item("staking_why_faq1_q", "staking_why_faq1_a"),
                _faq_item("staking_why_faq2_q", "staking_why_faq2_a"),
                _faq_item("staking_why_faq3_q", "staking_why_faq3_a"),
                _faq_item("staking_why_faq4_q", "staking_why_faq4_a"),
                spacing="3", width="100%",
            ),
            spacing="6", width="100%",
        ),
        padding_y=["32px", "40px", "56px"],
    )


# ─── 8. CTA ───────────────────────────────────────────────────────────────────


def _cta_section() -> rx.Component:
    return _shell(
        rx.box(
            rx.vstack(
                rx.heading(
                    AuthState.t["staking_why_cta_title"],
                    as_="h2",
                    size={"base": "5", "md": "6"},
                    weight="bold",
                    line_height="1.3",
                    color="var(--gray-12)",
                    style={"wordBreak": "break-word"},
                ),
                rx.text(
                    AuthState.t["staking_why_cta_lead"],
                    size="3", color=TEXT_MUTED, line_height="1.7",
                    max_width="640px",
                ),
                rx.flex(
                    rx.link(
                        rx.button(
                            rx.icon("send", size=16),
                            AuthState.t["staking_why_cta_primary"],
                            rx.icon("arrow-right", size=16),
                            size="3",
                            background="var(--amber-9)",
                            color="var(--gray-12)",
                            cursor="pointer",
                            padding="0 22px",
                            _hover={"background": "var(--amber-10)"},
                            style={"boxShadow": "0 12px 32px -10px rgba(255,154,0,0.5)"},
                        ),
                        href="/staking/spo",
                        underline="none",
                    ),
                    rx.link(
                        rx.button(
                            rx.icon("server", size=16),
                            AuthState.t["staking_why_cta_secondary"],
                            rx.icon("arrow-right", size=16),
                            size="3",
                            variant="soft",
                            color="var(--gray-12)",
                            cursor="pointer",
                        ),
                        href="/staking/spo",
                        underline="none",
                    ),
                    spacing="3", wrap="wrap", align="center",
                ),
                spacing="4", align_items="start", width="100%",
            ),
            padding="32px 28px",
            border=f"1px solid {rx.color('amber', 6)}",
            border_radius="20px",
            background=rx.color_mode_cond(
                "linear-gradient(135deg, rgba(255,236,179,0.5), rgba(255,255,255,0.5))",
                "linear-gradient(135deg, rgba(120,80,0,0.18), rgba(255,255,255,0.02))",
            ),
            backdrop_filter="blur(8px)",
            width="100%",
        ),
        padding_y=["32px", "40px", "60px"],
    )


# ─── ページ ───────────────────────────────────────────────────────────────────


@template(
    route="/staking/why",
    title="ステーキングとは？ | ステーキング | Cardanoism",
)
def staking_why_page() -> rx.Component:
    return rx.box(
        rx.vstack(
            _breadcrumb(),
            staking_subnav("why"),
            spacing="3",
            width="100%",
            max_width="1130px",
            margin_x="auto",
            padding_x=["20px", "28px", "40px"],
        ),
        _hero(),
        _why_section(),
        _steps_section(),
        _checkpoints_section(),
        _timeline_section(),
        _faq_section(),
        _cta_section(),
        width="100%",
        max_width="100%",
    )
