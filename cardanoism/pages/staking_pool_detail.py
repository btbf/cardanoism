"""
staking_pool_detail.py
ステークプール個別ページ（/pool/[pool_id]）

pools テーブルの 1 プールについて、委任者向けの情報をまとめて表示する。
委任 CTA は SPO 一覧と同じ WalletState.request_delegate_to_pool + delegation_dialog を再利用する。
SPO 向け / メタデータ整合性チェックは Phase B で追加予定。
"""
from __future__ import annotations

import logging

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.wallet_state import WalletState
from cardanoism.backend.pool_db import get_pool
from cardanoism.backend.koios import get_totals
from cardanoism.components.breadcrumb import breadcrumb
from cardanoism.components.staking_nav import staking_subnav
from cardanoism.components.delegation_dialog import delegation_dialog
from cardanoism.pages.staking_spo import (
    format_pool_card_data,
    _saturation_bar,
    _relay_status,
    _social_link,
    _metric,
    _ada_metric_with_tooltip,
    SPO_CSS,
    MAX_SUPPLY_LOVELACE,
    OPTIMAL_POOL_COUNT_K,
)

logger = logging.getLogger(__name__)


# ─── State ────────────────────────────────────────────────────────────────────


class PoolDetailState(rx.State):
    load: bool = False
    not_found: bool = False
    error: str = ""

    # pools 1 行を整形した表示用 dict（format_pool_card_data + 詳細用フィールド）
    pool: dict[str, str] = {}

    def on_load(self):
        self.load = False
        self.not_found = False
        self.error = ""
        self.pool = {}
        try:
            # URL 末尾から pool_id を取得
            path = self.router.url.path or ""
            parts = [p for p in path.split("/") if p]
            pool_id = parts[-1] if parts else ""
            if not pool_id:
                self.not_found = True
                return

            row = get_pool(pool_id)
            if not row:
                self.not_found = True
                return

            # 飽和点（= ソフトキャップ / 500）を /totals から確定
            sat_point = 0
            try:
                totals = get_totals() or {}
                reserves = int(totals.get("reserves") or 0)
                if reserves > 0:
                    sat_point = (MAX_SUPPLY_LOVELACE - reserves) // OPTIMAL_POOL_COUNT_K
            except Exception as e:  # noqa: BLE001
                logger.warning("get_totals failed: %s", e)

            data = format_pool_card_data(row, saturation_point_lovelace=sat_point)

            # 詳細ページ専用の追加フィールド
            about_full = str(row.get("extended_about") or "").strip()
            if not about_full:
                about_full = str(row.get("description") or "").strip()
            data["about_full"] = about_full
            ae = row.get("active_epoch_no")
            data["active_epoch"] = str(ae) if ae is not None else ""

            self.pool = data
        except Exception as e:  # noqa: BLE001
            logger.exception("PoolDetailState.on_load: %s", e)
            self.error = str(e)
        finally:
            self.load = True


# ─── UI ────────────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return breadcrumb(
        [("nav_staking", "/staking"), ("staking_subnav_spo", "/staking/spo")],
        "pool_detail_breadcrumb",
    )


def _header() -> rx.Component:
    p = PoolDetailState.pool
    icon = rx.cond(
        p["icon_url"] != "",
        rx.image(
            src=p["icon_url"],
            width="64px", height="64px",
            border_radius="12px",
            style={"objectFit": "cover"},
            flex_shrink="0",
            custom_attrs={"referrerpolicy": "no-referrer", "loading": "lazy"},
        ),
        rx.center(
            rx.icon("hexagon", size=28, color="var(--gray-9)"),
            min_width="64px", height="64px",
            border_radius="12px",
            background="var(--gray-4)",
            flex_shrink="0",
        ),
    )
    name_row = rx.hstack(
        rx.cond(
            p["ticker"] != "",
            rx.badge(p["ticker"], variant="solid", color_scheme="amber", radius="full", size="2"),
            rx.fragment(),
        ),
        rx.cond(
            p["pool_name"] != "",
            rx.heading(p["pool_name"], size="6", weight="bold", color="var(--gray-12)"),
            rx.heading(AuthState.t["staking_no_name"], size="6", weight="bold", color="var(--gray-10)"),
        ),
        rx.cond(
            p["is_retiring"] != "",
            rx.badge(AuthState.t["staking_badge_retiring"], color_scheme="red", variant="soft"),
            rx.fragment(),
        ),
        rx.cond(
            p["has_pending_fee_change"] != "",
            rx.badge(AuthState.t["staking_badge_pending_fee"], color_scheme="amber", variant="soft"),
            rx.fragment(),
        ),
        spacing="2", align="center", wrap="wrap",
    )
    social_row = rx.hstack(
        _social_link(p["homepage"], rx.icon("house", size=14, color="var(--amber-11)")),
        _social_link(p["twitter_url"], rx.icon("twitter", size=14, color="#1DA1F2")),
        _social_link(p["telegram_url"], rx.icon("send", size=14, color="#2AABEE")),
        _social_link(p["youtube_url"], rx.icon("youtube", size=14, color="#FF0000")),
        _social_link(p["github_url"], rx.icon("github", size=14, color="var(--gray-12)")),
        spacing="2", align="center", wrap="wrap",
    )
    pool_id_row = rx.hstack(
        rx.text(
            p["pool_id"], size="1", color="var(--gray-10)",
            style={"fontFamily": "ui-monospace, monospace", "wordBreak": "break-all"},
        ),
        rx.el.button(
            rx.icon("copy", size=12),
            on_click=[
                rx.set_clipboard(p["pool_id"]),
                rx.toast(
                    AuthState.t["staking_pool_id_copied"],
                    position="top-center",
                    style={
                        "background-color": "var(--indigo-11)",
                        "color": "white",
                        "border-radius": "0.5rem",
                    },
                ),
            ],
            style={
                "display": "inline-flex",
                "alignItems": "center",
                "border": "none",
                "background": "transparent",
                "color": "var(--gray-10)",
                "cursor": "pointer",
                "padding": "0 4px",
            },
            _hover={"color": "var(--gray-12)"},
        ),
        _relay_status(p["relay_state"]),
        spacing="2", align="center", wrap="wrap",
    )
    return rx.box(
        rx.hstack(
            icon,
            rx.vstack(
                name_row,
                social_row,
                pool_id_row,
                spacing="2", align_items="start", flex="1", min_width="0",
            ),
            spacing="4", align="start", width="100%",
        ),
        padding="20px 22px",
        background=rx.color_mode_cond("white", "rgba(255,255,255,0.05)"),
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        width="100%",
    )


def _delegate_cta() -> rx.Component:
    """委任 CTA。SPO 一覧と同じ 3 状態（委任中 / 委任する / 認証誘導）。"""
    pid = PoolDetailState.pool["pool_id"]
    is_currently_delegated = (
        WalletState.connected
        & (WalletState.current_delegated_pool_id == pid)
    )
    delegated_badge = rx.hstack(
        rx.icon("circle-check", size=16, color="var(--amber-11)"),
        rx.text(
            AuthState.t["delegate_btn_currently"],
            size="3", weight="bold", color="var(--amber-12)",
        ),
        spacing="2",
        align="center",
        padding="12px 22px",
        border_radius="999px",
        background="var(--amber-3)",
        border="1px solid var(--amber-8)",
        cursor="default",
        style={"display": "inline-flex"},
    )
    btn_style = {
        "display": "inline-flex",
        "alignItems": "center",
        "gap": "8px",
        "padding": "12px 26px",
        "borderRadius": "999px",
        "background": "var(--amber-9)",
        "border": "1.5px solid var(--amber-9)",
        "cursor": "pointer",
        "transition": "background 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease",
        "boxShadow": "0 2px 6px rgba(245,158,11,0.25)",
    }
    btn_hover = {
        "background": "var(--amber-10)",
        "transform": "translateY(-1px)",
        "box_shadow": "0 6px 14px -2px rgba(245,158,11,0.35)",
    }
    delegate_active = rx.el.button(
        rx.icon("zap", size=16, color="white"),
        rx.text(
            AuthState.t["delegate_btn"],
            color="white",
            style={"fontSize": "15px", "fontWeight": "700", "lineHeight": "1.0"},
        ),
        on_click=WalletState.request_delegate_to_pool(pid),
        style=btn_style,
        _hover=btn_hover,
    )
    delegate_prompt_auth = rx.el.button(
        rx.icon("zap", size=16, color="white"),
        rx.text(
            AuthState.t["delegate_btn"],
            color="white",
            style={"fontSize": "15px", "fontWeight": "700", "lineHeight": "1.0"},
        ),
        on_click=AuthState.open_auth_required_modal,
        style=btn_style,
        _hover=btn_hover,
    )
    return rx.cond(
        is_currently_delegated,
        delegated_badge,
        rx.cond(WalletState.connected, delegate_active, delegate_prompt_auth),
    )


def _saturation_row() -> rx.Component:
    p = PoolDetailState.pool
    sat_label = rx.hstack(
        rx.text(p["saturation_pct"], "%", size="2", weight="bold", color="var(--gray-12)"),
        rx.cond(
            p["is_saturated"] == "1",
            rx.badge(AuthState.t["staking_badge_saturated"], color_scheme="red", variant="soft", size="1"),
            rx.cond(
                p["is_saturated"] == "warn",
                rx.badge(AuthState.t["staking_badge_warning"], color_scheme="amber", variant="soft", size="1"),
                rx.fragment(),
            ),
        ),
        spacing="2", align="center",
    )
    return rx.hstack(
        rx.text(AuthState.t["staking_metric_saturation"], size="2", color="var(--gray-10)", weight="medium"),
        rx.box(_saturation_bar(p), flex="1"),
        rx.box(sat_label, flex_shrink="0", min_width="110px"),
        spacing="3", align="center", width="100%",
    )


def _metrics_grid() -> rx.Component:
    p = PoolDetailState.pool
    return rx.box(
        _ada_metric_with_tooltip(
            AuthState.t["staking_metric_stake"],
            p["stake_ada_ja"], p["stake_ada_en"], p["stake_ada"],
            emphasis=True,
        ),
        _ada_metric_with_tooltip(
            AuthState.t["staking_metric_pledge"],
            p["pledge_ada_ja"], p["pledge_ada_en"], p["pledge_ada"],
        ),
        _metric(AuthState.t["staking_metric_margin"], p["margin_pct"], "%"),
        _metric(AuthState.t["staking_metric_fixed_cost"], p["fixed_cost_ada"], "ADA"),
        _metric(AuthState.t["staking_metric_delegators"], p["delegators"], ""),
        _metric(AuthState.t["staking_metric_blocks"], p["block_count"], ""),
        _metric(AuthState.t["staking_metric_recent5ep"], p["history_total"], "", emphasis=True),
        _metric(AuthState.t["staking_metric_apy"], p["apy_avg"], "%", emphasis=True),
        width="100%",
        style={
            "display": "grid",
            "gap": "16px",
            "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
            "@media (min-width: 768px)": {
                "gridTemplateColumns": "repeat(4, minmax(0, 1fr))",
            },
        },
    )


def _note_row(icon: str, label, value, color: str) -> rx.Component:
    return rx.hstack(
        rx.icon(icon, size=15, color=color, flex_shrink="0"),
        rx.text(label, size="2", color="var(--gray-11)"),
        rx.text(value, size="2", weight="bold", color="var(--gray-12)"),
        spacing="2", align="center",
    )


def _info_section() -> rx.Component:
    p = PoolDetailState.pool
    return rx.box(
        rx.vstack(
            rx.text(
                AuthState.t["pool_detail_section_info"],
                size="3", weight="bold", color="var(--gray-12)",
            ),
            _saturation_row(),
            _metrics_grid(),
            # 手数料変更予告 / 退役予告 / 登録エポック
            rx.cond(
                p["has_pending_fee_change"] != "",
                _note_row(
                    "triangle-alert",
                    AuthState.t["pool_detail_pending_fee_epoch"],
                    p["pending_effective_epoch"],
                    "var(--amber-10)",
                ),
                rx.fragment(),
            ),
            rx.cond(
                p["is_retiring"] != "",
                _note_row(
                    "circle-x",
                    AuthState.t["pool_detail_retiring_epoch"],
                    p["retiring_epoch"],
                    "var(--red-10)",
                ),
                rx.fragment(),
            ),
            rx.cond(
                p["active_epoch"] != "",
                _note_row(
                    "calendar",
                    AuthState.t["pool_detail_registered_epoch"],
                    p["active_epoch"],
                    "var(--gray-9)",
                ),
                rx.fragment(),
            ),
            spacing="4", align_items="stretch", width="100%",
        ),
        padding="20px 22px",
        background=rx.color_mode_cond("var(--gray-2)", "rgba(255,255,255,0.015)"),
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 5)}",
        width="100%",
    )


def _about_section() -> rx.Component:
    p = PoolDetailState.pool
    return rx.cond(
        p["about_full"] != "",
        rx.box(
            rx.vstack(
                rx.text(
                    AuthState.t["pool_detail_about"],
                    size="3", weight="bold", color="var(--gray-12)",
                ),
                rx.text(
                    p["about_full"],
                    size="2", color="var(--gray-11)", line_height="1.7",
                    style={"whiteSpace": "pre-wrap"},
                ),
                spacing="3", align_items="start", width="100%",
            ),
            padding="20px 22px",
            background=rx.color_mode_cond("white", "rgba(255,255,255,0.05)"),
            border_radius="12px",
            border=f"1px solid {rx.color('gray', 5)}",
            width="100%",
        ),
        rx.fragment(),
    )


# ─── ページ ────────────────────────────────────────────────────────────────────


@template(
    route="/pool/[pool_id]",
    title="ステークプール詳細 | ステーキング | Cardanoism",
    on_load=PoolDetailState.on_load,
)
def staking_pool_detail_page() -> rx.Component:
    return rx.cond(
        PoolDetailState.load,
        rx.box(
            rx.html(SPO_CSS),
            # 委任確認モーダル（1 ページに 1 度だけマウント）
            delegation_dialog(),
            rx.vstack(
                _breadcrumb(),
                staking_subnav("spo"),
                rx.cond(
                    PoolDetailState.not_found,
                    rx.callout(
                        AuthState.t["pool_detail_not_found"],
                        icon="triangle-alert",
                        color_scheme="red",
                    ),
                    rx.vstack(
                        _header(),
                        rx.flex(
                            _delegate_cta(),
                            justify="end",
                            width="100%",
                        ),
                        _info_section(),
                        _about_section(),
                        spacing="4", width="100%",
                    ),
                ),
                spacing="4", width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
