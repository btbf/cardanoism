"""help.py
使い方ガイド (/help) — ドキュメント / Notion 風スタイル。

左に sticky な階層目次、右に章立て本文。GitBook / Notion / ソフトウェアドキュメント
で見慣れたレイアウト。装飾は最小限、可読性とスキャナビリティ重視。

章構成:
  1. はじめに
  2. スタートアップ (サインイン / アドレス登録 / ウォレット認証)
  3. ダッシュボード
  4. 通知 (チャンネル / ステーキング 8 / ガバナンス 5)
  5. ガバナンス提案 (日本語訳 / AI 要約 / 投票集計)
  6. ステーキング・委任
  7. データ探索 (SPO / DRep / カタリスト / 憲法 / トレジャリー / ネットワーク)
  8. 学習リソース
  9. その他
"""
from __future__ import annotations

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState


TEXT_MAIN  = "var(--gray-12)"
TEXT_BODY  = "var(--gray-12)"
TEXT_MUTED = "var(--gray-10)"
TEXT_DIM   = "var(--gray-9)"

CALLOUT = {
    "hint":    ("#0ea5e9", "lightbulb",     "doc_callout_hint"),
    "tip":     ("#10b981", "sparkles",      "doc_callout_tip"),
    "warning": ("#f59e0b", "triangle-alert","doc_callout_warning"),
}


# ─── 共通ヘルパー ─────────────────────────────────────────────────────────

def _shell(*children, **kw) -> rx.Component:
    base = dict(
        max_width="1240px",
        width="100%",
        margin_x="auto",
        padding_x=["16px", "24px", "32px"],
    )
    base.update(kw)
    return rx.box(*children, **base)


# ─── 本文プリミティブ ────────────────────────────────────────────────────

def _h2(num: str, title_key: str, anchor: str) -> rx.Component:
    return rx.box(
        rx.heading(
            rx.hstack(
                rx.text(num, color=TEXT_DIM, weight="bold",
                        style={"flexShrink": 0, "fontVariantNumeric": "tabular-nums"}),
                rx.text(AuthState.t[title_key], weight="bold", color=TEXT_MAIN),
                spacing="3", align="baseline",
            ),
            as_="h2",
            size={"base": "6", "md": "7"},
            style={"letterSpacing": "-0.01em"},
        ),
        id=anchor,
        style={
            "scrollMarginTop": "80px",
            "marginTop": "64px",
            "marginBottom": "16px",
            "paddingBottom": "12px",
            "borderBottom": "1px solid var(--gray-5)",
        },
    )


def _h3(num: str, title_key: str, anchor: str) -> rx.Component:
    return rx.heading(
        rx.hstack(
            rx.text(num, color=TEXT_DIM, weight="bold",
                    style={"flexShrink": 0, "fontVariantNumeric": "tabular-nums"}),
            rx.text(AuthState.t[title_key], weight="bold", color=TEXT_MAIN),
            spacing="3", align="baseline",
        ),
        as_="h3",
        size={"base": "4", "md": "5"},
        id=anchor,
        style={
            "scrollMarginTop": "80px",
            "marginTop": "36px",
            "marginBottom": "10px",
            "letterSpacing": "-0.005em",
        },
    )


def _p(text_key: str) -> rx.Component:
    """段落。インラインコード風 `…` をハイライト表示する。"""
    text = AuthState.t[text_key]
    # i18n の `code` バックティック表記を <code> 風 span に変換
    # (Reflex の rx.text は HTML を扱わないので、文字列のまま渡すが見やすさのため line_height 等を整える)
    return rx.text(
        text,
        size="3",
        color=TEXT_BODY,
        style={
            "lineHeight": "1.85",
            "marginBottom": "14px",
            "maxWidth": "780px",
        },
    )


def _bullets(item_keys: list[str]) -> rx.Component:
    return rx.box(
        rx.vstack(
            *[
                rx.hstack(
                    rx.box(
                        style={
                            "width": "5px", "height": "5px",
                            "borderRadius": "999px",
                            "background": "var(--gray-10)",
                            "flexShrink": 0,
                            "marginTop": "11px",
                        },
                    ),
                    rx.text(
                        AuthState.t[k],
                        size="3", color=TEXT_BODY,
                        style={"lineHeight": "1.75"},
                    ),
                    spacing="3", align="start", width="100%",
                )
                for k in item_keys
            ],
            spacing="2", align_items="start", width="100%",
        ),
        style={
            "marginBottom": "14px",
            "marginTop": "6px",
            "maxWidth": "780px",
        },
    )


def _callout(variant: str, text_key: str) -> rx.Component:
    color, icon, label_key = CALLOUT[variant]
    return rx.box(
        rx.hstack(
            rx.box(
                rx.icon(icon, size=16, color=color),
                style={
                    "width": "26px", "height": "26px",
                    "borderRadius": "8px",
                    "background": f"{color}15",
                    "border": f"1px solid {color}30",
                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                    "flexShrink": 0,
                },
            ),
            rx.vstack(
                rx.text(
                    AuthState.t[label_key],
                    size="1", weight="bold", color=color,
                    style={"letterSpacing": "0.10em", "textTransform": "uppercase"},
                ),
                rx.text(
                    AuthState.t[text_key],
                    size="2", color=TEXT_BODY,
                    style={"lineHeight": "1.7"},
                ),
                spacing="1", align_items="start",
            ),
            spacing="3", align="start", width="100%",
        ),
        padding="14px 16px",
        border_radius="10px",
        border=f"1px solid {color}30",
        background=f"{color}0c",
        style={
            "marginTop": "10px",
            "marginBottom": "16px",
            "maxWidth": "780px",
        },
    )


def _link_button(text_key: str, href: str, icon: str = "arrow-up-right") -> rx.Component:
    """章末などに置く外部ジャンプボタン。"""
    return rx.link(
        rx.hstack(
            rx.text(AuthState.t[text_key], size="2", weight="medium", color="var(--amber-11)"),
            rx.icon(icon, size=14, color="var(--amber-11)"),
            spacing="2", align="center",
        ),
        href=href, underline="none",
        style={
            "padding": "6px 12px",
            "borderRadius": "8px",
            "border": "1px solid var(--amber-7)",
            "background": "var(--amber-2)",
            "display": "inline-flex",
            "marginRight": "8px",
            "marginTop": "8px",
        },
        _hover={"background": "var(--amber-3)"},
    )


def _link_row(*links) -> rx.Component:
    return rx.flex(*links, wrap="wrap", gap="6px", style={"marginBottom": "16px"})


# ─── 目次 (左サイドバー) ─────────────────────────────────────────────────

# (番号, i18n_key, anchor_id, インデント)
_TOC: list[tuple[str, str, str, bool]] = [
    ("1",   "doc_toc_1",     "intro",        False),
    ("2",   "doc_toc_2",     "startup",      False),
    ("2.1", "doc_toc_2_1",   "signin",       True),
    ("2.2", "doc_toc_2_2",   "register",     True),
    ("2.3", "doc_toc_2_3",   "verify",       True),
    ("3",   "doc_toc_3",     "dashboard",    False),
    ("4",   "doc_toc_4",     "notify",       False),
    ("4.1", "doc_toc_4_1",   "channels",     True),
    ("4.2", "doc_toc_4_2",   "stk-events",   True),
    ("4.3", "doc_toc_4_3",   "gov-events",   True),
    ("5",   "doc_toc_5",     "governance",   False),
    ("5.1", "doc_toc_5_1",   "jp-trans",     True),
    ("5.2", "doc_toc_5_2",   "ai-facts",     True),
    ("5.3", "doc_toc_5_3",   "tally",        True),
    ("6",   "doc_toc_6",     "staking",      False),
    ("7",   "doc_toc_7",     "explore",      False),
    ("7.1", "doc_toc_7_1",   "spo-list",     True),
    ("7.2", "doc_toc_7_2",   "drep-list",    True),
    ("7.3", "doc_toc_7_3",   "catalyst",     True),
    ("7.4", "doc_toc_7_4",   "constitution", True),
    ("7.5", "doc_toc_7_5",   "treasury",     True),
    ("7.6", "doc_toc_7_6",   "network",      True),
    ("8",   "doc_toc_8",     "learn",        False),
    ("9",   "doc_toc_9",     "misc",         False),
]


def _toc_link(num: str, text_key: str, anchor: str, indent: bool) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.text(
                num,
                size="1",
                color=TEXT_MUTED,
                weight="medium",
                style={"flexShrink": 0, "minWidth": "26px",
                       "fontVariantNumeric": "tabular-nums"},
            ),
            rx.text(
                AuthState.t[text_key],
                size="2",
                color=TEXT_BODY if not indent else TEXT_MUTED,
                weight="medium" if not indent else "regular",
                style={"overflow": "hidden", "textOverflow": "ellipsis",
                       "whiteSpace": "nowrap"},
            ),
            spacing="2", align="center", width="100%",
        ),
        href=f"#{anchor}",
        underline="none",
        style={
            "display": "block",
            "paddingTop": "6px",
            "paddingBottom": "6px",
            "paddingLeft": "28px" if indent else "10px",
            "paddingRight": "10px",
            "borderRadius": "6px",
            "width": "100%",
            "boxSizing": "border-box",
            "transition": "background 0.12s ease",
        },
        _hover={
            "background": "var(--gray-3)",
        },
    )


def _toc() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(
                AuthState.t["doc_toc_label"],
                size="1",
                color=TEXT_MUTED,
                weight="bold",
                style={
                    "letterSpacing": "0.16em",
                    "textTransform": "uppercase",
                    "padding": "0 10px 8px",
                },
            ),
            rx.vstack(
                *[_toc_link(n, k, a, i) for (n, k, a, i) in _TOC],
                spacing="0", align_items="start", width="100%",
            ),
            spacing="1", align_items="start", width="100%",
        ),
        padding_y="20px",
        padding_right="16px",
        style={
            "position": "sticky",
            "top": "80px",
            "alignSelf": "start",
            "maxHeight": "calc(100vh - 100px)",
            "overflowY": "auto",
            "overflowX": "hidden",
            "borderRight": "1px solid var(--gray-5)",
        },
    )


# ─── ドキュメントヘッダ ──────────────────────────────────────────────────

def _doc_header() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("book-open", size=14, color="var(--amber-11)"),
                rx.text(
                    AuthState.t["doc_kicker"],
                    size="1", weight="bold", color="var(--amber-11)",
                    style={"letterSpacing": "0.18em"},
                ),
                spacing="2", align="center",
            ),
            rx.heading(
                AuthState.t["doc_title"],
                as_="h1",
                size={"base": "7", "md": "8"},
                weight="bold",
                color=TEXT_MAIN,
                style={"letterSpacing": "-0.015em", "marginTop": "8px"},
            ),
            rx.text(
                AuthState.t["doc_lead"],
                size="3",
                color=TEXT_MUTED,
                style={"lineHeight": "1.75", "maxWidth": "780px", "marginTop": "8px"},
            ),
            spacing="2", align_items="start", width="100%",
        ),
        padding_bottom="32px",
        margin_bottom="16px",
        border_bottom="1px solid var(--gray-5)",
    )


# ─── 本文 (各章) ─────────────────────────────────────────────────────────

def _ch1_intro() -> rx.Component:
    return rx.box(
        _h2("1", "doc_toc_1", "intro"),
        _p("doc_s1_p1"),
        _p("doc_s1_p2"),
        _callout("hint", "doc_s1_hint"),
    )


def _ch2_startup() -> rx.Component:
    return rx.box(
        _h2("2", "doc_toc_2", "startup"),
        _p("doc_s2_intro"),
        _h3("2.1", "doc_toc_2_1", "signin"),
        _p("doc_s2_1_p"),
        _link_row(_link_button("nav_login", "/login")),
        _h3("2.2", "doc_toc_2_2", "register"),
        _p("doc_s2_2_p"),
        _callout("tip", "doc_s2_2_tip"),
        _link_row(_link_button("help_wallet_link", "/mypage?tab=stake")),
        _h3("2.3", "doc_toc_2_3", "verify"),
        _p("doc_s2_3_p"),
    )


def _ch3_dashboard() -> rx.Component:
    return rx.box(
        _h2("3", "doc_toc_3", "dashboard"),
        _p("doc_s3_p1"),
        _bullets([
            "doc_s3_b1", "doc_s3_b2", "doc_s3_b3",
            "doc_s3_b4", "doc_s3_b5", "doc_s3_b6",
        ]),
        _link_row(_link_button("help_dashboard_link", "/mypage")),
    )


def _ch4_notify() -> rx.Component:
    return rx.box(
        _h2("4", "doc_toc_4", "notify"),
        _p("doc_s4_p1"),
        _h3("4.1", "doc_toc_4_1", "channels"),
        _p("doc_s4_1_p"),
        _bullets(["doc_s4_1_b1", "doc_s4_1_b2", "doc_s4_1_b3"]),
        _h3("4.2", "doc_toc_4_2", "stk-events"),
        _p("doc_s4_2_p"),
        _bullets([
            "help_notify_stk1_title", "help_notify_stk2_title", "help_notify_stk3_title",
            "help_notify_stk4_title", "help_notify_stk5_title", "help_notify_stk6_title",
            "help_notify_stk7_title", "help_notify_stk8_title",
        ]),
        _h3("4.3", "doc_toc_4_3", "gov-events"),
        _p("doc_s4_3_p"),
        _bullets([
            "help_notify_gov1_title", "help_notify_gov2_title", "help_notify_gov3_title",
            "help_notify_gov4_title", "help_notify_gov5_title",
        ]),
        _link_row(_link_button("help_notify_link", "/mypage?tab=notification")),
    )


def _ch5_governance() -> rx.Component:
    return rx.box(
        _h2("5", "doc_toc_5", "governance"),
        _p("doc_s5_p1"),
        _h3("5.1", "doc_toc_5_1", "jp-trans"),
        _p("doc_s5_1_p"),
        _h3("5.2", "doc_toc_5_2", "ai-facts"),
        _p("doc_s5_2_p"),
        _callout("warning", "doc_s5_2_warning"),
        _h3("5.3", "doc_toc_5_3", "tally"),
        _p("doc_s5_3_p"),
        _link_row(_link_button("help_data_f3_link", "/governance")),
    )


def _ch6_staking() -> rx.Component:
    return rx.box(
        _h2("6", "doc_toc_6", "staking"),
        _p("doc_s6_p1"),
        _p("doc_s6_p2"),
        _callout("hint", "doc_s6_hint"),
        _link_row(
            _link_button("help_data_f1_link", "/staking/spo"),
            _link_button("help_data_f2_link", "/governance/drep"),
        ),
    )


def _ch7_explore() -> rx.Component:
    return rx.box(
        _h2("7", "doc_toc_7", "explore"),
        _p("doc_s7_p1"),
        _h3("7.1", "doc_toc_7_1", "spo-list"),
        _p("doc_s7_1_p"),
        _link_row(_link_button("help_data_f1_link", "/staking/spo")),
        _h3("7.2", "doc_toc_7_2", "drep-list"),
        _p("doc_s7_2_p"),
        _link_row(_link_button("help_data_f2_link", "/governance/drep")),
        _h3("7.3", "doc_toc_7_3", "catalyst"),
        _p("doc_s7_3_p"),
        _link_row(_link_button("help_data_f5_link", "/catalyst")),
        _h3("7.4", "doc_toc_7_4", "constitution"),
        _p("doc_s7_4_p"),
        _link_row(_link_button("help_data_f7_link", "/constitution")),
        _h3("7.5", "doc_toc_7_5", "treasury"),
        _p("doc_s7_5_p"),
        _link_row(_link_button("help_data_f6_link", "/governance/treasury")),
        _h3("7.6", "doc_toc_7_6", "network"),
        _p("doc_s7_6_p"),
        _link_row(_link_button("help_network_link", "/staking")),
    )


def _ch8_learn() -> rx.Component:
    return rx.box(
        _h2("8", "doc_toc_8", "learn"),
        _p("doc_s8_p1"),
        _link_row(
            _link_button("help_learn_f1_link", "/staking/why"),
            _link_button("help_learn_f2_link", "/governance/why"),
        ),
    )


def _ch9_misc() -> rx.Component:
    return rx.box(
        _h2("9", "doc_toc_9", "misc"),
        _bullets(["doc_s9_b1", "doc_s9_b2", "doc_s9_b3"]),
    )


# ─── 末尾の CTA ──────────────────────────────────────────────────────────

def _doc_cta() -> rx.Component:
    cta_href = rx.cond(
        AuthState.is_logged_in,
        rx.cond(AuthState.is_stake_addresses_empty, "/mypage?tab=stake", "/mypage"),
        "/login",
    )
    return rx.box(
        rx.vstack(
            rx.heading(
                AuthState.t["doc_cta_title"],
                as_="h2",
                size="6",
                weight="bold",
                color=TEXT_MAIN,
            ),
            rx.text(
                AuthState.t["doc_cta_lead"],
                size="3", color=TEXT_MUTED,
                style={"lineHeight": "1.7", "maxWidth": "640px"},
            ),
            rx.link(
                rx.button(
                    AuthState.t["doc_cta_button"],
                    rx.icon("arrow-right", size=16),
                    size="3", color_scheme="amber", variant="solid",
                    cursor="pointer",
                    style={"borderRadius": "10px", "padding": "0 22px"},
                ),
                href=cta_href, underline="none", margin_top="6px",
            ),
            spacing="3", align_items="start",
        ),
        margin_top="64px",
        padding="28px",
        border_radius="14px",
        border="1px solid",
        border_color=rx.color_mode_cond("var(--amber-6)", "rgba(245,158,11,0.30)"),
        background=rx.color_mode_cond(
            "linear-gradient(135deg, #fffdf5 0%, #fff5d6 100%)",
            "linear-gradient(135deg, rgba(245,158,11,0.06) 0%, rgba(245,158,11,0.02) 100%)",
        ),
    )


def _content() -> rx.Component:
    return rx.box(
        _doc_header(),
        _ch1_intro(),
        _ch2_startup(),
        _ch3_dashboard(),
        _ch4_notify(),
        _ch5_governance(),
        _ch6_staking(),
        _ch7_explore(),
        _ch8_learn(),
        _ch9_misc(),
        _doc_cta(),
        padding_y="40px",
        padding_left=["0", "0", "40px"],
        padding_right="20px",
        width="100%",
    )


# ─── ページ本体 ──────────────────────────────────────────────────────────

@template(
    route="/help",
    title="使い方ガイド | Cardanoism",
    description="Cardanoism の使い方を章立てで解説したドキュメントページ。サインインから委任、ガバナンス参加までを詳細に網羅しています。",
)
def help_page() -> rx.Component:
    return _shell(
        rx.box(
            # PC: 左 TOC + 右本文 / モバイル: 本文のみ (TOC は折りたたみ)
            rx.tablet_and_desktop(_toc()),
            _content(),
            display="grid",
            grid_template_columns=["1fr", "1fr", "260px 1fr", "280px 1fr"],
            gap=["0", "0", "32px"],
            width="100%",
            align_items="start",
        ),
        padding_top="20px",
        padding_bottom="40px",
    )
