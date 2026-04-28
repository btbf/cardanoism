"""
staking_spo.py
ステーキング > SPO 一覧（/staking/spo）

データソースは pools テーブル（notify_worker.py --event pool_sync で同期）。
"""
from __future__ import annotations

import logging
from typing import Any

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.fiat_db import get_fiat_rate
from cardanoism.backend.pool_db import get_pools, count_pools
from cardanoism.backend.price import format_ada
from cardanoism.components.staking_nav import staking_subnav

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 30


# ─── State ────────────────────────────────────────────────────────────────────


class StakingSPOState(rx.State):
    load: bool = False
    error: str = ""

    inputed_value: str = ""
    search_query: str = ""
    sort: str = "stake_desc"
    only_active: bool = True

    current_page: int = 1
    total_pages: int = 0
    total_items: int = 0
    start_page: int = 1
    end_page: int = 1
    middle_page: list[int] = []

    pools: list[dict[str, str]] = []

    def _fetch(self):
        offset = (self.current_page - 1) * ITEMS_PER_PAGE
        try:
            rows = get_pools(
                search=self.search_query,
                only_active=self.only_active,
                sort=self.sort,
                limit=ITEMS_PER_PAGE,
                offset=offset,
            )
            total = count_pools(search=self.search_query, only_active=self.only_active)

            out: list[dict[str, str]] = []
            for idx, r in enumerate(rows):
                pool_id = str(r.get("pool_id_bech32") or "")
                # スマホ用の短縮表示（先頭 10 + ... + 末尾 8）
                if len(pool_id) > 22:
                    pool_id_short = f"{pool_id[:10]}...{pool_id[-8:]}"
                else:
                    pool_id_short = pool_id

                live_stake = int(r.get("live_stake") or 0)
                pledge = int(r.get("live_pledge") or 0)
                fixed_cost = int(r.get("fixed_cost") or 0)
                margin_raw = r.get("margin")
                margin_pct = float(margin_raw) * 100.0 if margin_raw is not None else 0.0

                sat_raw = r.get("live_saturation")
                sat_pct = float(sat_raw) * 100.0 if sat_raw is not None else 0.0
                sat_bar = max(0.0, min(100.0, sat_pct))

                status = str(r.get("pool_status") or "")
                retiring_epoch = r.get("retiring_epoch")

                out.append({
                    "rank":            str(offset + idx + 1),
                    "pool_id":         pool_id,
                    "pool_id_short":   pool_id_short,
                    "ticker":          str(r.get("ticker") or ""),
                    "pool_name":       str(r.get("pool_name") or ""),
                    "homepage":        str(r.get("homepage") or ""),
                    "stake_ada":       format_ada(live_stake, integer=True) if live_stake else "0",
                    "pledge_ada":      format_ada(pledge, integer=True) if pledge else "0",
                    "fixed_cost_ada":  format_ada(fixed_cost, integer=True) if fixed_cost else "0",
                    "margin_pct":      f"{margin_pct:.2f}",
                    "saturation_pct":  f"{sat_pct:.1f}",
                    "saturation_bar":  f"{sat_bar:.1f}",
                    "is_saturated":    "1" if sat_pct >= 100.0 else ("warn" if sat_pct >= 80.0 else ""),
                    "delegators":      str(int(r.get("live_delegators") or 0)),
                    "block_count":     str(int(r.get("block_count") or 0)),
                    "status":          status,
                    "is_retiring":     "1" if status == "retiring" else "",
                    "retiring_epoch":  str(retiring_epoch) if retiring_epoch is not None else "",
                })
            self.pools = out
            self.total_items = total
            self.total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            self.start_page = max(1, self.current_page - 3)
            self.end_page   = min(self.total_pages, self.current_page + 3)
            self.middle_page = list(range(self.start_page, self.end_page + 1))
        except Exception as e:
            logger.exception("StakingSPOState._fetch: %s", e)
            self.error = str(e)

    def on_load(self):
        self.load = False
        self.error = ""
        self.inputed_value = ""
        self.search_query = ""
        self.sort = "stake_desc"
        self.only_active = True
        self.current_page = 1
        self._fetch()
        self.load = True

    def set_input(self, v: str):
        self.inputed_value = v
        self.search_query = v
        self.current_page = 1
        self._fetch()

    def set_sort(self, v: str):
        self.sort = v
        self.current_page = 1
        self._fetch()

    def toggle_only_active(self, v: bool):
        self.only_active = bool(v)
        self.current_page = 1
        self._fetch()

    def set_page(self, p):
        try:
            self.current_page = int(p)
            self._fetch()
        except (TypeError, ValueError):
            pass

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._fetch()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._fetch()


# ─── UI パーツ ────────────────────────────────────────────────────────────────


def _breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.link(AuthState.t["nav_staking"], href="/staking", size="2", underline="hover", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(AuthState.t["staking_subnav_spo"], size="2", weight="medium"),
        spacing="2",
        align="center",
        width="100%",
        padding_top="15px",
    )


def _saturation_bar(p) -> rx.Component:
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


def _pool_card(p) -> rx.Component:
    rank_badge = rx.center(
        rx.text("#", p["rank"], size="3", weight="bold", color="var(--gray-11)"),
        min_width="48px",
        height="48px",
        border_radius="10px",
        background="var(--gray-4)",
        flex_shrink="0",
    )
    name = rx.hstack(
        rx.cond(
            p["ticker"] != "",
            rx.badge(p["ticker"], variant="solid", color_scheme="amber", radius="full"),
            rx.fragment(),
        ),
        rx.cond(
            p["pool_name"] != "",
            rx.text(p["pool_name"], size="3", weight="bold", color="var(--gray-12)"),
            rx.text(AuthState.t["staking_no_name"], size="3", weight="bold", color="var(--gray-10)"),
        ),
        rx.cond(
            p["is_retiring"] != "",
            rx.badge(AuthState.t["staking_badge_retiring"], color_scheme="red", variant="soft"),
            rx.fragment(),
        ),
        spacing="2", align="center", wrap="wrap",
    )
    pool_id_inline = rx.hstack(
        rx.text(p["pool_id_short"], size="1", color="var(--gray-10)",
                style={"fontFamily": "ui-monospace, monospace", "wordBreak": "break-all"}),
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
        spacing="1", align="center",
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

    metrics = rx.grid(
        _metric(AuthState.t["staking_metric_stake"], p["stake_ada"], "ADA", emphasis=True),
        _metric(AuthState.t["staking_metric_pledge"], p["pledge_ada"], "ADA"),
        _metric(AuthState.t["staking_metric_margin"], p["margin_pct"], "%"),
        _metric(AuthState.t["staking_metric_fixed_cost"], p["fixed_cost_ada"], "ADA"),
        _metric(AuthState.t["staking_metric_delegators"], p["delegators"], ""),
        _metric(AuthState.t["staking_metric_blocks"], p["block_count"], ""),
        columns={"base": "2", "sm": "3", "md": "6"},
        spacing="3",
        width="100%",
    )

    saturation_row = rx.hstack(
        rx.text(AuthState.t["staking_metric_saturation"], size="1", color="var(--gray-10)", weight="medium"),
        rx.box(_saturation_bar(p), flex="1"),
        rx.box(sat_label, flex_shrink="0", min_width="100px"),
        spacing="3", align="center", width="100%",
    )

    return rx.box(
        rx.vstack(
            rx.hstack(
                rank_badge,
                rx.vstack(
                    name,
                    pool_id_inline,
                    spacing="1", align_items="start", flex="1", min_width="0",
                ),
                rx.cond(
                    p["homepage"] != "",
                    rx.link(
                        rx.icon("external-link", size=15, color="var(--gray-10)"),
                        href=p["homepage"],
                        is_external=True,
                        underline="none",
                    ),
                    rx.fragment(),
                ),
                spacing="3", align="center", width="100%",
            ),
            saturation_row,
            metrics,
            spacing="3", align_items="stretch", width="100%",
        ),
        padding="16px 18px",
        border_radius="12px",
        border=f"1px solid {rx.color('gray', 4)}",
        background="var(--gray-2)",
        width="100%",
        _hover={"background": "var(--gray-3)"},
        transition="background 0.15s",
    )


def _metric(label, value, unit: str, emphasis: bool = False) -> rx.Component:
    value_color = "var(--amber-11)" if emphasis else "var(--gray-12)"
    return rx.vstack(
        rx.text(label, size="1", color="var(--gray-10)", weight="medium"),
        rx.hstack(
            rx.text(value, size="3", weight="bold", color=value_color),
            rx.cond(
                unit != "",
                rx.text(unit, size="1", color="var(--gray-10)"),
                rx.fragment(),
            ),
            spacing="1", align="baseline",
        ),
        spacing="0", align_items="start",
    )


def _filter_bar() -> rx.Component:
    return rx.hstack(
        rx.input(
            placeholder=AuthState.t["staking_search_placeholder"],
            size="3",
            max_length=100,
            value=StakingSPOState.inputed_value,
            on_change=lambda v: StakingSPOState.set_input(v).debounce(400),
            flex="1",
            min_width="0",
        ),
        rx.select.root(
            rx.select.trigger(),
            rx.select.content(
                rx.select.item(AuthState.t["staking_sort_stake_desc"],      value="stake_desc"),
                rx.select.item(AuthState.t["staking_sort_pledge_desc"],     value="pledge_desc"),
                rx.select.item(AuthState.t["staking_sort_saturation_desc"], value="saturation_desc"),
                rx.select.item(AuthState.t["staking_sort_saturation_asc"],  value="saturation_asc"),
                rx.select.item(AuthState.t["staking_sort_fee_asc"],         value="fee_asc"),
                rx.select.item(AuthState.t["staking_sort_blocks_desc"],     value="blocks_desc"),
                rx.select.item(AuthState.t["staking_sort_delegators_desc"], value="delegators_desc"),
                rx.select.item(AuthState.t["staking_sort_ticker_asc"],      value="ticker_asc"),
            ),
            value=StakingSPOState.sort,
            on_change=StakingSPOState.set_sort,
            size="3",
        ),
        spacing="2", wrap="wrap", width="100%",
    )


def _pagination() -> rx.Component:
    def btn(page):
        is_active = page == StakingSPOState.current_page
        return rx.button(
            rx.text(page, weight="bold"),
            on_click=lambda: StakingSPOState.set_page(page),
            variant=rx.cond(is_active, "solid", "soft"),
            radius="full",
            size="2",
            padding_x="10px",
            class_name="md:inline-flex hidden",
            _hover={"cursor": "pointer"},
        )
    return rx.flex(
        rx.button(
            rx.icon(tag="chevron-left"),
            on_click=StakingSPOState.prev_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=StakingSPOState.current_page == 1,
            _hover={"cursor": "pointer"},
        ),
        rx.foreach(StakingSPOState.middle_page, btn),
        rx.button(
            rx.icon(tag="chevron-right"),
            on_click=StakingSPOState.next_page,
            radius="full",
            size="2",
            variant="soft",
            disabled=StakingSPOState.current_page == StakingSPOState.total_pages,
            _hover={"cursor": "pointer"},
        ),
        class_name="pagination gap-2",
        padding_top="1.5em",
        justify="end",
        align="center",
    )


# ─── ページ ────────────────────────────────────────────────────────────────────


@template(
    route="/staking/spo",
    title="SPO一覧 | ステーキング | Cardanoism",
    on_load=StakingSPOState.on_load,
)
def staking_spo_page() -> rx.Component:
    return rx.cond(
        StakingSPOState.load,
        rx.box(
            rx.vstack(
                _breadcrumb(),
                staking_subnav("spo"),
                _filter_bar(),
                rx.hstack(
                    rx.text(AuthState.t["gov_search_results"], size="3"),
                    rx.text(StakingSPOState.total_items, size="5", weight="bold", color="var(--amber-11)"),
                    rx.text(AuthState.t["gov_results_unit"], size="3"),
                    spacing="2", align="baseline", width="100%", wrap="wrap",
                ),
                rx.cond(
                    StakingSPOState.pools,
                    rx.vstack(
                        rx.foreach(StakingSPOState.pools.to(list[dict[str, str]]), _pool_card),
                        spacing="2", width="100%",
                    ),
                    rx.callout(AuthState.t["staking_no_pools"], icon="info", color_scheme="gray"),
                ),
                rx.cond(StakingSPOState.pools, _pagination(), rx.fragment()),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="40px"),
    )
