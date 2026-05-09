"""pricing.py
プラン比較ページ (/pricing)

PLANS 設定 (plan_config.py) に基づいてカードを並べる。
ベータ期間中は Standard 機能解放のバナーを上部に表示。
"""
from __future__ import annotations

import logging

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.plan_config import PLANS, BETA_MODE, COMPARISON_SECTIONS, PlanDetails

logger = logging.getLogger(__name__)


ACCENT       = "#ffcf00"
ACCENT_DARK  = "#c7a300"
TEXT_MUTED   = "var(--gray-10)"


# ─── State ────────────────────────────────────────────────────────────────────


class PricingState(rx.State):
    # 月額 / 年額の切替トグル ("monthly" / "yearly")
    billing: str = "monthly"

    def set_monthly(self):
        self.billing = "monthly"

    def set_yearly(self):
        self.billing = "yearly"


# ─── 共通パーツ ────────────────────────────────────────────────────────────────


def _shell(*children, **kw) -> rx.Component:
    base = dict(
        max_width="1180px",
        width="100%",
        margin_x="auto",
        padding_x=["20px", "28px", "40px"],
    )
    base.update(kw)
    return rx.box(*children, **base)


def _breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(AuthState.t["pricing_title"], size="2", weight="medium"),
        spacing="2", align="center", width="100%", padding_top="15px",
    )


def _hero() -> rx.Component:
    return _shell(
        rx.vstack(
            rx.text(AuthState.t["pricing_kicker"], size="2", weight="bold",
                    color=ACCENT_DARK, letter_spacing="0.14em"),
            rx.heading(
                AuthState.t["pricing_title"],
                as_="h1",
                size={"base": "6", "md": "8"},
                weight="bold",
                line_height="1.2",
                style={"wordBreak": "break-word"},
            ),
            rx.text(
                AuthState.t["pricing_subtitle"],
                size={"base": "2", "md": "3"},
                color=TEXT_MUTED, line_height="1.7",
                max_width="720px",
                style={"wordBreak": "break-word"},
            ),
            spacing="3", align_items="start", width="100%",
        ),
        padding_y=["32px", "44px", "56px"],
    )


def _beta_banner() -> rx.Component:
    if not BETA_MODE:
        return rx.fragment()
    return _shell(
        rx.box(
            rx.vstack(
                rx.text(
                    AuthState.t["pricing_beta_banner_title"],
                    size={"base": "3", "md": "4"},
                    weight="bold", color="var(--amber-12)",
                    style={"wordBreak": "break-word"},
                ),
                rx.text(
                    AuthState.t["pricing_beta_banner_desc"],
                    size="2", color="var(--amber-11)", line_height="1.7",
                ),
                rx.text(
                    AuthState.t["pricing_beta_special_offer"],
                    size="1", color="var(--amber-11)", line_height="1.7",
                    style={"fontStyle": "italic"},
                ),
                spacing="2", align_items="start", width="100%",
            ),
            padding="16px 20px",
            border=f"1px solid var(--amber-7)",
            border_radius="14px",
            background=rx.color_mode_cond("rgba(255,243,199,0.6)", "rgba(120,80,0,0.18)"),
            width="100%",
        ),
        padding_y="0",
    )


def _billing_toggle_pills() -> rx.Component:
    """月額/年額切替ピル本体 (どこにでも埋め込める形)。"""
    def _pill(label_key: str, active, on_click) -> rx.Component:
        return rx.box(
            rx.text(
                AuthState.t[label_key], size="2", weight="bold",
                color=rx.cond(active, "var(--gray-12)", "var(--gray-11)"),
                style={"whiteSpace": "nowrap"},
            ),
            on_click=on_click,
            cursor="pointer",
            padding="6px 14px",
            border_radius="9999px",
            background=rx.cond(active, "var(--amber-3)", "transparent"),
            style={"transition": "background 0.15s, color 0.15s"},
            _hover=rx.cond(active, None, {"background": "var(--gray-3)"}),
        )
    return rx.hstack(
        _pill("pricing_billing_monthly", PricingState.billing == "monthly", PricingState.set_monthly),
        _pill("pricing_billing_yearly",  PricingState.billing == "yearly",  PricingState.set_yearly),
        spacing="1",
        padding="3px",
        border_radius="9999px",
        background="var(--gray-2)",
        border="1px solid var(--gray-5)",
        style={"flexShrink": "0"},
    )


def _format_price(jpy: int, usd: float) -> tuple[str, str]:
    """(JPY 表記, USD 表記)。0 の場合は無料表示。"""
    if jpy <= 0 and usd <= 0:
        return "¥0", "$0"
    return f"¥{jpy:,}", f"${usd:,.2f}".rstrip("0").rstrip(".") + ".99" if usd != round(usd) else f"${int(usd):,}"



# ─── 機能比較表 ───────────────────────────────────────────────────────────────


def _comparison_table() -> rx.Component:
    """プラン別機能比較表。横軸 = プラン、縦軸 = 機能。
    左 1 列を sticky にして、横スクロール時も機能名が見えるようにする。
    ヘッダーに価格 + CTA を組み込んで、別途プライシングカード行を不要に。
    """
    # 列幅: 機能名 20% + プラン × len(PLANS) で残り 80% を均等割り
    label_width_pct = 20
    plan_width_pct = (100 - label_width_pct) // len(PLANS)  # 5 プランなら 16%

    # ヘッダー行: 機能 | Free | Light | Standard | Plus | Pro
    header_cells = [
        rx.el.th(
            rx.text("", size="2"),
            style={
                "padding":     "12px 16px",
                "background":  "var(--gray-2)",
                "borderBottom": "1px solid var(--gray-6)",
                "borderRight": "1px solid var(--gray-6)",
                "position":    "sticky",
                "left":        0,
                "top":         0,
                "zIndex":      3,
                "width":       f"{label_width_pct}%",
                "minWidth":    "160px",
                "textAlign":   "left",
            },
        ),
    ]
    for plan in PLANS:
        color = plan["color"]
        is_popular = plan["popular"]
        is_free = (plan["tier"] == "free")
        jpy_m = plan["price_jpy_monthly"]
        usd_m = plan["price_usd_monthly"]
        jpy_y = plan["price_jpy_yearly"]
        usd_y = plan["price_usd_yearly"]
        monthly_jpy = "¥0" if jpy_m == 0 else f"¥{jpy_m:,}"
        monthly_usd = "$0" if usd_m == 0 else f"${usd_m:.2f}"
        yearly_jpy = "¥0" if jpy_y == 0 else f"¥{jpy_y:,}"
        yearly_usd = "$0" if usd_y == 0 else f"${usd_y:.2f}"

        # 月額 × 12 (打ち消し線で表示する元値)。Free は 0 なので非表示。
        crossed_jpy = f"¥{jpy_m * 12:,}" if jpy_m > 0 else ""
        crossed_usd = f"${usd_m * 12:.2f}" if usd_m > 0 else ""
        crossed_display = rx.cond(AuthState.language == "en", crossed_usd, crossed_jpy)
        has_crossed = (jpy_m > 0)

        # 価格 (月額/年額切替 + 言語別通貨)。EN なら USD、JA なら JPY を表示。
        monthly_display = rx.cond(AuthState.language == "en", monthly_usd, monthly_jpy)
        yearly_display  = rx.cond(AuthState.language == "en", yearly_usd,  yearly_jpy)

        # 年額時に上部へ「月額 × 12 (打消線)」を表示
        crossed_row = rx.cond(
            PricingState.billing == "yearly",
            rx.text(
                crossed_display,
                size="1",
                color=TEXT_MUTED,
                style={
                    "textDecoration": "line-through",
                    "lineHeight":     "1.2",
                    "minHeight":      "16px",
                },
            ),
            rx.box(style={"minHeight": "16px"}),  # 月額時もスペース確保で列高を揃える
        ) if has_crossed else rx.box(style={"minHeight": "16px"})

        price_block = rx.vstack(
            crossed_row,
            rx.cond(
                PricingState.billing == "monthly",
                rx.hstack(
                    rx.text(monthly_display, size="5", weight="bold", color="var(--gray-12)",
                            style={"letterSpacing": "-0.02em", "lineHeight": "1"}),
                    rx.text(AuthState.t["pricing_per_month"], size="1", color=TEXT_MUTED),
                    spacing="1", align="end",
                ),
                rx.hstack(
                    rx.text(yearly_display, size="5", weight="bold", color="var(--gray-12)",
                            style={"letterSpacing": "-0.02em", "lineHeight": "1"}),
                    rx.text(AuthState.t["pricing_per_year"], size="1", color=TEXT_MUTED),
                    spacing="1", align="end",
                ),
            ),
            spacing="0", align="center",
        )

        # CTA: 未ログインで Free だけ「無料で始める」、他は「選択」
        logged_in_href = "/mypage" if is_free else "/mypage?tab=subscription"
        not_logged_in_label_key = "pricing_signup" if is_free else "pricing_select"
        cta = rx.cond(
            AuthState.is_logged_in,
            rx.link(
                rx.button(
                    AuthState.t["pricing_select"],
                    rx.icon("arrow-right", size=12),
                    size="2", cursor="pointer",
                    background=color, color="white",
                    _hover={"opacity": "0.92"},
                    style={"boxShadow": f"0 6px 18px -10px {color}"},
                ),
                href=logged_in_href, underline="none",
            ),
            rx.link(
                rx.button(
                    AuthState.t[not_logged_in_label_key],
                    rx.icon("arrow-right", size=12),
                    size="2", cursor="pointer",
                    background=color, color="white",
                    _hover={"opacity": "0.92"},
                    style={"boxShadow": f"0 6px 18px -10px {color}"},
                ),
                href="/login", underline="none",
            ),
        )

        header_cells.append(
            rx.el.th(
                rx.vstack(
                    rx.text(AuthState.t[plan["name_key"]],
                            size="4", weight="bold", color="var(--gray-12)"),
                    rx.text(AuthState.t[plan["tagline_key"]],
                            size="1", color=TEXT_MUTED, line_height="1.5",
                            style={
                                "wordBreak": "break-word",
                                "minHeight": "44px",  # 2 行分確保 (1 行のプランと高さを合わせる)
                                "display":   "flex",
                                "alignItems": "center",
                                "justifyContent": "center",
                                "textAlign": "center",
                            }),
                    rx.box(height="3px", width="42px",
                           border_radius="999px", background=color),
                    price_block,
                    rx.box(cta, style={"marginTop": "auto"}),
                    spacing="2", align="center",
                    style={"minWidth": "0", "height": "100%"},
                ),
                style={
                    "padding":      "16px 12px",
                    "textAlign":    "center",
                    "verticalAlign": "top",
                    "background":   "var(--gray-2)",
                    "borderBottom": "1px solid var(--gray-6)",
                    "position":     "sticky",
                    "top":          0,
                    "zIndex":       2,
                    "width":        f"{plan_width_pct}%",
                    "minWidth":     "120px",
                },
            )
        )

    # データ行: カテゴリ見出し + 機能行を交互に並べる
    body_rows: list[rx.Component] = []
    for cat_key, rows in COMPARISON_SECTIONS:
        # カテゴリ見出し行
        body_rows.append(
            rx.el.tr(
                rx.el.td(
                    rx.text(
                        AuthState.t[cat_key],
                        size="2", weight="bold",
                        color="var(--gray-12)",
                        style={"letterSpacing": "0.04em"},
                    ),
                    col_span=len(PLANS) + 1,
                    style={
                        "padding":    "12px 16px",
                        "background": "var(--gray-3)",
                        "borderBottom": "1px solid var(--gray-6)",
                    },
                ),
            )
        )
        # 機能行
        for label_key, cells in rows:
            row_cells = [
                rx.el.td(
                    rx.text(AuthState.t[label_key], size="2", color="var(--gray-12)",
                            style={"wordBreak": "break-word"}),
                    style={
                        "padding":      "12px 16px",
                        "borderBottom": "1px solid var(--gray-5)",
                        "borderRight":  "1px solid var(--gray-5)",
                        "background":   "var(--gray-1)",
                        "position":     "sticky",
                        "left":         0,
                        "zIndex":       1,
                        "minWidth":     "160px",
                    },
                ),
            ]
            for cell in cells:
                if cell == "check":
                    body = rx.icon("check", size=18, color="var(--green-10)")
                elif cell == "—":
                    body = rx.text("—", size="2", color="var(--gray-9)")
                else:
                    body = rx.text(cell, size="2", weight="bold", color="var(--gray-12)")
                row_cells.append(
                    rx.el.td(
                        rx.center(body, width="100%"),
                        style={
                            "padding":      "12px",
                            "textAlign":    "center",
                            "verticalAlign": "middle",
                            "borderBottom": "1px solid var(--gray-5)",
                            "background":   "var(--gray-1)",
                        },
                    )
                )
            body_rows.append(rx.el.tr(*row_cells))

    return _shell(
        rx.vstack(
            # 見出し + サブタイトル を左、月額/年額トグルを右に配置
            rx.flex(
                rx.vstack(
                    rx.heading(
                        AuthState.t["plan_compare_title"],
                        as_="h2",
                        size={"base": "5", "md": "6"},
                        weight="bold",
                        color="var(--gray-12)",
                    ),
                    rx.text(
                        AuthState.t["plan_compare_subtitle"],
                        size="2", color=TEXT_MUTED, line_height="1.7",
                    ),
                    spacing="2", align_items="start",
                    style={"flex": "1 1 auto", "minWidth": "0"},
                ),
                _billing_toggle_pills(),
                spacing="4",
                align={"base": "start", "md": "center"},
                wrap="wrap",
                width="100%",
            ),
            # おすすめバッジ行 (テーブル外、列幅と揃えて浮かせる)
            rx.flex(
                rx.box(
                    width=f"{label_width_pct}%",
                    style={"flexShrink": "0"},
                ),
                *[
                    rx.box(
                        rx.center(
                            rx.badge(
                                AuthState.t["pricing_popular_badge"],
                                color_scheme="amber",
                                variant="solid", size="2", radius="full",
                            ),
                            width="100%",
                        ) if plan["popular"] else rx.fragment(),
                        width=f"{plan_width_pct}%",
                        style={"flexShrink": "0"},
                    )
                    for plan in PLANS
                ],
                width="100%",
                style={
                    "position":      "relative",
                    "marginBottom":  "-14px",  # テーブル上端に被せる
                    "zIndex":        2,
                    "pointerEvents": "none",
                },
            ),
            rx.box(
                rx.el.table(
                    rx.el.thead(rx.el.tr(*header_cells)),
                    rx.el.tbody(*body_rows),
                    style={
                        "borderCollapse": "separate",
                        "borderSpacing":  0,
                        "width":          "100%",
                        "tableLayout":    "fixed",
                    },
                ),
                style={
                    "overflowX":    "auto",  # 幅が足りない時だけ横スクロール
                    "width":        "100%",
                    "border":       "1px solid var(--gray-6)",
                    "borderRadius": "12px",
                    "background":   "var(--gray-1)",
                    "minWidth":     "0",
                },
            ),
            spacing="3", align_items="start", width="100%",
        ),
        padding_y=["28px", "36px", "48px"],
        max_width="100%",  # 比較表セクションは全幅伸縮
    )


# ─── ページ ───────────────────────────────────────────────────────────────────


@template(
    route="/pricing",
    title="プラン比較 | Cardanoism",
)
def pricing_page() -> rx.Component:
    return rx.box(
        rx.vstack(
            _breadcrumb(),
            spacing="3",
            width="100%",
            max_width="1180px",
            margin_x="auto",
            padding_x=["20px", "28px", "40px"],
        ),
        _hero(),
        _beta_banner(),
        _comparison_table(),
        rx.box(height="40px"),  # bottom padding
        width="100%",
        max_width="100%",
    )
