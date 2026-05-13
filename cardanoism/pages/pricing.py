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
from cardanoism.components.breadcrumb import breadcrumb

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
    # 他のページ (staking_spo / governance 等) と幅を統一する。
    # template_page_style.max-width=1130px と一致させ、左右パディングは
    # テンプレート側に任せて _shell では追加しない (二重パディングを避ける)。
    base = dict(
        max_width="1130px",
        width="100%",
        margin_x="auto",
    )
    base.update(kw)
    return rx.box(*children, **base)


def _breadcrumb() -> rx.Component:
    return breadcrumb([], "pricing_title")


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


def _adjustment_note() -> rx.Component:
    """プラン・料金が確定前である旨の注意書き。比較表の直前に表示。"""
    return _shell(
        rx.hstack(
            rx.icon(tag="info", size=18, color="var(--amber-11)"),
            rx.text(
                AuthState.t["pricing_adjustment_note"],
                size={"base": "2", "md": "3"},
                color="var(--amber-11)",
                line_height="1.6",
                style={"fontStyle": "italic"},
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        padding_y=["24px", "32px", "40px"],
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



# ─── スマホ向け プラン別カード ─────────────────────────────────────────────────


def _mobile_feature_row(label_key: str, cell_value: str) -> rx.Component:
    """スマホカード 1 機能行。
    cell_value:
      - "check" → ✓ アイコン + 機能名
      - "—"     → 表示しない (None を返す)
      - その他   → 機能名: 値 (例「ステークアドレス上限: 3」)
    """
    if cell_value == "—":
        return rx.fragment()
    if cell_value == "check":
        return rx.hstack(
            rx.icon("check", size=16, color="var(--green-10)", flex_shrink="0"),
            rx.text(AuthState.t[label_key], size="2", color="var(--gray-12)"),
            spacing="2", align="center", width="100%",
        )
    # 数値・記号系 (5 / 10 / ∞ 等)
    return rx.hstack(
        rx.text(AuthState.t[label_key], size="2", color="var(--gray-11)"),
        rx.spacer(),
        rx.text(cell_value, size="2", weight="bold", color="var(--gray-12)"),
        spacing="2", align="center", width="100%",
    )


_TIER_NAME_JA = {
    "free":     "フリー",
    "light":    "ライト",
    "standard": "スタンダード",
    "plus":     "プラス",
    "pro":      "プロ",
}


def _mobile_plan_card(plan: PlanDetails, plan_idx: int) -> rx.Component:
    """スマホ向け 1 プランカード。比較表の対象プラン列を縦に展開。"""
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
    monthly_display = rx.cond(AuthState.language == "en", monthly_usd, monthly_jpy)
    yearly_display  = rx.cond(AuthState.language == "en", yearly_usd,  yearly_jpy)

    # 価格 + 期間ラベル
    price_block = rx.cond(
        PricingState.billing == "monthly",
        rx.hstack(
            rx.text(monthly_display, size="7", weight="bold", color="var(--gray-12)",
                    style={"letterSpacing": "-0.02em"}),
            rx.text(AuthState.t["pricing_per_month"], size="2", color=TEXT_MUTED),
            spacing="1", align="baseline",
        ),
        rx.hstack(
            rx.text(yearly_display, size="7", weight="bold", color="var(--gray-12)",
                    style={"letterSpacing": "-0.02em"}),
            rx.text(AuthState.t["pricing_per_year"], size="2", color=TEXT_MUTED),
            spacing="1", align="baseline",
        ),
    )

    # CTA: ベータ中は「準備中」disabled。それ以外は選択 / 無料で始める
    not_logged_in_label_key = "pricing_signup" if is_free else "pricing_select"
    if BETA_MODE:
        cta_btn = rx.button(
            AuthState.t["pricing_coming_soon"],
            size="3", disabled=True,
            style={
                "background": "var(--gray-4)",
                "color":      "var(--gray-10)",
                "cursor":     "not-allowed",
                "border":     "1px solid var(--gray-6)",
                "width":      "100%",
            },
        )
    else:
        logged_in_href = "/mypage" if is_free else "/mypage?tab=subscription"
        cta_btn = rx.cond(
            AuthState.is_logged_in,
            rx.link(
                rx.button(
                    AuthState.t["pricing_select"],
                    rx.icon("arrow-right", size=14),
                    size="3", cursor="pointer",
                    background=color, color="white",
                    style={"width": "100%"},
                ),
                href=logged_in_href, underline="none", width="100%",
            ),
            rx.link(
                rx.button(
                    AuthState.t[not_logged_in_label_key],
                    rx.icon("arrow-right", size=14),
                    size="3", cursor="pointer",
                    background=color, color="white",
                    style={"width": "100%"},
                ),
                href="/login", underline="none", width="100%",
            ),
        )

    # 機能リスト: COMPARISON_SECTIONS を回し、対象プラン列の値で表示分岐
    feature_sections: list[rx.Component] = []
    for cat_key, rows in COMPARISON_SECTIONS:
        section_rows: list[rx.Component] = []
        for label_key, cells in rows:
            cell = cells[plan_idx] if plan_idx < len(cells) else "—"
            if cell == "—":
                continue
            section_rows.append(_mobile_feature_row(label_key, cell))
        if not section_rows:
            continue
        feature_sections.append(
            rx.vstack(
                rx.text(
                    AuthState.t[cat_key],
                    size="1", weight="bold",
                    color="var(--gray-10)",
                    style={"letterSpacing": "0.08em", "textTransform": "uppercase"},
                ),
                rx.vstack(*section_rows, spacing="2", align_items="stretch", width="100%"),
                spacing="2", align_items="stretch", width="100%",
            )
        )

    # プラン名はスマホでは日本語 (フリー / ライト / スタンダード / プラス / プロ) を優先表示。
    # EN モード時は i18n の英語名にフォールバック。
    name_ja = _TIER_NAME_JA.get(plan["tier"], plan["tier"])
    name_display = rx.cond(
        AuthState.language == "ja",
        rx.Var.create(name_ja),
        AuthState.t[plan["name_key"]],
    )

    # ヘッダー部 (おすすめバッジ + プラン名 + サブ)
    header = rx.vstack(
        rx.cond(
            rx.Var.create(is_popular),
            rx.badge(
                AuthState.t["pricing_popular_badge"],
                color_scheme="amber",
                variant="solid", size="2", radius="full",
            ),
            rx.fragment(),
        ),
        rx.text(name_display,
                size="6", weight="bold", color="var(--gray-12)"),
        rx.text(AuthState.t[plan["tagline_key"]],
                size="2", color=TEXT_MUTED, line_height="1.6"),
        rx.box(height="4px", width="48px",
               border_radius="999px", background=color, margin_top="4px"),
        spacing="2", align_items="start", width="100%",
    )

    return rx.box(
        rx.vstack(
            header,
            price_block,
            cta_btn,
            rx.divider(margin_y="4px"),
            rx.vstack(*feature_sections, spacing="5", align_items="stretch", width="100%"),
            spacing="4", align_items="stretch", width="100%",
        ),
        padding="22px 20px",
        border_radius="14px",
        border=rx.cond(
            rx.Var.create(is_popular),
            "2px solid var(--amber-8)",
            f"1px solid var(--gray-5)",
        ),
        background="var(--gray-1)",
        width="100%",
        style={
            "boxShadow": rx.cond(
                rx.Var.create(is_popular),
                "0 10px 30px -12px rgba(245,158,11,0.35)",
                "0 1px 3px rgba(15,23,42,0.05)",
            ),
        },
    )


def _mobile_plan_cards() -> rx.Component:
    """スマホ用: プラン別カードを縦に並べる。
    並び順は PLANS の定義順 (フリー → ライト → スタンダード → プラス → プロ)。
    """
    cards = [
        _mobile_plan_card(plan, idx) for idx, plan in enumerate(PLANS)
    ]
    return rx.vstack(
        rx.flex(
            rx.vstack(
                rx.heading(
                    AuthState.t["plan_compare_title"],
                    as_="h2",
                    size="5",
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
            spacing="3",
            wrap="wrap",
            width="100%",
        ),
        # 月額/年額トグルを単独行で
        rx.box(_billing_toggle_pills()),
        *cards,
        spacing="5", align_items="stretch", width="100%",
    )


# ─── 機能比較表 (デスクトップ用) ──────────────────────────────────────────────


def _comparison_table() -> rx.Component:
    """プラン別機能比較表。横軸 = プラン、縦軸 = 機能。
    左 1 列を sticky にして、横スクロール時も機能名が見えるようにする。
    ヘッダーに価格 + CTA を組み込んで、別途プライシングカード行を不要に。

    スマホでは横スクロール前提で、各セルの min-width で読みやすさを確保する。
    """
    # ヘッダー行: 機能 | Free | Light | Standard | Plus | Pro
    # 左 1 列 (機能名) は sticky で横スクロール時も見えるようにする。
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
                "minWidth":    "180px",
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

        # CTA: ベータ期間中は全プランの申込導線を「準備中」表示にする。
        # ベータ終了 (BETA_MODE=False) で従来の選択ボタンへ戻る。
        logged_in_href = "/mypage" if is_free else "/mypage?tab=subscription"
        not_logged_in_label_key = "pricing_signup" if is_free else "pricing_select"
        if BETA_MODE:
            cta = rx.button(
                AuthState.t["pricing_coming_soon"],
                size="2",
                disabled=True,
                style={
                    "background": "var(--gray-4)",
                    "color":      "var(--gray-10)",
                    "cursor":     "not-allowed",
                    "border":     "1px solid var(--gray-6)",
                },
            )
        else:
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

        # 横スクロール時に各カラム内で要素が一緒に動くよう、おすすめバッジは
        # ヘッダーセル内部の先頭に配置する (以前は外側 flex で浮かせていた)。
        popular_badge = rx.cond(
            rx.Var.create(is_popular),
            rx.badge(
                AuthState.t["pricing_popular_badge"],
                color_scheme="amber",
                variant="solid", size="2", radius="full",
            ),
            rx.box(style={"minHeight": "24px"}),  # バッジ無しでも高さ揃え
        )

        header_cells.append(
            rx.el.th(
                rx.vstack(
                    popular_badge,
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
                    "minWidth":     "150px",
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
                        "minWidth":     "180px",
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

    desktop_table = rx.vstack(
        # 見出し + サブタイトル を左、月額/年額トグルを右に配置
        rx.flex(
            rx.vstack(
                rx.heading(
                    AuthState.t["plan_compare_title"],
                    as_="h2",
                    size="6",
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
            align="center",
            wrap="wrap",
            width="100%",
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
                "width":        "100%",
                "border":       "1px solid var(--gray-6)",
                "borderRadius": "12px",
                "background":   "var(--gray-1)",
            },
        ),
        spacing="3", align_items="start", width="100%",
    )

    return _shell(
        # スマホ (< 768px): カードレイアウト / それ以上: テーブル
        rx.box(
            _mobile_plan_cards(),
            style={
                "display": "block",
                "@media (min-width: 768px)": {"display": "none"},
            },
            width="100%",
        ),
        rx.box(
            desktop_table,
            style={
                "display": "none",
                "@media (min-width: 768px)": {"display": "block"},
            },
            width="100%",
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
            max_width="1130px",
            margin_x="auto",
        ),
        _hero(),
        _beta_banner(),
        _adjustment_note(),
        _comparison_table(),
        rx.box(height="40px"),  # bottom padding
        width="100%",
        max_width="100%",
    )
