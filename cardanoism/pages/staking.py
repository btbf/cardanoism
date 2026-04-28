"""
staking.py
ステーキング > ダッシュボード（/staking）

データソースは pools テーブル（notify_worker.py --event pool_sync で同期）。
ページ側は DB を読むだけで Koios を叩かない。
"""
from __future__ import annotations

import logging
from typing import Any

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.fiat_db import get_fiat_rate
from cardanoism.backend.pool_db import get_network_summary, get_top_pools
from cardanoism.backend.price import format_ada, format_jpy_short, format_usd_short
from cardanoism.components.staking_nav import staking_subnav

logger = logging.getLogger(__name__)


# ─── State ────────────────────────────────────────────────────────────────────


class StakingDashboardState(rx.State):
    load: bool = False
    error: str = ""

    # ネットワーク集計
    total_pools: int = 0
    active_pools: int = 0
    retiring_pools: int = 0
    saturated_pools: int = 0
    total_delegators: int = 0
    total_live_stake_ada_display: str = "-"
    total_live_stake_jpy: str = ""
    total_live_stake_usd: str = ""

    # TOP プール一覧
    top_pools: list[dict[str, str]] = []

    def _fetch(self):
        try:
            rate = get_fiat_rate() or {}
            ada_jpy = float(rate.get("ada_jpy") or 0)
            ada_usd = float(rate.get("ada_usd") or 0)

            summary = get_network_summary()
            self.total_pools = int(summary.get("total_pools") or 0)
            self.active_pools = int(summary.get("active_pools") or 0)
            self.retiring_pools = int(summary.get("retiring_pools") or 0)
            self.saturated_pools = int(summary.get("saturated_pools") or 0)
            self.total_delegators = int(summary.get("total_delegators") or 0)

            total_lovelace = int(summary.get("total_live_stake") or 0)
            ada = total_lovelace / 1_000_000 if total_lovelace else 0
            self.total_live_stake_ada_display = format_ada(total_lovelace, integer=True) if total_lovelace else "0"
            self.total_live_stake_jpy = format_jpy_short(ada * ada_jpy) if ada_jpy else ""
            self.total_live_stake_usd = format_usd_short(ada * ada_usd) if ada_usd else ""

            rows = get_top_pools(limit=20)
            top: list[dict[str, str]] = []
            for idx, r in enumerate(rows):
                stake = int(r.get("live_stake") or 0)
                sat_raw = r.get("live_saturation")
                sat_pct = float(sat_raw) * 100.0 if sat_raw is not None else 0.0
                # CSS の width として安全な範囲に丸める（過飽和は 100% で頭打ちにし、別途バッジで示す）
                sat_bar = max(0.0, min(100.0, sat_pct))
                top.append({
                    "rank":          str(idx + 1),
                    "pool_id":       str(r.get("pool_id_bech32") or ""),
                    "ticker":        str(r.get("ticker") or ""),
                    "pool_name":     str(r.get("pool_name") or ""),
                    "stake_ada":     format_ada(stake, integer=True) if stake else "0",
                    "saturation_pct": f"{sat_pct:.1f}",
                    "saturation_bar": f"{sat_bar:.1f}",
                    "is_saturated":  "1" if sat_pct >= 100.0 else ("warn" if sat_pct >= 80.0 else ""),
                })
            self.top_pools = top
        except Exception as e:
            logger.exception("StakingDashboardState._fetch: %s", e)
            self.error = str(e)

    def on_load(self):
        self.load = False
        self.error = ""
        self._fetch()
        self.load = True


# ─── UI パーツ ────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(AuthState.t["nav_staking"], size="2", weight="medium"),
        spacing="2",
        align="center",
        width="100%",
        padding_top="15px",
    )


def _stat_card(icon: str, label, value, sub=None, accent: str = "var(--amber-9)") -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    rx.icon(icon, size=18, color=accent),
                    width="36px",
                    height="36px",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    border_radius="10px",
                    background=f"color-mix(in srgb, {accent} 18%, transparent)",
                    border=f"1px solid color-mix(in srgb, {accent} 32%, transparent)",
                ),
                rx.text(label, size="2", color="var(--gray-10)", weight="medium", letter_spacing="0.04em"),
                spacing="2", align="center", width="100%",
            ),
            rx.text(value, size="7", weight="bold", color="var(--gray-12)", style={"letterSpacing": "-0.02em"}),
            rx.cond(
                sub if sub is not None else False,
                rx.text(sub if sub is not None else "", size="1", color="var(--gray-10)"),
                rx.fragment(),
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding="20px",
        border_radius="14px",
        border=f"1px solid {rx.color('gray', 4)}",
        background="var(--gray-2)",
        width="100%",
    )


def _hero_stats() -> rx.Component:
    fiat_sub = rx.cond(
        AuthState.language == "en",
        rx.cond(
            StakingDashboardState.total_live_stake_usd != "",
            rx.hstack(rx.text("≈", size="1"), rx.text(StakingDashboardState.total_live_stake_usd, size="1"), spacing="1"),
            rx.fragment(),
        ),
        rx.cond(
            StakingDashboardState.total_live_stake_jpy != "",
            rx.hstack(rx.text("≈", size="1"), rx.text(StakingDashboardState.total_live_stake_jpy, size="1"), spacing="1"),
            rx.fragment(),
        ),
    )
    return rx.grid(
        _stat_card(
            "coins",
            AuthState.t["staking_stat_total_stake"],
            rx.hstack(
                rx.text(StakingDashboardState.total_live_stake_ada_display, size="7", weight="bold", color="var(--gray-12)"),
                rx.text("ADA", size="2", color="var(--gray-10)", margin_left="6px"),
                spacing="0", align="baseline",
            ),
            sub=fiat_sub,
            accent="var(--amber-9)",
        ),
        _stat_card(
            "server",
            AuthState.t["staking_stat_active_pools"],
            StakingDashboardState.active_pools.to_string(),
            sub=AuthState.t["staking_stat_total_pools_label"] + ": " + StakingDashboardState.total_pools.to_string(),
            accent="var(--blue-9)",
        ),
        _stat_card(
            "users",
            AuthState.t["staking_stat_total_delegators"],
            StakingDashboardState.total_delegators.to_string(),
            accent="var(--green-9)",
        ),
        _stat_card(
            "triangle-alert",
            AuthState.t["staking_stat_saturated_pools"],
            StakingDashboardState.saturated_pools.to_string(),
            sub=AuthState.t["staking_stat_retiring_label"] + ": " + StakingDashboardState.retiring_pools.to_string(),
            accent="var(--red-9)",
        ),
        columns={"base": "1", "sm": "2", "md": "4"},
        spacing="3",
        width="100%",
    )


def _saturation_bar(p) -> rx.Component:
    """0〜100% の飽和率バー。80% 超 = 黄色、100% 超 = 赤。"""
    fill_color = rx.match(
        p["is_saturated"],
        ("1", "var(--red-9)"),
        ("warn", "var(--amber-9)"),
        "var(--green-9)",
    )
    return rx.box(
        rx.box(
            width=p["saturation_bar"] + "%",
            height="100%",
            background=fill_color,
            border_radius="999px",
            transition="width 0.3s",
        ),
        width="100%",
        height="6px",
        background="var(--gray-4)",
        border_radius="999px",
        overflow="hidden",
    )


def _top_pool_row(p) -> rx.Component:
    rank = rx.center(
        rx.text("#", p["rank"], size="2", weight="bold", color="var(--gray-11)"),
        min_width="40px",
        height="32px",
        border_radius="8px",
        background="var(--gray-4)",
        flex_shrink="0",
    )
    label = rx.cond(
        p["ticker"] != "",
        rx.text("[", p["ticker"], "] ", p["pool_name"], size="2", weight="bold", color="var(--gray-12)"),
        rx.text(p["pool_id"], size="1", color="var(--gray-10)", style={"fontFamily": "ui-monospace, monospace"}),
    )
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
    return rx.box(
        rx.hstack(
            rank,
            rx.vstack(
                rx.hstack(
                    label,
                    rx.spacer(),
                    rx.text(p["stake_ada"], size="2", weight="bold", color="var(--amber-11)"),
                    rx.text("ADA", size="1", color="var(--gray-10)"),
                    spacing="2", align="baseline", width="100%", wrap="wrap",
                ),
                rx.hstack(
                    _saturation_bar(p),
                    rx.box(sat_label, flex_shrink="0", min_width="80px"),
                    spacing="3", align="center", width="100%",
                ),
                spacing="2", align_items="stretch", flex="1", min_width="0",
            ),
            spacing="3", align="center", width="100%",
        ),
        padding="12px 14px",
        border_radius="10px",
        border=f"1px solid {rx.color('gray', 4)}",
        background="var(--gray-2)",
        width="100%",
        _hover={"background": "var(--gray-3)"},
        transition="background 0.15s",
    )


def _top_pools_section() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.heading(AuthState.t["staking_top_pools_title"], size="5", as_="h2"),
                rx.spacer(),
                rx.link(
                    rx.button(
                        AuthState.t["staking_view_all"],
                        rx.icon("arrow-right", size=14),
                        variant="soft",
                        size="2",
                        cursor="pointer",
                    ),
                    href="/staking/spo",
                    underline="none",
                ),
                width="100%", align="center",
            ),
            rx.text(AuthState.t["staking_top_pools_subtitle"], size="2", color="var(--gray-10)"),
            rx.cond(
                StakingDashboardState.top_pools,
                rx.vstack(
                    rx.foreach(StakingDashboardState.top_pools.to(list[dict[str, str]]), _top_pool_row),
                    spacing="2", width="100%",
                ),
                rx.callout(AuthState.t["staking_no_data"], icon="info", color_scheme="gray"),
            ),
            spacing="3", width="100%", align_items="stretch",
        ),
        padding_top="8px", width="100%",
    )


# ─── ページ ────────────────────────────────────────────────────────────────────


@template(
    route="/staking",
    title="ステーキング | Cardanoism",
    on_load=StakingDashboardState.on_load,
)
def staking_page() -> rx.Component:
    return rx.cond(
        StakingDashboardState.load,
        rx.box(
            rx.vstack(
                _breadcrumb(),
                staking_subnav("dashboard"),
                _hero_stats(),
                _top_pools_section(),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
